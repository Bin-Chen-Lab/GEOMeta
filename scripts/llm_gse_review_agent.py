#!/usr/bin/env python3
"""
Optional LLM reviewer for Stage 1 QA1 ambiguous within-GSE issues.

This script does NOT overwrite Stage 1 annotations. It reads the Stage 1 QA1 review
queue and original/corrected Stage 1 table, builds evidence packets for selected
GSE-field issues, and asks an LLM reviewer for a structured recommendation:

- Fill
- Do Not Fill
- Need Human Review

Recommended use
---------------
Run this only after within_gse_consistency_audit.py, and only for medium/ambiguous
issues. High-confidence blank-cell fills are already handled by deterministic rules.

Azure OpenAI environment variables
----------------------------------
AZURE_OPENAI_ENDPOINT=https://YOUR_RESOURCE.openai.azure.com/
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_DEPLOYMENT=gpt-5-or-your-deployment
AZURE_OPENAI_API_VERSION=2025-04-01-preview

OpenAI fallback environment variables
-------------------------------------
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.1
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from within_gse_consistency_audit import clean_value, is_missing, read_table


REVIEW_SYSTEM_PROMPT = """You are a GEOMeta metadata review agent. Your job is to review flagged within-GSE annotation issues after Stage 1 LLM annotation.

You are NOT the initial annotator. You are a conservative reviewer.

Given a GSE-level evidence packet, decide whether missing cells for one field should be filled, left unchanged, or sent to human review.

Allowed decisions:
- Fill
- Do Not Fill
- Need Human Review

Rules:
1. Do not force all GSMs in the same GSE to have the same value. Some fields may truly vary by disease group, tissue, dose, timepoint, sex, genotype, or treatment.
2. Fill only if the evidence strongly supports the same value for the flagged blank GSMs.
3. Do not overwrite existing non-empty values.
4. Use GSE_Info for shared study context and GSM_Info/title/source for sample-specific assignment.
5. If multiple biologically plausible values exist, choose Need Human Review.
6. If the current blank likely represents a true unavailable value, choose Do Not Fill.
7. Provide concise evidence-based reasoning.

