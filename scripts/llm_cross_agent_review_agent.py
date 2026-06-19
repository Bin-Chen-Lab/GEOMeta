#!/usr/bin/env python3
"""
Optional LLM reviewer for GEOMeta Stage 1 QA2 cross-agent validation issues.

This script does NOT overwrite annotations. It reads the cross-agent validation
report, builds evidence packets from the Stage 1/1.5 table, and asks an LLM
reviewer for structured recommendations:

- Correct Field
- Do Not Change
- Need Human Review

Use it only for flagged conflicts/missing related fields, not for every row.

Example
-------
PYTHONPATH=. python scripts/llm_cross_agent_review_agent.py \
  --stage1 artifacts/outputs/geometa_full_RUN_stage1_qa1_corrected_high_confidence.xlsx \
  --cross-report artifacts/outputs/geometa_full_RUN_stage1_qa2_cross_agent_validation_report.xlsx \
  --output artifacts/outputs/geometa_full_RUN_stage1_qa2_llm_cross_agent_recommendations.xlsx \
  --max-issues 50
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

# Local imports from scripts directory.
from stage1_cross_agent_validation import clean_value, read_table


REVIEW_SYSTEM_PROMPT = """You are a conservative GEOMeta cross-agent validation reviewer.

You are not the initial annotator. Your role is to review conflicts between fields
produced by different Stage 1 annotation agents.

You will receive:
- one flagged issue
- current annotations for the GSM
- same-GSE field distributions for related fields
- GSE_Info and GSM_Info snippets

Allowed decisions:
- Correct Field
- Do Not Change
- Need Human Review

Rules:
1. Do not force all samples in a GSE to be identical. Disease, tissue, treatment,
   dose, timepoint, sex, genotype, and model type may vary by sample.
