#!/usr/bin/env python3
"""
GEOMeta Stage 1 QA3: evidence-grounded verifier / targeted rescue.

Purpose
-------
Run after Stage 1 QA1 within-GSE audit and Stage 1 QA2 cross-agent validation,
before Stage 2 post-processing.

This module builds targeted evidence packets from GSE_Info/GSM_Info and current
Stage 1 annotations, asks an LLM reviewer to verify only flagged fields, and
applies only conservative, high-confidence missing-cell rescue corrections.

It is designed to cover cases that Stage 1 QA1 cannot safely solve:
- whole-GSE missing fields,
- ambiguous case/control disease labels,
- true mixed-tissue or mixed-perturbation designs,
- evidence present only in free text but missed in Stage 1.

Safety policy
-------------
- Never reannotate every field for every GSM.
- Never force all GSMs in a GSE to be identical.
- Default auto-application only fills missing/NA cells.
- Default does not overwrite existing non-empty values.
- LLM output is structured JSON and is kept as an auditable recommendation.
- Human review is required for low confidence, conflicting evidence, or non-empty overwrites.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from geo_annotation_agent.token_budget import TokenBudget, check_messages_token_budget
from geo_annotation_agent.release_policy import add_stage1_qa3_mode_a_flags


# -----------------------------------------------------------------------------
# Core field definitions
# -----------------------------------------------------------------------------

STAGE1_FIELDS = [
    "GSM_ID",
    "GSE_ID",
    "Seq_Type",
    "Organism",
    "Strain",
    "Genotype",
    "RNA_Library",
    "RNA_Source",
    "Tissue",
    "Experimental_Setting",
    "Model_Type",
    "Disease",
    "GSE_Pert",
    "GSM_Pert",
    "Pert",
    "Pert_Dose",
    "Pert_Freq",
    "Pert_Duration",
    "Route_Admin",
    "SampleType",
    "Specimen_Type",
    "Race",
    "Ethnicity",
    "Age",
    "Sex",
    "Timepoint",
    "Outcome",
]

HIGH_IMPACT_FIELDS = {
    "Disease",
    "Tissue",
    "RNA_Source",
    "RNA_Library",
    "Seq_Type",
    "Organism",
    "Experimental_Setting",
    "Model_Type",
    "GSE_Pert",
    "GSM_Pert",
    "Pert",
    "Pert_Dose",
    "Pert_Freq",
    "Pert_Duration",
    "Route_Admin",
    "SampleType",
    "Specimen_Type",
}

WHOLE_GSE_REANNOTATION_FIELDS = {
    "RNA_Library",
    "Seq_Type",
    "Organism",
    "Experimental_Setting",
    "Model_Type",
    "GSE_Pert",
    "RNA_Source",
    "Tissue",
    "Disease",
    "SampleType",
    "Specimen_Type",
}

SAMPLE_SPECIFIC_HIGH_IMPACT_FIELDS = {
    "Disease",
    "Tissue",
    "RNA_Source",
    "GSM_Pert",
    "Pert",
    "Pert_Dose",
    "Pert_Freq",
    "Pert_Duration",
    "Route_Admin",
    "SampleType",
    "Specimen_Type",
    "Timepoint",
    "Sex",
    "Age",
}

MISSING_TOKENS = {
    "",
    "na",
    "n/a",
    "nan",
    "none",
    "null",
    "unknown",
    "not specified",
    "not reported",
    "not available",
    "not applicable",
    "not provided",
    "unavailable",
}

DESIGN_FIELDS = [
    "Disease",
    "Tissue",
    "RNA_Source",
    "RNA_Library",
    "Seq_Type",
    "SampleType",
    "Specimen_Type",
    "GSE_Pert",
    "GSM_Pert",
    "Pert",
    "Pert_Dose",
    "Pert_Freq",
    "Pert_Duration",
    "Route_Admin",
    "Timepoint",
    "Genotype",
    "Strain",
    "Sex",
    "Age",
]


QA3_VALID_MODES = {"off", "smart", "full"}

QA3_SMART_HIGH_VALUE_FIELDS = {
    "Disease",
    "Tissue",
    "RNA_Source",
    "GSE_Pert",
    "GSM_Pert",
    "Pert",
    "SampleType",
    "Specimen_Type",
}

QA3_SMART_LOW_YIELD_FIELDS = {
    "RNA_Library",
    "Pert_Dose",
    "Pert_Freq",
    "Pert_Duration",
    "Route_Admin",
}

QA3_SMART_DEFAULT_MAX_TASKS = 50
QA3_FULL_DEFAULT_MAX_TASKS = 150

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------

@dataclass
class EvidenceVerifierConfig:
    gse_col: str = "GSE_ID"
    gsm_col: str = "GSM_ID"
    qa3_mode: str = "smart"
    max_tasks: Optional[int] = None
    max_gse_info_chars: int = 5000
    max_gsm_info_chars: int = 2500
    max_same_gse_examples: int = 40
    max_missing_gsm_ids_in_packet: int = 250
    min_confidence_to_apply: float = 0.90
    build_tasks_only: bool = False
    apply_accepted: bool = True
    allow_nonempty_overwrite: bool = False
    sleep_between_calls: float = 0.2
    include_stage1_qa2_medium: bool = True
    include_stage1_qa2_low: bool = False
    include_sampling_qc: bool = True
    max_sampling_qc_tasks_per_gse: int = 2
    fields_for_sampling_qc: Tuple[str, ...] = (
        "Disease",
        "Tissue",
        "RNA_Source",
        "RNA_Library",
        "GSE_Pert",
        "GSM_Pert",
        "Pert",
        "SampleType",
        "Specimen_Type",
    )


# -----------------------------------------------------------------------------
# Small helpers
# -----------------------------------------------------------------------------

def clean_value(x: Any) -> str:
    if x is None:
        return ""
    try:
        if isinstance(x, float) and x != x:
            return ""
    except Exception:
        pass
    return str(x).strip()


def norm_value(x: Any) -> str:
    return re.sub(r"\s+", " ", clean_value(x).lower()).strip()


def is_missing(x: Any) -> bool:
    return norm_value(x) in MISSING_TOKENS


def is_nonmissing(x: Any) -> bool:
    return not is_missing(x)


def safe_json_loads(x: Any) -> Any:
    text = clean_value(x)
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        return {}


def truncate_text(x: Any, max_chars: int) -> str:
    text = clean_value(x)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + " ...[truncated]"


def read_table(path: Path, sheet_name: Optional[str] = None) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        return pd.read_excel(path, sheet_name=sheet_name or 0, dtype=str, keep_default_na=False)
    if suffix == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    if suffix in {".tsv", ".txt"}:
        return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported input file type: {path}")


def read_excel_sheet_if_exists(path: Optional[Path], sheet_name: str) -> pd.DataFrame:
    if path is None or not Path(path).exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name=sheet_name, dtype=str, keep_default_na=False)
    except Exception:
        return pd.DataFrame()


def split_gsm_list(x: Any) -> List[str]:
    text = clean_value(x)
    if not text:
        return []
    parts = re.split(r"\s*[|;,]\s*|\s+", text)
    out = []
    seen = set()
    for p in parts:
        p = p.strip()
        if re.fullmatch(r"GSM\d+", p) and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def ensure_id_cols(df: pd.DataFrame, cfg: EvidenceVerifierConfig) -> pd.DataFrame:
    missing = [c for c in [cfg.gse_col, cfg.gsm_col] if c not in df.columns]
    if missing:
        raise ValueError(f"Stage1 table missing required ID columns: {missing}")
    out = df.copy()
    out[cfg.gse_col] = out[cfg.gse_col].astype(str).str.strip()
    out[cfg.gsm_col] = out[cfg.gsm_col].astype(str).str.strip()
    return out


def value_distribution(df: pd.DataFrame, fields: Iterable[str]) -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = {}
    for field in fields:
        if field not in df.columns:
            continue
        vc = df[field].map(lambda x: "<missing>" if is_missing(x) else clean_value(x)).value_counts(dropna=False)
        out[field] = {str(k): int(v) for k, v in vc.items()}
    return out


def make_design_signatures(gse_df: pd.DataFrame, cfg: EvidenceVerifierConfig, max_groups: int = 12) -> List[Dict[str, Any]]:
    fields = [c for c in DESIGN_FIELDS if c in gse_df.columns]
    if not fields:
        return []

    tmp = gse_df[[cfg.gsm_col] + fields].copy()
    for c in fields:
        tmp[c] = tmp[c].map(lambda x: "<missing>" if is_missing(x) else clean_value(x))

    # Group by the most design-informative fields that are present.
    group_fields = [c for c in ["Disease", "Tissue", "RNA_Source", "GSM_Pert", "Pert", "Pert_Dose", "Timepoint", "SampleType", "Specimen_Type"] if c in tmp.columns]
    if not group_fields:
        group_fields = fields[:5]

    rows: List[Dict[str, Any]] = []
    grouped = tmp.groupby(group_fields, dropna=False, sort=False)
    for keys, sub in grouped:
        if not isinstance(keys, tuple):
            keys = (keys,)
        desc = {field: value for field, value in zip(group_fields, keys)}
        rows.append({
            "n_samples": int(sub.shape[0]),
            "signature": desc,
            "example_gsm_ids": sub[cfg.gsm_col].astype(str).head(10).tolist(),
        })
    rows = sorted(rows, key=lambda r: -r["n_samples"])
    return rows[:max_groups]


def infer_task_type_from_stage1_qa1(issue_type: str, priority: str, field: str) -> str:
    issue_low = issue_type.lower()
    priority_low = priority.lower()
    if "whole-gse" in issue_low or "targeted re-annotation" in priority_low:
        return "whole_gse_missing_field"
    if "partial missing" in issue_low:
        return "partial_missing_targeted_rescue"
    if "conflict" in issue_low:
        if field in {"Disease", "Tissue", "RNA_Source", "GSM_Pert", "Pert", "Pert_Dose"}:
            return "mixed_design_or_case_control_review"
        return "within_gse_conflict_review"
    return "stage1_qa1_flagged_review"


# -----------------------------------------------------------------------------
# Task builder
# -----------------------------------------------------------------------------

def add_task(tasks: List[Dict[str, Any]], task: Dict[str, Any], seen: set[Tuple[str, str, str, str]]) -> None:
    key = (
        clean_value(task.get("Task_Type", "")),
        clean_value(task.get("GSE_ID", "")),
        clean_value(task.get("GSM_ID", "")),
        clean_value(task.get("Target_Field", "")),
    )
    if key in seen:
        return
    seen.add(key)
    task["Task_ID"] = f"EV{len(tasks) + 1:07d}"
    tasks.append(task)


def build_tasks_from_stage1_qa1(
    df_stage1: pd.DataFrame,
    stage1_qa1_report: Optional[Path],
    cfg: EvidenceVerifierConfig,
) -> List[Dict[str, Any]]:
    tasks: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str, str, str]] = set()

    queue = read_excel_sheet_if_exists(stage1_qa1_report, "LLM_Human_Review_Queue")
    summary = read_excel_sheet_if_exists(stage1_qa1_report, "GSE_Field_Summary")

    # Use explicit Stage1 QA1 queue first.
    if not queue.empty:
        for _, r in queue.iterrows():
            gse_id = clean_value(r.get("GSE_ID", ""))
            field = clean_value(r.get("Field", ""))
            if not gse_id or field not in HIGH_IMPACT_FIELDS:
                continue

            issue_type = clean_value(r.get("Issue_Type", ""))
            priority = clean_value(r.get("Review_Priority", ""))
            task_type = infer_task_type_from_stage1_qa1(issue_type, priority, field)

            # Whole-GSE missing and ambiguous partial/conflict issues are the main Stage1 QA3 targets.
            keep = False
            if task_type == "whole_gse_missing_field" and field in WHOLE_GSE_REANNOTATION_FIELDS:
                keep = True
            elif task_type in {"partial_missing_targeted_rescue", "mixed_design_or_case_control_review", "within_gse_conflict_review"}:
                keep = True
            elif "High" in priority:
                keep = True

            if not keep:
                continue

            example_missing = split_gsm_list(r.get("Example_Missing_GSMs", ""))
            add_task(
                tasks,
                {
                    "Task_Source": "Stage1 QA1",
                    "Task_Type": task_type,
                    "GSE_ID": gse_id,
                    "GSM_ID": "",
                    "Target_Field": field,
                    "Issue_Type": issue_type,
                    "Severity": "High" if "High" in priority else "Medium",
                    "Review_Priority": priority,
                    "Current_Value": "",
                    "Suggested_Value_From_Rule": clean_value(r.get("Dominant_Value", "")),
                    "Example_Missing_GSMs": " | ".join(example_missing),
                    "Issue_Row_JSON": json.dumps({k: clean_value(v) for k, v in r.to_dict().items()}, ensure_ascii=False),
                },
                seen,
            )

    # If a Stage1 QA1 report is unavailable or incomplete, independently add whole-GSE missing tasks.
    if summary.empty:
        work = df_stage1.copy()
        rows = []
        for gse_id, gse_df in work.groupby(cfg.gse_col, dropna=False):
            for field in WHOLE_GSE_REANNOTATION_FIELDS:
                if field not in gse_df.columns:
                    continue
                n_total = int(gse_df.shape[0])
                n_missing = int(gse_df[field].map(is_missing).sum())
                if n_total > 0 and n_missing == n_total:
                    rows.append({
                        "GSE_ID": gse_id,
                        "Field": field,
                        "Issue_Type": "Whole-GSE Missing",
                        "Review_Priority": "High - Targeted Re-annotation",
                        "N_Total": n_total,
                        "N_Missing": n_missing,
                    })
        summary = pd.DataFrame(rows)

    if not summary.empty:
        for _, r in summary.iterrows():
            field = clean_value(r.get("Field", ""))
            gse_id = clean_value(r.get("GSE_ID", ""))
            issue_type = clean_value(r.get("Issue_Type", ""))
            if field not in WHOLE_GSE_REANNOTATION_FIELDS:
                continue
            if issue_type != "Whole-GSE Missing":
                continue
            add_task(
                tasks,
                {
                    "Task_Source": "Stage1 QA1_Summary",
                    "Task_Type": "whole_gse_missing_field",
                    "GSE_ID": gse_id,
                    "GSM_ID": "",
                    "Target_Field": field,
                    "Issue_Type": issue_type,
                    "Severity": "High",
                    "Review_Priority": clean_value(r.get("Review_Priority", "High - Targeted Re-annotation")),
                    "Current_Value": "<all missing>",
                    "Suggested_Value_From_Rule": clean_value(r.get("Dominant_Value", "")),
                    "Example_Missing_GSMs": clean_value(r.get("Example_Missing_GSMs", "")),
                    "Issue_Row_JSON": json.dumps({k: clean_value(v) for k, v in r.to_dict().items()}, ensure_ascii=False),
                },
                seen,
            )

    return tasks


def build_tasks_from_stage1_qa2(
    stage1_qa2_report: Optional[Path],
    cfg: EvidenceVerifierConfig,
) -> List[Dict[str, Any]]:
    tasks: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str, str, str]] = set()
    issues = read_excel_sheet_if_exists(stage1_qa2_report, "Cross_Agent_Issues")
    if issues.empty:
        return tasks

    allowed_sev = {"High"}
    if cfg.include_stage1_qa2_medium:
        allowed_sev.add("Medium")
    if cfg.include_stage1_qa2_low:
        allowed_sev.add("Low")

    for _, r in issues.iterrows():
        severity = clean_value(r.get("Severity", ""))
        needs_llm = clean_value(r.get("Needs_LLM_Review", "")).upper() == "YES"
        needs_human = clean_value(r.get("Needs_Human_Review", "")).upper() == "YES"
        if severity not in allowed_sev and not needs_llm and not needs_human:
            continue

        suggested_field = clean_value(r.get("Suggested_Field", ""))
        fields_involved = [x.strip() for x in clean_value(r.get("Fields_Involved", "")).split(";") if x.strip()]
        target_field = suggested_field if suggested_field else (fields_involved[0] if fields_involved else "")
        if target_field and target_field not in HIGH_IMPACT_FIELDS:
            # Keep conflicts that involve high-impact fields even if suggested_field is generic.
            if not any(f in HIGH_IMPACT_FIELDS for f in fields_involved):
                continue
            target_field = next((f for f in fields_involved if f in HIGH_IMPACT_FIELDS), target_field)

        add_task(
            tasks,
            {
                "Task_Source": "Stage1 QA2",
                "Task_Type": "cross_agent_conflict_verification",
                "GSE_ID": clean_value(r.get("GSE_ID", "")),
                "GSM_ID": clean_value(r.get("GSM_ID", "")),
                "Target_Field": target_field,
                "Issue_Type": clean_value(r.get("Issue_Type", "Cross-agent conflict")),
                "Severity": severity or "Medium",
                "Review_Priority": "Cross-agent validation",
                "Current_Value": "",
                "Suggested_Value_From_Rule": clean_value(r.get("Suggested_Value", "")),
                "Example_Missing_GSMs": "",
                "Rule_ID": clean_value(r.get("Rule_ID", "")),
                "Rule_Name": clean_value(r.get("Rule_Name", "")),
                "Fields_Involved": "; ".join(fields_involved),
                "Issue_Row_JSON": json.dumps({k: clean_value(v) for k, v in r.to_dict().items()}, ensure_ascii=False),
            },
            seen,
        )

    return tasks


def build_sampling_qc_tasks(
    df_stage1: pd.DataFrame,
    existing_tasks: List[Dict[str, Any]],
    cfg: EvidenceVerifierConfig,
) -> List[Dict[str, Any]]:
    """Small risk-based evidence check for high-impact fields even if not flagged."""
    if not cfg.include_sampling_qc:
        return []

    existing_keys = {(t.get("GSE_ID", ""), t.get("Target_Field", "")) for t in existing_tasks}
    tasks: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str, str, str]] = set()

    for gse_id, gse_df in df_stage1.groupby(cfg.gse_col, dropna=False):
        added = 0
        for field in cfg.fields_for_sampling_qc:
            if added >= cfg.max_sampling_qc_tasks_per_gse:
                break
            if field not in gse_df.columns:
                continue
            if (clean_value(gse_id), field) in existing_keys:
                continue

            vals = gse_df[field]
            n = int(gse_df.shape[0])
            missing_count = int(vals.map(is_missing).sum())
            vc = vals[~vals.map(is_missing)].map(clean_value).value_counts(dropna=False)
            unique_nonmissing = int(vc.shape[0])
            # Trigger only if there is some risk signal: missingness or heterogeneity in high-impact field.
            if missing_count == 0 and unique_nonmissing <= 1:
                continue

            severity = "Medium" if missing_count > 0 else "Low"
            add_task(
                tasks,
                {
                    "Task_Source": "Sampling_QC",
                    "Task_Type": "evidence_support_sampling_qc",
                    "GSE_ID": clean_value(gse_id),
                    "GSM_ID": "",
                    "Target_Field": field,
                    "Issue_Type": "Risk-triggered evidence support check",
                    "Severity": severity,
                    "Review_Priority": "Sampling QC",
                    "Current_Value": "",
                    "Suggested_Value_From_Rule": "",
                    "Example_Missing_GSMs": "",
                    "Issue_Row_JSON": json.dumps({
                        "GSE_ID": clean_value(gse_id),
                        "Field": field,
                        "N_Total": n,
                        "N_Missing": missing_count,
                        "Unique_NonMissing_Values": unique_nonmissing,
                        "Distribution": {str(k): int(v) for k, v in vc.items()},
                    }, ensure_ascii=False),
                },
                seen,
            )
            added += 1

    return tasks

def _qa3_mode_normalized(mode: Any) -> str:
    mode = clean_value(mode).lower()
    return mode if mode in QA3_VALID_MODES else "smart"


def _qa3_default_max_tasks_for_mode(mode: str) -> int:
    mode = _qa3_mode_normalized(mode)
    if mode == "full":
        return QA3_FULL_DEFAULT_MAX_TASKS
    if mode == "off":
        return 0
    return QA3_SMART_DEFAULT_MAX_TASKS


def _qa3_task_priority_score(row: pd.Series) -> int:
    """
    Higher score = more valuable QA3 LLM task.

    Smart mode should spend LLM calls on issues that are likely to improve
    final biological/release quality.
    """
    field = clean_value(row.get("Target_Field", ""))
    task_type = clean_value(row.get("Task_Type", ""))
    severity = clean_value(row.get("Severity", ""))

    score = 0

    if severity == "High":
        score += 40
    elif severity == "Medium":
        score += 20
    elif severity == "Low":
        score += 5

    field_weights = {
        "Disease": 100,
        "Tissue": 85,
        "RNA_Source": 70,
        "GSE_Pert": 70,
        "GSM_Pert": 70,
        "Pert": 65,
        "SampleType": 60,
        "Specimen_Type": 60,
        "Seq_Type": 50,
        "Organism": 45,
        "Experimental_Setting": 45,
        "Model_Type": 45,
        "RNA_Library": 15,
        "Pert_Dose": 10,
        "Pert_Freq": 10,
        "Pert_Duration": 10,
        "Route_Admin": 10,
    }
    score += field_weights.get(field, 0)

    task_weights = {
        "partial_missing_targeted_rescue": 45,
        "mixed_design_or_case_control_review": 45,
        "cross_agent_conflict_verification": 35,
        "within_gse_conflict_review": 30,
        "whole_gse_missing_field": 20,
        "evidence_support_sampling_qc": -20,
    }
    score += task_weights.get(task_type, 0)

    # Whole-GSE RNA_Library and treatment detail missingness are usually low yield
    # unless explicit evidence is already present. Do not spend routine QA3 budget there.
    if field in QA3_SMART_LOW_YIELD_FIELDS:
        score -= 70

    if field == "RNA_Library" and task_type == "whole_gse_missing_field":
        score -= 40

    return int(score)


def apply_qa3_mode_policy(tasks_df: pd.DataFrame, cfg: EvidenceVerifierConfig) -> pd.DataFrame:
    """
    Apply off/smart/full task-selection policy before LLM calls.

    off   = no QA3 LLM tasks.
    smart = prioritized high-value tasks only.
    full  = broad QA3 task list, capped by max_tasks.
    """
    mode = _qa3_mode_normalized(cfg.qa3_mode)

    if tasks_df is None or tasks_df.empty:
        return pd.DataFrame(columns=[] if tasks_df is None else tasks_df.columns)

    tasks_df = tasks_df.copy()

    if mode == "off":
        return tasks_df.head(0).copy()

    max_tasks = cfg.max_tasks
    if max_tasks is None:
        max_tasks = _qa3_default_max_tasks_for_mode(mode)

    if mode == "smart":
        tasks_df["_QA3_Smart_Score"] = tasks_df.apply(_qa3_task_priority_score, axis=1)

        # Keep high-value candidates. This threshold keeps Disease/Tissue/Perturbation
        # issues and drops most low-yield missing dose/duration/frequency/route tasks.
        tasks_df = tasks_df.loc[tasks_df["_QA3_Smart_Score"] >= 50].copy()

        tasks_df = tasks_df.sort_values(
            ["_QA3_Smart_Score", "Severity", "GSE_ID", "GSM_ID", "Target_Field"],
            ascending=[False, True, True, True, True],
            kind="stable",
        )

        tasks_df = tasks_df.drop(columns=["_QA3_Smart_Score"])

    # full mode uses the existing ordered task list.
    if max_tasks is not None:
        max_tasks = int(max_tasks)

        if max_tasks <= 0:
            return tasks_df.head(0).copy()

        tasks_df = tasks_df.head(max_tasks).reset_index(drop=True)

    tasks_df["Task_ID"] = [f"EV{i + 1:07d}" for i in range(tasks_df.shape[0])]
    return tasks_df

def build_verification_tasks(
    df_stage1: pd.DataFrame,
    stage1_qa1_report: Optional[Path],
    stage1_qa2_report: Optional[Path],
    cfg: EvidenceVerifierConfig,
) -> pd.DataFrame:
    df_stage1 = ensure_id_cols(df_stage1, cfg)

    tasks: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str, str, str]] = set()

    for task in build_tasks_from_stage1_qa1(df_stage1, stage1_qa1_report, cfg):
        add_task(tasks, task, seen)
    for task in build_tasks_from_stage1_qa2(stage1_qa2_report, cfg):
        add_task(tasks, task, seen)
    for task in build_sampling_qc_tasks(df_stage1, tasks, cfg):
        add_task(tasks, task, seen)

    priority = {
        "whole_gse_missing_field": 1,
        "partial_missing_targeted_rescue": 2,
        "mixed_design_or_case_control_review": 3,
        "cross_agent_conflict_verification": 4,
        "within_gse_conflict_review": 5,
        "evidence_support_sampling_qc": 6,
    }
    tasks_df = pd.DataFrame(tasks)
    if tasks_df.empty:
        return pd.DataFrame(columns=[
            "Task_ID", "Task_Source", "Task_Type", "GSE_ID", "GSM_ID", "Target_Field",
            "Issue_Type", "Severity", "Review_Priority", "Current_Value",
            "Suggested_Value_From_Rule", "Example_Missing_GSMs", "Issue_Row_JSON",
        ])

    tasks_df["_sort"] = tasks_df["Task_Type"].map(priority).fillna(99)
    tasks_df = tasks_df.sort_values(
        ["_sort", "Severity", "GSE_ID", "GSM_ID", "Target_Field"],
        kind="stable",
    ).drop(columns=["_sort"])

    tasks_df = apply_qa3_mode_policy(tasks_df, cfg)
    return tasks_df


# -----------------------------------------------------------------------------
# Evidence packet builder
# -----------------------------------------------------------------------------

def selected_rows_for_task(gse_df: pd.DataFrame, task: Dict[str, Any], cfg: EvidenceVerifierConfig) -> pd.DataFrame:
    field = clean_value(task.get("Target_Field", ""))
    gsm_id = clean_value(task.get("GSM_ID", ""))
    task_type = clean_value(task.get("Task_Type", ""))

    pieces = []

    if gsm_id and cfg.gsm_col in gse_df.columns:
        row_df = gse_df[gse_df[cfg.gsm_col].astype(str).str.strip() == gsm_id]
        if not row_df.empty:
            pieces.append(row_df)

    missing_gsms = split_gsm_list(task.get("Example_Missing_GSMs", ""))
    if missing_gsms:
        miss_df = gse_df[gse_df[cfg.gsm_col].astype(str).isin(missing_gsms)]
        if not miss_df.empty:
            pieces.append(miss_df)

    if field in gse_df.columns:
        missing_df = gse_df[gse_df[field].map(is_missing)].head(cfg.max_same_gse_examples // 2)
        nonmissing_df = gse_df[~gse_df[field].map(is_missing)].head(cfg.max_same_gse_examples // 2)
        if task_type in {"whole_gse_missing_field", "evidence_support_sampling_qc"}:
            pieces.append(gse_df.head(cfg.max_same_gse_examples))
        else:
            pieces.extend([missing_df, nonmissing_df])
    else:
        pieces.append(gse_df.head(cfg.max_same_gse_examples))

    if not pieces:
        return gse_df.head(cfg.max_same_gse_examples)

    selected = pd.concat(pieces, axis=0).drop_duplicates(subset=[cfg.gsm_col], keep="first")
    return selected.head(cfg.max_same_gse_examples)


def build_evidence_packet(
    df_stage1: pd.DataFrame,
    task: Dict[str, Any],
    cfg: EvidenceVerifierConfig,
) -> Dict[str, Any]:
    gse_id = clean_value(task.get("GSE_ID", ""))
    target_field = clean_value(task.get("Target_Field", ""))
    gse_df = df_stage1[df_stage1[cfg.gse_col].astype(str).str.strip() == gse_id].copy()

    if gse_df.empty:
        return {"task": task, "error": f"No rows found for GSE_ID={gse_id}"}

    selected = selected_rows_for_task(gse_df, task, cfg)

    gse_info = ""
    if "GSE_Info" in gse_df.columns:
        nonempty = [clean_value(x) for x in gse_df["GSE_Info"].tolist() if clean_value(x)]
        gse_info = nonempty[0] if nonempty else ""

    packet_fields = [cfg.gsm_col]
    for c in [
        "GSE_ID", "GSM_ID", "Title", "Sample_Title", "Source_Name", "Source Name",
        "GSM_Info",
    ] + DESIGN_FIELDS:
        if c in selected.columns and c not in packet_fields:
            packet_fields.append(c)

    sample_records: List[Dict[str, Any]] = []
    for _, row in selected.iterrows():
        rec: Dict[str, Any] = {}
        for c in packet_fields:
            val = clean_value(row.get(c, ""))
            if c == "GSM_Info":
                val = truncate_text(val, cfg.max_gsm_info_chars)
            rec[c] = val
        sample_records.append(rec)

    missing_gsm_ids: List[str] = []
    affected_current_values: Dict[str, str] = {}
    if target_field in gse_df.columns:
        missing_mask = gse_df[target_field].map(is_missing)
        missing_gsm_ids = gse_df.loc[missing_mask, cfg.gsm_col].astype(str).head(cfg.max_missing_gsm_ids_in_packet).tolist()
        affected_current_values = {
            str(row[cfg.gsm_col]): clean_value(row[target_field])
            for _, row in gse_df[[cfg.gsm_col, target_field]].iterrows()
            if (not clean_value(task.get("GSM_ID", "")) or str(row[cfg.gsm_col]) == clean_value(task.get("GSM_ID", "")))
        }

    distributions = value_distribution(gse_df, [c for c in DESIGN_FIELDS if c in gse_df.columns])
    design_signatures = make_design_signatures(gse_df, cfg)

    return {
        "task": task,
        "instructions": {
            "review_goal": "Verify the target annotation against source GEO evidence and current annotations.",
            "do_not_force_uniformity": True,
            "allowed_decisions": ["Fill All", "Fill Subset", "Correct Field", "Do Not Change", "Need Human Review"],
            "safety_policy": "Prefer Need Human Review when evidence is ambiguous or multiple biologically plausible assignments exist.",
        },
        "gse_id": gse_id,
        "target_field": target_field,
        "gse_size": int(gse_df.shape[0]),
        "gse_info": truncate_text(gse_info, cfg.max_gse_info_chars),
        "same_gse_field_distributions": distributions,
        "design_signature_summary": design_signatures,
        "missing_gsm_ids_for_target_field": missing_gsm_ids,
        "affected_current_values": affected_current_values,
        "sample_records": sample_records,
    }


# -----------------------------------------------------------------------------
# LLM structured reviewer
# -----------------------------------------------------------------------------

REVIEW_SYSTEM_PROMPT = """You are a conservative GEOMeta evidence-grounded verification reviewer.