Return strict JSON only."""

REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "decision": {"type": "string", "enum": ["Fill", "Do Not Fill", "Need Human Review"]},
        "suggested_value": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string"},
        "evidence_used": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["decision", "suggested_value", "confidence", "reason", "evidence_used", "warnings"],
}


def read_review_queue(report_path: Path, sheet_name: str = "LLM_Human_Review_Queue") -> pd.DataFrame:
    return pd.read_excel(report_path, sheet_name=sheet_name, dtype=str, keep_default_na=False)


def choose_issues_for_llm(queue_df: pd.DataFrame, include_high_priority: bool = True, max_issues: Optional[int] = None) -> pd.DataFrame:
    if queue_df.empty:
        return queue_df

    df = queue_df.copy()
    # Exclude deterministic high-confidence candidate fills already handled by rules unless explicitly needed.
    # Keep partial missing, conflicts, and whole-GSE missing because these need reasoning.
    mask = df["Issue_Type"].astype(str).str.contains("Partial Missing|Conflict|Whole-GSE Missing", case=False, na=False)
    df = df.loc[mask].copy()

    if not include_high_priority:
        df = df[~df["Review_Priority"].astype(str).str.startswith("High - Candidate Fill")].copy()

    priority_order = {
        "High - Targeted Re-annotation": 1,
        "High - Biological/Design Conflict": 2,
        "High - Candidate Fill": 3,
        "Medium - Candidate Review": 4,
        "Medium - Inconsistency Review": 5,
        "Medium - Missing Field Review": 6,
    }
    df["_priority_sort"] = df["Review_Priority"].map(priority_order).fillna(99)
    df = df.sort_values(["_priority_sort", "GSE_ID", "Field"]).drop(columns=["_priority_sort"])
    if max_issues is not None:
        df = df.head(max_issues)
    return df


def build_evidence_packet(
    stage1_df: pd.DataFrame,
    issue_row: Dict[str, Any],
    gse_col: str,
    gsm_col: str,
    max_gsm_info_chars: int,
    max_samples: int,
) -> Dict[str, Any]:
    gse_id = clean_value(issue_row["GSE_ID"])
    field = clean_value(issue_row["Field"])
    gse_df = stage1_df[stage1_df[gse_col].astype(str) == gse_id].copy()

    if gse_df.empty:
        return {
            "issue": issue_row,
            "error": f"No rows found for {gse_id}",
        }

    # Use the first non-empty GSE_Info as study-level evidence if present.
    gse_info = ""
    if "GSE_Info" in gse_df.columns:
        nonempty = [clean_value(x) for x in gse_df["GSE_Info"].tolist() if clean_value(x)]
        gse_info = nonempty[0] if nonempty else ""

    helper_cols = [gsm_col]
    for c in ["Sample_Title", "Title", "Source_Name", "GSM_Info", field, "Disease", "Tissue", "RNA_Source", "Seq_Type", "RNA_Library", "SampleType", "Specimen_Type", "GSM_Pert", "Pert", "Pert_Dose", "Timepoint", "Sex", "Age"]:
        if c in gse_df.columns and c not in helper_cols:
            helper_cols.append(c)

    # Prioritize rows where the target field is missing, plus a representative set of non-missing rows.
    missing_mask = gse_df[field].apply(lambda x: is_missing(x, treat_na_as_missing=False)) if field in gse_df.columns else pd.Series(False, index=gse_df.index)
    missing_rows = gse_df.loc[missing_mask, helper_cols].head(max_samples)
    nonmissing_rows = gse_df.loc[~missing_mask, helper_cols].head(max_samples)
    selected = pd.concat([missing_rows, nonmissing_rows], axis=0).drop_duplicates(subset=[gsm_col]).head(max_samples * 2)

    sample_records: List[Dict[str, Any]] = []
    for _, row in selected.iterrows():
        rec = {c: clean_value(row.get(c, "")) for c in helper_cols}
        if "GSM_Info" in rec and len(rec["GSM_Info"]) > max_gsm_info_chars:
            rec["GSM_Info"] = rec["GSM_Info"][:max_gsm_info_chars] + " ...[truncated]"
        sample_records.append(rec)

    value_distribution = {}
    if field in gse_df.columns:
        vals = [clean_value(x) for x in gse_df[field].tolist()]
        for v in vals:
            key = "<blank>" if is_missing(v, treat_na_as_missing=False) else v
            value_distribution[key] = value_distribution.get(key, 0) + 1

    return {
        "issue": issue_row,
        "gse_id": gse_id,
        "field": field,
        "gse_info": gse_info,
        "value_distribution": value_distribution,
        "missing_gsm_ids": gse_df.loc[missing_mask, gsm_col].astype(str).head(200).tolist() if field in gse_df.columns else [],
        "sample_records": sample_records,
    }


def get_client_and_mode() -> tuple[Any, str, str]:
    # Lazily import so users can run rule-based audit without openai installed.
    from openai import AzureOpenAI, OpenAI

    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    azure_api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")

    if azure_endpoint and azure_key and azure_deployment:
        client = AzureOpenAI(api_key=azure_key, azure_endpoint=azure_endpoint, api_version=azure_api_version)
        return client, "azure", azure_deployment

    openai_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-5.1")
    if openai_key:
        client = OpenAI(api_key=openai_key)
        return client, "openai", model

    raise RuntimeError(
        "No LLM credentials found. Set Azure OpenAI environment variables or OPENAI_API_KEY."
    )


def call_llm_review(client: Any, mode: str, model_or_deployment: str, packet: Dict[str, Any], temperature: float = 0.0) -> Dict[str, Any]:
    user_content = json.dumps(packet, ensure_ascii=False, indent=2)

    # Use Chat Completions compatible shape for Azure/OpenAI SDKs.
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "geometa_review_decision",
            "strict": True,
            "schema": REVIEW_SCHEMA,
        },
    }

    resp = client.chat.completions.create(
        model=model_or_deployment,
        messages=[
            {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format=response_format,
        temperature=temperature,
    )
    content = resp.choices[0].message.content
    return json.loads(content)


def main() -> None:
    parser = argparse.ArgumentParser(description="Optional LLM reviewer for Stage 1 QA1 within-GSE issues")
    parser.add_argument("--stage1", required=True, help="Stage 1 table or high-confidence-corrected Stage 1 file")
    parser.add_argument("--consistency-report", required=True, help="Output report from within_gse_consistency_audit.py")
    parser.add_argument("--output", required=True, help="Output xlsx with LLM recommendations")
    parser.add_argument("--gse-col", default="GSE_ID")
    parser.add_argument("--gsm-col", default="GSM_ID")
    parser.add_argument("--max-issues", type=int, default=None)
    parser.add_argument("--exclude-high-candidate-fill", action="store_true", help="Skip high-priority candidate fill issues already handled by deterministic rules")
    parser.add_argument("--max-gsm-info-chars", type=int, default=1800)
    parser.add_argument("--max-samples", type=int, default=12)
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    args = parser.parse_args()

    stage1_df = read_table(Path(args.stage1))
    queue_df = read_review_queue(Path(args.consistency_report))
    issues_df = choose_issues_for_llm(
        queue_df,
        include_high_priority=not args.exclude_high_candidate_fill,
        max_issues=args.max_issues,
    )

    print(f"Selected {len(issues_df):,} issues for LLM review.")
    client, mode, model_or_deployment = get_client_and_mode()

    rows: List[Dict[str, Any]] = []
    packets: List[Dict[str, Any]] = []
    for i, (_, issue) in enumerate(issues_df.iterrows(), start=1):
        packet = build_evidence_packet(
            stage1_df=stage1_df,
            issue_row=issue.to_dict(),
            gse_col=args.gse_col,
            gsm_col=args.gsm_col,
            max_gsm_info_chars=args.max_gsm_info_chars,
            max_samples=args.max_samples,
        )
        packets.append(packet)
        try:
            decision = call_llm_review(client, mode, model_or_deployment, packet)
            status = "OK"
            error = ""
        except Exception as exc:  # noqa: BLE001
            decision = {
                "decision": "Need Human Review",
                "suggested_value": "",
                "confidence": 0.0,
                "reason": "LLM review call failed; route to human review.",
                "evidence_used": [],
                "warnings": [],
            }
            status = "ERROR"
            error = repr(exc)

        rows.append(
            {
                "Issue_ID": issue.get("Issue_ID", ""),
                "GSE_ID": issue.get("GSE_ID", ""),
                "Field": issue.get("Field", ""),
                "Issue_Type": issue.get("Issue_Type", ""),
                "Review_Priority": issue.get("Review_Priority", ""),
                "LLM_Status": status,
                "LLM_Error": error,
                "LLM_Decision": decision.get("decision", ""),
                "LLM_Suggested_Value": decision.get("suggested_value", ""),
                "LLM_Confidence": decision.get("confidence", ""),
                "LLM_Reason": decision.get("reason", ""),
                "Evidence_Used_JSON": json.dumps(decision.get("evidence_used", []), ensure_ascii=False),
                "Warnings_JSON": json.dumps(decision.get("warnings", []), ensure_ascii=False),
                "Human_Final_Decision": "",
                "Human_Notes": "",
            }
        )
        print(f"[{i}/{len(issues_df)}] {issue.get('GSE_ID')} {issue.get('Field')} -> {decision.get('decision')} ({status})")
        time.sleep(args.sleep_seconds)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    review_df = pd.DataFrame(rows)
    packets_df = pd.DataFrame([{"Issue_ID": p.get("issue", {}).get("Issue_ID", ""), "Evidence_Packet_JSON": json.dumps(p, ensure_ascii=False)} for p in packets])

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        review_df.to_excel(writer, index=False, sheet_name="LLM_Recommendations")
        packets_df.to_excel(writer, index=False, sheet_name="Evidence_Packets")

    print(f"Saved LLM recommendations: {out_path}")


if __name__ == "__main__":
    main()