2. Do not overwrite existing non-empty values unless evidence is strong.
3. Prefer Need Human Review when multiple biologically plausible assignments exist.
4. If you suggest a correction, specify exactly one field and one corrected value.
5. Use GSE_Info for study-level context and GSM_Info/title/source for sample-level context.
6. Return strict JSON only. Do not include markdown or extra text."""

REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "decision": {"type": "string", "enum": ["Correct Field", "Do Not Change", "Need Human Review"]},
        "field_to_correct": {"type": "string"},
        "suggested_value": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string"},
        "evidence_used": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["decision", "field_to_correct", "suggested_value", "confidence", "reason", "evidence_used", "warnings"],
}


def read_issues(cross_report: Path, sheet_name: str = "Cross_Agent_Issues") -> pd.DataFrame:
    return pd.read_excel(cross_report, sheet_name=sheet_name, dtype=str, keep_default_na=False)


def select_issues(
    issues_df: pd.DataFrame,
    max_issues: Optional[int],
    include_medium: bool,
    include_low: bool,
    rule_ids: Optional[List[str]],
) -> pd.DataFrame:
    if issues_df.empty:
        return issues_df

    df = issues_df.copy()
    severities = ["High"]
    if include_medium:
        severities.append("Medium")
    if include_low:
        severities.append("Low")
    df = df[df["Severity"].isin(severities)].copy()

    if rule_ids:
        df = df[df["Rule_ID"].isin(rule_ids)].copy()

    priority = {"High": 1, "Medium": 2, "Low": 3}
    df["_severity_sort"] = df["Severity"].map(priority).fillna(99)
    df = df.sort_values(["_severity_sort", "GSE_ID", "GSM_ID", "Rule_ID"], kind="stable").drop(columns=["_severity_sort"])

    if max_issues is not None:
        df = df.head(max_issues)
    return df


def parse_json_cell(x: Any) -> Dict[str, Any]:
    text = clean_value(x)
    if not text:
        return {}
    try:
        val = json.loads(text)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def build_evidence_packet(
    stage1_df: pd.DataFrame,
    issue: Dict[str, Any],
    gse_col: str,
    gsm_col: str,
    max_gse_info_chars: int,
    max_gsm_info_chars: int,
    max_same_gse_examples: int,
) -> Dict[str, Any]:
    gse_id = clean_value(issue.get("GSE_ID", ""))
    gsm_id = clean_value(issue.get("GSM_ID", ""))
    gse_df = stage1_df[stage1_df[gse_col].astype(str).str.strip() == gse_id].copy()
    row_df = gse_df[gse_df[gsm_col].astype(str).str.strip() == gsm_id]

    current_row: Dict[str, Any] = {}
    if not row_df.empty:
        row = row_df.iloc[0]
        fields = [
            "GSM_ID", "GSE_ID", "Seq_Type", "Organism", "Strain", "Genotype",
            "RNA_Library", "RNA_Source", "Tissue", "Experimental_Setting", "Model_Type",
            "Disease", "GSE_Pert", "GSM_Pert", "Pert", "Pert_Dose", "Pert_Freq",
            "Pert_Duration", "Route_Admin", "SampleType", "Specimen_Type", "Race",
            "Ethnicity", "Age", "Sex", "Timepoint", "Outcome",
        ]
        current_row = {c: clean_value(row.get(c, "")) for c in fields if c in row.index}

        gse_info = clean_value(row.get("GSE_Info", ""))
        gsm_info = clean_value(row.get("GSM_Info", ""))
    else:
        gse_info = ""
        gsm_info = ""

    if len(gse_info) > max_gse_info_chars:
        gse_info = gse_info[:max_gse_info_chars] + " ...[truncated]"
    if len(gsm_info) > max_gsm_info_chars:
        gsm_info = gsm_info[:max_gsm_info_chars] + " ...[truncated]"

    fields_involved = [x.strip() for x in clean_value(issue.get("Fields_Involved", "")).split(";") if x.strip()]
    helper_cols = [gsm_col] + [c for c in fields_involved if c in gse_df.columns and c != gsm_col]
    for c in ["Disease", "Tissue", "RNA_Source", "Seq_Type", "RNA_Library", "SampleType", "Specimen_Type", "GSM_Pert", "Pert", "Pert_Dose", "Timepoint", "Sex", "Age"]:
        if c in gse_df.columns and c not in helper_cols:
            helper_cols.append(c)

    examples: List[Dict[str, str]] = []
    if not gse_df.empty and helper_cols:
        examples_df = gse_df[helper_cols].head(max_same_gse_examples)
        examples = [
            {c: clean_value(r.get(c, "")) for c in helper_cols}
            for _, r in examples_df.iterrows()
        ]

    return {
        "issue": {
            "Issue_ID": issue.get("Issue_ID", ""),
            "GSE_ID": gse_id,
            "GSM_ID": gsm_id,
            "Rule_ID": issue.get("Rule_ID", ""),
            "Rule_Name": issue.get("Rule_Name", ""),
            "Severity": issue.get("Severity", ""),
            "Issue_Type": issue.get("Issue_Type", ""),
            "Fields_Involved": fields_involved,
            "Current_Values": parse_json_cell(issue.get("Current_Values_JSON", "")),
            "Same_GSE_Distributions": parse_json_cell(issue.get("Same_GSE_Distributions_JSON", "")),
            "Suggested_Action": issue.get("Suggested_Action", ""),
            "Suggested_Field": issue.get("Suggested_Field", ""),
            "Suggested_Value": issue.get("Suggested_Value", ""),
            "Rule_Rationale": issue.get("Rationale", ""),
        },
        "current_row_annotations": current_row,
        "gse_info": gse_info,
        "gsm_info": gsm_info,
        "same_gse_examples": examples,
    }


def get_client_and_mode() -> tuple[Any, str, str]:
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

    raise RuntimeError("No LLM credentials found. Set Azure OpenAI variables or OPENAI_API_KEY.")


def call_llm_review(client: Any, model_or_deployment: str, packet: Dict[str, Any], temperature: float = 0.0) -> Dict[str, Any]:
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "geometa_cross_agent_review_decision",
            "strict": True,
            "schema": REVIEW_SCHEMA,
        },
    }

    resp = client.chat.completions.create(
        model=model_or_deployment,
        messages=[
            {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(packet, ensure_ascii=False, indent=2)},
        ],
        response_format=response_format,
        temperature=temperature,
    )
    return json.loads(resp.choices[0].message.content)


def main() -> None:
    parser = argparse.ArgumentParser(description="Optional LLM reviewer for Stage 1 QA2 cross-agent validation")
    parser.add_argument("--stage1", required=True, help="Stage 1/Stage 1 QA1 corrected table")
    parser.add_argument("--cross-report", required=True, help="Stage 1 QA2 cross-agent validation report")
    parser.add_argument("--output", required=True, help="Output Excel file")
    parser.add_argument("--gse-col", default="GSE_ID")
    parser.add_argument("--gsm-col", default="GSM_ID")
    parser.add_argument("--max-issues", type=int, default=None)
    parser.add_argument("--include-medium", action="store_true", help="Also send Medium severity issues to LLM")
    parser.add_argument("--include-low", action="store_true", help="Also send Low severity issues to LLM")
    parser.add_argument("--rule-ids", default=None, help="Optional comma-separated Rule_ID filter, e.g. R001,R030")
    parser.add_argument("--max-gse-info-chars", type=int, default=3000)
    parser.add_argument("--max-gsm-info-chars", type=int, default=2200)
    parser.add_argument("--max-same-gse-examples", type=int, default=12)
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    args = parser.parse_args()

    stage1_df = read_table(Path(args.stage1))
    issues_df = read_issues(Path(args.cross_report))
    rule_ids = [x.strip() for x in args.rule_ids.split(",") if x.strip()] if args.rule_ids else None
    selected = select_issues(
        issues_df=issues_df,
        max_issues=args.max_issues,
        include_medium=args.include_medium,
        include_low=args.include_low,
        rule_ids=rule_ids,
    )

    print(f"Selected {len(selected):,} cross-agent issues for LLM review.")
    client, _mode, model_or_deployment = get_client_and_mode()

    rows: List[Dict[str, Any]] = []
    packet_rows: List[Dict[str, Any]] = []
    for i, (_, issue_row) in enumerate(selected.iterrows(), start=1):
        issue = issue_row.to_dict()
        packet = build_evidence_packet(
            stage1_df=stage1_df,
            issue=issue,
            gse_col=args.gse_col,
            gsm_col=args.gsm_col,
            max_gse_info_chars=args.max_gse_info_chars,
            max_gsm_info_chars=args.max_gsm_info_chars,
            max_same_gse_examples=args.max_same_gse_examples,
        )
        try:
            decision = call_llm_review(client, model_or_deployment, packet)
            status = "OK"
            error = ""
        except Exception as exc:  # noqa: BLE001
            decision = {
                "decision": "Need Human Review",
                "field_to_correct": "",
                "suggested_value": "",
                "confidence": 0.0,
                "reason": "LLM review failed; route to human review.",
                "evidence_used": [],
                "warnings": [],
            }
            status = "ERROR"
            error = repr(exc)

        rows.append(
            {
                "Issue_ID": issue.get("Issue_ID", ""),
                "GSE_ID": issue.get("GSE_ID", ""),
                "GSM_ID": issue.get("GSM_ID", ""),
                "Rule_ID": issue.get("Rule_ID", ""),
                "Rule_Name": issue.get("Rule_Name", ""),
                "Severity": issue.get("Severity", ""),
                "LLM_Status": status,
                "LLM_Error": error,
                "LLM_Decision": decision.get("decision", ""),
                "LLM_Field_To_Correct": decision.get("field_to_correct", ""),
                "LLM_Suggested_Value": decision.get("suggested_value", ""),
                "LLM_Confidence": decision.get("confidence", ""),
                "LLM_Reason": decision.get("reason", ""),
                "Evidence_Used_JSON": json.dumps(decision.get("evidence_used", []), ensure_ascii=False),
                "Warnings_JSON": json.dumps(decision.get("warnings", []), ensure_ascii=False),
                "Human_Final_Decision": "",
                "Human_Field_To_Correct": "",
                "Human_Final_Value": "",
                "Human_Notes": "",
            }
        )
        packet_rows.append(
            {
                "Issue_ID": issue.get("Issue_ID", ""),
                "Evidence_Packet_JSON": json.dumps(packet, ensure_ascii=False),
            }
        )
        print(f"[{i}/{len(selected)}] {issue.get('GSE_ID')} {issue.get('GSM_ID')} {issue.get('Rule_ID')} -> {decision.get('decision')} ({status})")
        time.sleep(args.sleep_seconds)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, index=False, sheet_name="LLM_Recommendations")
        pd.DataFrame(packet_rows).to_excel(writer, index=False, sheet_name="Evidence_Packets")

    print(f"Saved LLM cross-agent recommendations: {output}")


if __name__ == "__main__":
    main()