You are not the initial annotator. Your job is to verify a flagged Stage 1 field using source GEO evidence.

You will receive:
- a single targeted task,
- GSE_Info and representative GSM_Info records,
- current annotations for related fields,
- same-GSE value distributions,
- a design signature summary.

Allowed decisions:
- Fill All: fill the target field for all currently missing GSMs in this GSE.
- Fill Subset: fill the target field only for listed GSMs.
- Correct Field: correct one target field for one/few listed GSMs if the current value is unsupported.
- Do Not Change: current missing/annotation state is appropriate or evidence is insufficient.
- Need Human Review: multiple biologically plausible values exist or evidence is unclear.

Rules:
1. Do not force all GSMs in the same GSE to have the same value. Disease, tissue, perturbation, dose, timepoint, sex, genotype, and sample type may truly vary.
2. For case/control studies, assign Disease only from sample-specific evidence when possible. Do not majority-fill Disease.
3. For multi-tissue or multi-perturbation designs, identify subgroups and avoid global propagation.
4. Use exact evidence from GSE_Info/GSM_Info/Title/Source/Characteristics when available. Evidence can be short excerpts or concise paraphrases.
5. If evidence supports a value only at study level, use Fill All only for study-level or protocol-level fields such as Organism, Seq_Type, RNA_Library, Experimental_Setting, Model_Type, or GSE_Pert.
6. Do not invent labels not supported by the evidence.
7. Prefer Need Human Review when the evidence is ambiguous.
8. Return strict JSON only. No markdown. No extra text."""

REVIEW_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["Fill All", "Fill Subset", "Correct Field", "Do Not Change", "Need Human Review"],
        },
        "target_field": {"type": "string"},
        "suggested_value": {"type": "string"},
        "affected_gsm_ids": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string"},
        "design_assessment": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "design_type": {
                    "type": "string",
                    "enum": [
                        "single_context",
                        "case_control",
                        "multi_tissue",
                        "multi_perturbation",
                        "multi_timepoint",
                        "mixed_complex",
                        "unclear",
                    ],
                },
                "subgroup_summary": {"type": "string"},
            },
            "required": ["design_type", "subgroup_summary"],
        },
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "source": {"type": "string"},
                    "text": {"type": "string"},
                    "supports": {"type": "string"},
                },
                "required": ["source", "text", "supports"],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "decision",
        "target_field",
        "suggested_value",
        "affected_gsm_ids",
        "confidence",
        "reason",
        "design_assessment",
        "evidence",
        "warnings",
    ],
}


def make_openai_client_from_env_or_cfg(cfg_obj: Any = None) -> Tuple[Any, str]:
    """Return an OpenAI-compatible client and model/deployment name."""
    from openai import AzureOpenAI, OpenAI

    # Azure variables remain supported for local users.
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    azure_api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")

    if azure_endpoint and azure_key and azure_deployment:
        return AzureOpenAI(api_key=azure_key, azure_endpoint=azure_endpoint, api_version=azure_api_version), azure_deployment

    if cfg_obj is not None:
        api_key = clean_value(getattr(cfg_obj, "llm_api_key", ""))
        base_url = clean_value(getattr(cfg_obj, "llm_base_url", ""))
        model = clean_value(getattr(cfg_obj, "llm_model", ""))
        if api_key and base_url and model:
            return OpenAI(api_key=api_key, base_url=base_url), model

    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-5"

    if api_key:
        return OpenAI(api_key=api_key, base_url=base_url), model

    raise RuntimeError("No LLM credentials found. Set LLM_API_KEY/OPENAI_API_KEY or Azure OpenAI variables.")


def call_llm_review(client: Any, model_or_deployment: str, packet: Dict[str, Any], cfg_obj: Any | None = None) -> Dict[str, Any]:
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "geometa_stage1_qa3_evidence_verification",
            "strict": True,
            "schema": REVIEW_SCHEMA,
        },
    }

    messages = [
        {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(packet, ensure_ascii=False, indent=2)},
    ]

    budget = TokenBudget.from_config(cfg_obj)
    check_messages_token_budget(
        messages,
        budget=budget,
        context_label=f"Stage1 QA3 evidence verifier task={packet.get('Task_ID', '')}",
        action=str(getattr(cfg_obj, "llm_token_budget_action", "raise")) if cfg_obj is not None else "raise",
    )

    request = {
        "model": model_or_deployment,
        "messages": messages,
        "response_format": response_format,
    }

    # Do not pass temperature. Some GPT-5/Azure-compatible deployments only support the default.
    resp = client.chat.completions.create(**request)
    return json.loads(resp.choices[0].message.content)


# -----------------------------------------------------------------------------
# Applying accepted recommendations
# -----------------------------------------------------------------------------

def normalize_decision(x: Any) -> str:
    return clean_value(x)


def recommendation_to_rows(rec: Dict[str, Any], task: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(task)
    out.update({
        "Decision": clean_value(rec.get("decision", "Need Human Review")),
        "LLM_Target_Field": clean_value(rec.get("target_field", task.get("Target_Field", ""))),
        "LLM_Suggested_Value": clean_value(rec.get("suggested_value", "")),
        "LLM_Affected_GSM_IDs": " | ".join([clean_value(x) for x in rec.get("affected_gsm_ids", []) if clean_value(x)]),
        "LLM_Confidence": rec.get("confidence", ""),
        "LLM_Reason": clean_value(rec.get("reason", "")),
        "LLM_Design_Type": clean_value(rec.get("design_assessment", {}).get("design_type", "")) if isinstance(rec.get("design_assessment", {}), dict) else "",
        "LLM_Subgroup_Summary": clean_value(rec.get("design_assessment", {}).get("subgroup_summary", "")) if isinstance(rec.get("design_assessment", {}), dict) else "",
        "LLM_Evidence_JSON": json.dumps(rec.get("evidence", []), ensure_ascii=False),
        "LLM_Warnings_JSON": json.dumps(rec.get("warnings", []), ensure_ascii=False),
        "LLM_Raw_JSON": json.dumps(rec, ensure_ascii=False),
        "LLM_Status": "OK",
        "LLM_Error": "",
    })
    return out


def should_apply_recommendation(row: Dict[str, Any], cfg: EvidenceVerifierConfig) -> Tuple[bool, str]:
    decision = normalize_decision(row.get("Decision", ""))
    if decision not in {"Fill All", "Fill Subset", "Correct Field"}:
        return False, f"Decision is {decision}; no automatic correction."

    try:
        confidence = float(row.get("LLM_Confidence", 0))
    except Exception:
        confidence = 0.0
    if confidence < cfg.min_confidence_to_apply:
        return False, f"Confidence {confidence:.3f} below threshold {cfg.min_confidence_to_apply:.3f}."

    suggested = clean_value(row.get("LLM_Suggested_Value", ""))
    if is_missing(suggested):
        return False, "Suggested value is missing/NA."

    evidence = safe_json_loads(row.get("LLM_Evidence_JSON", ""))
    if not isinstance(evidence, list) or len(evidence) == 0:
        return False, "No evidence items returned."

    return True, "Accepted by Stage1 QA3 high-confidence evidence-grounded rule."


def apply_stage1_qa3_recommendations(
    df_stage1: pd.DataFrame,
    recommendations_df: pd.DataFrame,
    cfg: EvidenceVerifierConfig,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    corrected = df_stage1.copy()
    corrected = ensure_id_cols(corrected, cfg)

    if recommendations_df.empty:
        empty_cols = [
            "Task_ID", "GSE_ID", "GSM_ID", "Field", "Old_Value", "New_Value",
            "Decision", "Apply_Status", "Apply_Reason",
        ]
        return corrected, pd.DataFrame(columns=empty_cols), pd.DataFrame(), recommendations_df

    applied_rows: List[Dict[str, Any]] = []
    accepted_rows: List[Dict[str, Any]] = []
    human_rows: List[Dict[str, Any]] = []

    for _, rr in recommendations_df.iterrows():
        row = {k: rr.get(k, "") for k in recommendations_df.columns}
        ok, reason = should_apply_recommendation(row, cfg)
        decision = normalize_decision(row.get("Decision", ""))
        field = clean_value(row.get("LLM_Target_Field", row.get("Target_Field", "")))
        gse_id = clean_value(row.get("GSE_ID", ""))
        suggested = clean_value(row.get("LLM_Suggested_Value", ""))

        if not ok or field not in corrected.columns:
            row["Apply_Status"] = "Human Review" if decision == "Need Human Review" or not ok else "Rejected"
            row["Apply_Reason"] = reason if field in corrected.columns else f"Field not found in Stage1 table: {field}"
            human_rows.append(row)
            continue

        affected_gsms = split_gsm_list(row.get("LLM_Affected_GSM_IDs", ""))
        if decision == "Fill All":
            gse_mask = corrected[cfg.gse_col].astype(str).str.strip().eq(gse_id)
            affected_gsms = corrected.loc[gse_mask & corrected[field].map(is_missing), cfg.gsm_col].astype(str).tolist()
        elif decision == "Fill Subset":
            # If the LLM did not list IDs, fall back to task missing examples only.
            if not affected_gsms:
                affected_gsms = split_gsm_list(row.get("Example_Missing_GSMs", ""))
        elif decision == "Correct Field":
            if not affected_gsms:
                gsm_id = clean_value(row.get("GSM_ID", ""))
                affected_gsms = [gsm_id] if gsm_id else []

        if not affected_gsms:
            row["Apply_Status"] = "Human Review"
            row["Apply_Reason"] = "No affected GSM_IDs available."
            human_rows.append(row)
            continue

        applied_any = False
        for gsm_id in affected_gsms:
            idx = corrected.index[
                corrected[cfg.gse_col].astype(str).str.strip().eq(gse_id)
                & corrected[cfg.gsm_col].astype(str).str.strip().eq(gsm_id)
            ]
            if len(idx) == 0:
                continue
            i = idx[0]
            old = clean_value(corrected.at[i, field])

            if not is_missing(old) and not cfg.allow_nonempty_overwrite:
                applied_rows.append({
                    "Task_ID": row.get("Task_ID", ""),
                    "GSE_ID": gse_id,
                    "GSM_ID": gsm_id,
                    "Field": field,
                    "Old_Value": old,
                    "New_Value": suggested,
                    "Decision": decision,
                    "Apply_Status": "Not Applied",
                    "Apply_Reason": "Existing non-empty value; non-empty overwrite disabled.",
                })
                continue

            corrected.at[i, field] = suggested
            applied_any = True
            applied_rows.append({
                "Task_ID": row.get("Task_ID", ""),
                "GSE_ID": gse_id,
                "GSM_ID": gsm_id,
                "Field": field,
                "Old_Value": old,
                "New_Value": suggested,
                "Decision": decision,
                "Apply_Status": "Applied",
                "Apply_Reason": reason,
            })

        row["Apply_Status"] = "Applied" if applied_any else "Human Review"
        row["Apply_Reason"] = reason if applied_any else "No cells were applied; likely non-empty overwrite or unmatched GSM IDs."
        if applied_any:
            accepted_rows.append(row)
        else:
            human_rows.append(row)

    return (
        corrected,
        pd.DataFrame(applied_rows),
        pd.DataFrame(accepted_rows),
        pd.DataFrame(human_rows),
    )


# -----------------------------------------------------------------------------
# Main pipeline callable
# -----------------------------------------------------------------------------

def _qa3_print_progress(
    *,
    done_tasks: int,
    total_tasks: int,
    recommendations: List[Dict[str, Any]],
    start_time: float,
) -> None:
    elapsed = time.perf_counter() - start_time
    pct = (done_tasks / total_tasks * 100.0) if total_tasks else 100.0
    avg = elapsed / done_tasks if done_tasks else 0.0
    eta = avg * max(total_tasks - done_tasks, 0)

    def fmt(seconds: float) -> str:
        seconds = max(float(seconds), 0.0)
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"

    accepted_like = 0
    human_like = 0
    no_change_like = 0

    for r in recommendations:
        decision = clean_value(r.get("Decision", ""))
        if decision in {"Fill All", "Fill Subset", "Correct Field"}:
            accepted_like += 1
        elif decision == "Do Not Change":
            no_change_like += 1
        else:
            human_like += 1

    print(
        "[Stage1 QA3 progress] "
        f"tasks={done_tasks:,}/{total_tasks:,} ({pct:.1f}%); "
        f"accepted_like={accepted_like:,}; "
        f"human_review_like={human_like:,}; "
        f"no_change={no_change_like:,}; "
        f"elapsed={fmt(elapsed)}; "
        f"avg={avg:.1f}s/task; "
        f"ETA={fmt(eta)}",
        flush=True,
    )

def run_stage1_qa3_verification_pipeline(
    df_stage1: pd.DataFrame,
    stage1_qa1_report: Optional[Path],
    stage1_qa2_report: Optional[Path],
    output_dir: Path,
    run_version: str,
    verifier_config: Optional[EvidenceVerifierConfig] = None,
    cfg_pipeline: Any = None,
) -> Tuple[pd.DataFrame, Dict[str, Path]]:
    cfg = verifier_config or EvidenceVerifierConfig()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    debug_dir = output_dir.parent / "debug" / "stage1_qa3" / run_version
    debug_dir.mkdir(parents=True, exist_ok=True)

    df_stage1 = ensure_id_cols(df_stage1, cfg)

    tasks_df = build_verification_tasks(df_stage1, stage1_qa1_report, stage1_qa2_report, cfg)
    tasks_path = output_dir / f"{run_version}_stage1_qa3_evidence_verification_tasks.xlsx"
    tasks_df.to_excel(tasks_path, index=False)

    packets: List[Dict[str, Any]] = []
    recommendations: List[Dict[str, Any]] = []

    if cfg.build_tasks_only or tasks_df.empty:
        corrected = df_stage1.copy()
        rec_df = pd.DataFrame()
        applied_df = pd.DataFrame()
        accepted_df = pd.DataFrame()
        human_df = tasks_df.copy()
        if not human_df.empty:
            human_df["Apply_Status"] = "Not Reviewed"
            human_df["Apply_Reason"] = "Stage1 QA3 was run in build-tasks-only mode."
    else:
        client, model = make_openai_client_from_env_or_cfg(cfg_pipeline)
        qa3_progress_start = time.perf_counter()
        total_tasks = int(tasks_df.shape[0])

        print(
            "[Stage1 QA3] Starting evidence-grounded LLM verification "
            f"for {total_tasks:,} task(s); mode={_qa3_mode_normalized(cfg.qa3_mode)}; "
            f"min_confidence_to_apply={cfg.min_confidence_to_apply:.2f}; "
            f"apply_accepted={cfg.apply_accepted}; "
            f"allow_nonempty_overwrite={cfg.allow_nonempty_overwrite}.",
            flush=True,
        )

        for idx, (_, task_row) in enumerate(tasks_df.iterrows(), start=1):
            task = {k: clean_value(v) for k, v in task_row.to_dict().items()}
            packet = build_evidence_packet(df_stage1, task, cfg)
            packets.append(packet)

            packet_path = debug_dir / f"{task.get('Task_ID', f'EV{idx:07d}')}_packet.json"
            packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")

            try:
                rec = call_llm_review(client, model, packet, cfg_obj=cfg_pipeline)
                out_row = recommendation_to_rows(rec, task)
            except Exception as e:
                out_row = dict(task)
                out_row.update({
                    "Decision": "Need Human Review",
                    "LLM_Target_Field": task.get("Target_Field", ""),
                    "LLM_Suggested_Value": "",
                    "LLM_Affected_GSM_IDs": "",
                    "LLM_Confidence": 0,
                    "LLM_Reason": "LLM review failed; routed to human review.",
                    "LLM_Design_Type": "unclear",
                    "LLM_Subgroup_Summary": "",
                    "LLM_Evidence_JSON": "[]",
                    "LLM_Warnings_JSON": json.dumps([str(e)], ensure_ascii=False),
                    "LLM_Raw_JSON": "{}",
                    "LLM_Status": "ERROR",
                    "LLM_Error": str(e),
                })
            recommendations.append(out_row)
            if cfg.sleep_between_calls:
                time.sleep(float(cfg.sleep_between_calls))

            _qa3_print_progress(
                done_tasks=idx,
                total_tasks=total_tasks,
                recommendations=recommendations,
                start_time=qa3_progress_start,
            )

        rec_df = pd.DataFrame(recommendations)
        # Apply only if enabled. Otherwise, keep recommendations as review-only.
        if cfg.apply_accepted:
            corrected, applied_df, accepted_df, human_df = apply_stage1_qa3_recommendations(df_stage1, rec_df, cfg)
        else:
            corrected = df_stage1.copy()
            applied_df = pd.DataFrame()
            accepted_df = pd.DataFrame()
            human_df = rec_df.copy()
            if not human_df.empty:
                human_df["Apply_Status"] = "Not Applied"
                human_df["Apply_Reason"] = "Stage1 QA3 automatic application disabled."

    # Mode A: do not block on human-review cases. Add explicit row-level
    # provenance/review flags and continue with corrected output.
    corrected = add_stage1_qa3_mode_a_flags(
        corrected,
        applied_df=applied_df,
        human_df=human_df,
        gse_col=cfg.gse_col,
        gsm_col=cfg.gsm_col,
    )

    corrected_path = output_dir / f"{run_version}_stage1_qa3_corrected_targeted.xlsx"
    recommendations_path = output_dir / f"{run_version}_stage1_qa3_llm_recommendations.xlsx"
    applied_path = output_dir / f"{run_version}_stage1_qa3_applied_cell_changes.xlsx"
    human_path = output_dir / f"{run_version}_stage1_qa3_human_review_queue.xlsx"
    report_path = output_dir / f"{run_version}_stage1_qa3_evidence_verification_report.xlsx"
    packets_jsonl_path = debug_dir / f"{run_version}_stage1_qa3_evidence_packets.jsonl"

    corrected.to_excel(corrected_path, index=False)
    rec_df.to_excel(recommendations_path, index=False)
    applied_df.to_excel(applied_path, index=False)
    human_df.to_excel(human_path, index=False)

    with packets_jsonl_path.open("w", encoding="utf-8") as f:
        for packet in packets:
            f.write(json.dumps(packet, ensure_ascii=False) + "\n")

    summary = {
        "run_version": run_version,
        "n_tasks": int(tasks_df.shape[0]),
        "n_recommendations": int(rec_df.shape[0]) if not rec_df.empty else 0,
        "n_applied_cell_changes": int(applied_df.shape[0]) if not applied_df.empty else 0,
        "n_accepted_tasks": int(accepted_df.shape[0]) if not accepted_df.empty else 0,
        "n_human_review_tasks": int(human_df.shape[0]) if not human_df.empty else 0,
        "config": asdict(cfg),
    }
    summary_df = pd.DataFrame([summary])

    with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
        tasks_df.to_excel(writer, sheet_name="Verification_Tasks", index=False)
        rec_df.to_excel(writer, sheet_name="LLM_Recommendations", index=False)
        applied_df.to_excel(writer, sheet_name="Applied_Cell_Changes", index=False)
        accepted_df.to_excel(writer, sheet_name="Accepted_Task_Summary", index=False)
        human_df.to_excel(writer, sheet_name="Human_Review_Queue", index=False)
        summary_df.to_excel(writer, sheet_name="Summary", index=False)

    outputs = {
        "tasks": tasks_path,
        "corrected": corrected_path,
        "recommendations": recommendations_path,
        "applied_changes": applied_path,
        "human_review": human_path,
        "report": report_path,
        "packets_jsonl": packets_jsonl_path,
    }
    return corrected, outputs


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Run GEOMeta Stage 1 QA3 evidence-grounded verifier / targeted rescue")
    parser.add_argument("--stage1", required=True, help="Stage1/Stage1 QA1 corrected table with GSE_Info/GSM_Info attached")
    parser.add_argument(
        "--stage1-qa1-report",
        "--stage1-5-report",
        dest="stage1_qa1_report",
        default=None,
        help="Stage1 QA1 consistency report xlsx; --stage1-5-report is a backward-compatible alias.",
    )
    parser.add_argument(
        "--stage1-qa2-report",
        "--stage1-6-report",
        dest="stage1_qa2_report",
        default=None,
        help="Stage1 QA2 cross-agent validation report xlsx; --stage1-6-report is a backward-compatible alias.",
    )
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--run-version", required=True, help="Run version prefix")
    parser.add_argument("--gse-col", default="GSE_ID")
    parser.add_argument("--gsm-col", default="GSM_ID")
    parser.add_argument("--max-tasks", type=int, default=None)
    parser.add_argument(
        "--stage1-qa3-mode",
        "--qa3-mode",
        dest="stage1_qa3_mode",
        choices=["off", "smart", "full"],
        default="smart",
        help="QA3 mode: off skips QA3 tasks, smart runs prioritized tasks, full runs broad QA3.",
    )
    parser.add_argument("--min-confidence-to-apply", type=float, default=0.90)
    parser.add_argument("--build-tasks-only", action="store_true")
    parser.add_argument("--no-apply", action="store_true", help="Do not apply accepted recommendations; still save recommendations")
    parser.add_argument("--allow-nonempty-overwrite", action="store_true")
    parser.add_argument("--skip-sampling-qc", action="store_true")
    parser.add_argument(
        "--include-stage1-qa2-low",
        "--include-stage1-6-low",
        dest="include_stage1_qa2_low",
        action="store_true",
    )
    args = parser.parse_args()

    df_stage1 = read_table(Path(args.stage1))

    qa3_mode = args.stage1_qa3_mode

    if args.max_tasks is not None:
        qa3_max_tasks = args.max_tasks
    elif qa3_mode == "full":
        qa3_max_tasks = 150
    elif qa3_mode == "off":
        qa3_max_tasks = 0
    else:
        qa3_max_tasks = 50

    cfg = EvidenceVerifierConfig(
        gse_col=args.gse_col,
        gsm_col=args.gsm_col,
        qa3_mode=qa3_mode,
        max_tasks=qa3_max_tasks,
        min_confidence_to_apply=args.min_confidence_to_apply,
        build_tasks_only=args.build_tasks_only,
        apply_accepted=not args.no_apply,
        allow_nonempty_overwrite=args.allow_nonempty_overwrite,
        include_sampling_qc=(qa3_mode == "full") and not args.skip_sampling_qc,
        include_stage1_qa2_low=args.include_stage1_qa2_low,
    )

    corrected, outputs = run_stage1_qa3_verification_pipeline(
        df_stage1=df_stage1,
        stage1_qa1_report=Path(args.stage1_qa1_report) if args.stage1_qa1_report else None,
        stage1_qa2_report=Path(args.stage1_qa2_report) if args.stage1_qa2_report else None,
        output_dir=Path(args.output_dir),
        run_version=args.run_version,
        verifier_config=cfg,
        cfg_pipeline=None,
    )

    print("Stage 1 QA3 complete.")
    for k, v in outputs.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
