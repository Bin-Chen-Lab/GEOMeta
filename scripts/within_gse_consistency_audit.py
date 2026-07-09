#!/usr/bin/env python3
"""
Stage 1.5 within-GSE consistency audit and high-confidence correction.

Purpose
-------
Run immediately after Stage 1 LLM annotation and before Stage 2 post-processing.

This script:
1. Audits all Stage 1 fields within each GSE.
2. Detects partial missing values, inconsistent values, and whole-GSE missing fields.
3. Generates cell-level correction candidates.
4. Automatically accepts only high-confidence deterministic corrections:
   - blank-cell fills from unanimous same-GSE evidence for selected fields;
   - dedicated within-GSE rules such as GSM_Pert-derived GSE_Pert correction.
5. Routes ambiguous or biologically variable cases to review instead of force-correcting.
6. Produces a corrected Stage 1 file for downstream Stage 2 input.

Important design choices
------------------------
- Does NOT broadly overwrite non-empty annotations.
- Allows narrow deterministic non-empty correction only for explicit rule-backed cases,
  such as GSE_Pert derived from within-GSE GSM_Pert.
- Does NOT treat the literal string "NA" as blank by default, because "NA" may be a valid
  conservative annotation from Stage 1.
- Does NOT force all samples in a GSE to have the same value.
- Exports medium/ambiguous cases for LLM or human review.

Example
-------
python scripts/within_gse_consistency_audit.py \
  --input artifacts/outputs/geometa_full_RUN_stage1.xlsx \
  --output-dir artifacts/outputs \
  --run-version geometa_full_RUN
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


# -----------------------------------------------------------------------------
# Stage 1 field definitions
# -----------------------------------------------------------------------------

DEFAULT_STAGE1_FIELDS: List[str] = [
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

ID_FIELDS = {"GSM_ID", "GSE_ID"}

# These fields can often be propagated within a GSE when only a subset is blank,
# but only under strict evidence rules.
PROPAGATABLE_FIELDS = {
    "Seq_Type",
    "Organism",
    "RNA_Library",
    "RNA_Source",
    "Tissue",
    "Experimental_Setting",
    "Model_Type",
    "Disease",
    "SampleType",
    "Specimen_Type",
}

# These fields are biologically/experimentally likely to vary within a GSE.
# They should be audited but not auto-corrected.
REVIEW_ONLY_FIELDS = {
    "Strain",
    "Genotype",
    "GSE_Pert",
    "GSM_Pert",
    "Pert",
    "Pert_Dose",
    "Pert_Freq",
    "Pert_Duration",
    "Route_Admin",
    "Race",
    "Ethnicity",
    "Age",
    "Sex",
    "Timepoint",
    "Outcome",
}

# Fields handled by dedicated deterministic QA1 rules.
# These should still appear in the GSE_Field_Summary sheet, but they should not
# also generate generic missing-cell candidates/review rows because the dedicated
# rule below creates cleaner, rule-specific candidates and review items.
DEDICATED_QA1_RULE_FIELDS = {
    "GSE_Pert",
}

# Optional metadata fields that should never be corrected if present in files.
NEVER_CORRECT_FIELDS = {
    "GSE_Info",
    "GSM_Info",
    "Sample_Title",
    "Sample_Description",
    "Title",
    "Source_Name",
}

# Field-specific thresholds. Defaults below are intentionally conservative.
FIELD_THRESHOLDS: Dict[str, Dict[str, float]] = {
    # RNA_Library is commonly study/protocol-level, and the May 2026 file shows
    # many partial-missing cases. Allow higher missing percentage if all non-empty
    # values agree and at least five GSMs support the value.
    "RNA_Library": {
        "min_support": 5,
        "min_dominant_ratio": 1.00,
        "max_missing_pct": 0.50,
    },
    "Organism": {
        "min_support": 3,
        "min_dominant_ratio": 1.00,
        "max_missing_pct": 0.50,
    },
    "Seq_Type": {
        "min_support": 5,
        "min_dominant_ratio": 1.00,
        "max_missing_pct": 0.40,
    },
    "Experimental_Setting": {
        "min_support": 5,
        "min_dominant_ratio": 1.00,
        "max_missing_pct": 0.40,
    },
    # Disease/Tissue/RNA_Source/SampleType can genuinely vary in multi-group GSEs,
    # so require all non-empty values to agree and keep missing fraction stricter.
    "Disease": {
        "min_support": 5,
        "min_dominant_ratio": 1.00,
        "max_missing_pct": 0.30,
    },
    "Tissue": {
        "min_support": 5,
        "min_dominant_ratio": 1.00,
        "max_missing_pct": 0.30,
    },
    "RNA_Source": {
        "min_support": 5,
        "min_dominant_ratio": 1.00,
        "max_missing_pct": 0.30,
    },
    "SampleType": {
        "min_support": 5,
        "min_dominant_ratio": 1.00,
        "max_missing_pct": 0.30,
    },
    "Specimen_Type": {
        "min_support": 5,
        "min_dominant_ratio": 1.00,
        "max_missing_pct": 0.30,
    },
    "Model_Type": {
        "min_support": 5,
        "min_dominant_ratio": 1.00,
        "max_missing_pct": 0.30,
    },
}

DEFAULT_THRESHOLDS = {
    "min_support": 5,
    "min_dominant_ratio": 1.00,
    "max_missing_pct": 0.30,
}

EMPTY_TOKENS = {"", "nan", "none", "null", "missing", "blank"}
OPTIONAL_EMPTY_TOKENS = {
    "na",
    "n/a",
    "not available",
    "not applicable",
    "unknown",
    "not specified",
    "not reported",
    "not provided",
    "unavailable",
}

@dataclass(frozen=True)
class AuditConfig:
    gse_col: str = "GSE_ID"
    gsm_col: str = "GSM_ID"
    stage1_fields: Tuple[str, ...] = tuple(DEFAULT_STAGE1_FIELDS)
    treat_na_as_missing: bool = False
    min_support_default: int = 5
    min_dominant_ratio_default: float = 1.0
    max_missing_pct_default: float = 0.30
    max_examples_per_issue: int = 20


def clean_value(value: Any) -> str:
    """Return a stable string representation without turning 'NA' into missing."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    # Normalize Excel artifacts like 'nan' from prior string casts.
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def is_missing(value: Any, treat_na_as_missing: bool = False) -> bool:
    text = clean_value(value).strip()
    low = text.lower()
    if low in EMPTY_TOKENS:
        return True
    if treat_na_as_missing and low in OPTIONAL_EMPTY_TOKENS:
        return True
    return False


def norm_for_count(value: Any) -> str:
    """Normalization used only for counting exact-value consistency."""
    text = clean_value(value)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def read_table(path: Path, sheet_name: Optional[str] = None) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        return pd.read_excel(path, sheet_name=sheet_name or 0, dtype=str, keep_default_na=False)
    if suffix == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    if suffix in {".tsv", ".txt"}:
        return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)
    raise ValueError(f"Unsupported input file type: {path}")


def write_excel(
    corrected_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
    review_queue_df: pd.DataFrame,
    output_report: Path,
    output_corrected: Path,
    output_candidates: Path,
) -> None:
    output_report.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_report, engine="openpyxl") as writer:
        summary_df.to_excel(writer, index=False, sheet_name="GSE_Field_Summary")
        candidates_df.to_excel(writer, index=False, sheet_name="Cell_Correction_Candidates")
        review_queue_df.to_excel(writer, index=False, sheet_name="LLM_Human_Review_Queue")
        corrected_df.to_excel(writer, index=False, sheet_name="Corrected_Stage1")

    corrected_df.to_excel(output_corrected, index=False)
    candidates_df.to_excel(output_candidates, index=False)


def get_thresholds(field: str, config: AuditConfig) -> Dict[str, float]:
    t = dict(DEFAULT_THRESHOLDS)
    t["min_support"] = config.min_support_default
    t["min_dominant_ratio"] = config.min_dominant_ratio_default
    t["max_missing_pct"] = config.max_missing_pct_default
    t.update(FIELD_THRESHOLDS.get(field, {}))
    return t


def classify_field_policy(field: str) -> str:
    if field in ID_FIELDS or field in NEVER_CORRECT_FIELDS:
        return "never_correct"
    if field in PROPAGATABLE_FIELDS:
        return "propagatable"
    if field in REVIEW_ONLY_FIELDS:
        return "review_only"
    return "review_only"


def compute_distribution(series: pd.Series, config: AuditConfig) -> Tuple[Dict[str, int], int, int]:
    total = len(series)
    missing_mask = series.apply(lambda x: is_missing(x, config.treat_na_as_missing))
    missing_count = int(missing_mask.sum())
    non_missing = series[~missing_mask].map(norm_for_count)
    counts = non_missing.value_counts(dropna=False).to_dict()
    counts = {str(k): int(v) for k, v in counts.items() if str(k).strip() != ""}
    return counts, missing_count, total


def dominant_stats(counts: Dict[str, int]) -> Tuple[str, int, float, int]:
    if not counts:
        return "", 0, 0.0, 0
    sorted_items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    dominant_value, dominant_count = sorted_items[0]
    non_missing_count = sum(counts.values())
    dominant_ratio = dominant_count / non_missing_count if non_missing_count else 0.0
    unique_non_missing = len(counts)
    return dominant_value, dominant_count, dominant_ratio, unique_non_missing


def determine_issue_type(
    missing_count: int,
    total: int,
    counts: Dict[str, int],
    unique_non_missing: int,
) -> str:
    if total == 0:
        return "No Rows"
    if missing_count == total:
        return "Whole-GSE Missing"
    if missing_count > 0 and counts:
        if unique_non_missing == 1:
            return "Partial Missing - Single Non-empty Value"
        return "Partial Missing + Non-empty Conflict"
    if missing_count == 0 and unique_non_missing > 1:
        return "Non-empty Conflict"
    return "No Issue"


def determine_priority(
    field: str,
    issue_type: str,
    missing_pct: float,
    unique_non_missing: int,
    dominant_ratio: float,
) -> str:
    if issue_type == "No Issue":
        return "None"
    if issue_type == "Whole-GSE Missing":
        if field in PROPAGATABLE_FIELDS:
            return "High - Targeted Re-annotation"
        return "Medium - Missing Field Review"
    if "Conflict" in issue_type:
        if field in {"Disease", "Tissue", "RNA_Source", "Pert", "Pert_Dose", "GSM_Pert", "Control_Status"}:
            return "High - Biological/Design Conflict"
        return "Medium - Inconsistency Review"
    if issue_type.startswith("Partial Missing"):
        if field in PROPAGATABLE_FIELDS and dominant_ratio >= 0.95 and missing_pct <= 0.50:
            return "High - Candidate Fill"
        return "Medium - Candidate Review"
    return "Medium"


def should_auto_accept(
    field: str,
    old_value: Any,
    counts: Dict[str, int],
    missing_count: int,
    total: int,
    config: AuditConfig,
) -> Tuple[bool, str, str, str]:
    """Return auto_accept, confidence, suggested_value, reason."""
    if not is_missing(old_value, config.treat_na_as_missing):
        return False, "None", "", "Existing non-empty annotation is never overwritten automatically."

    policy = classify_field_policy(field)
    if policy != "propagatable":
        return False, "Low", "", f"Field policy is {policy}; auto-fill is disabled."

    if not counts:
        return False, "Low", "", "No non-empty value exists in the same GSE."

    dominant_value, dominant_count, dominant_ratio, unique_non_missing = dominant_stats(counts)
    thresholds = get_thresholds(field, config)
    missing_pct = missing_count / total if total else 0.0

    if unique_non_missing != 1:
        return (
            False,
            "Medium",
            dominant_value,
            f"Multiple non-empty values exist in the same GSE: {json.dumps(counts, ensure_ascii=False)}.",
        )

    if dominant_count < int(thresholds["min_support"]):
        return (
            False,
            "Medium",
            dominant_value,
            f"Only {dominant_count} supporting non-empty GSMs; minimum support is {int(thresholds['min_support'])}.",
        )

    if dominant_ratio < float(thresholds["min_dominant_ratio"]):
        return (
            False,
            "Medium",
            dominant_value,
            f"Dominant ratio {dominant_ratio:.3f} is below threshold {thresholds['min_dominant_ratio']:.3f}.",
        )

    if missing_pct > float(thresholds["max_missing_pct"]):
        return (
            False,
            "Medium",
            dominant_value,
            f"Missing percentage {missing_pct:.3f} exceeds threshold {thresholds['max_missing_pct']:.3f}.",
        )

    reason = (
        f"High-confidence blank fill: field={field}; same-GSE non-empty values all equal "
        f"'{dominant_value}' ({dominant_count}/{dominant_count}); missing_pct={missing_pct:.3f}; "
        "only blank cells are modified."
    )
    return True, "High", dominant_value, reason

def _norm_token(value: Any) -> str:
    return re.sub(r"\s+", " ", clean_value(value)).strip().casefold()


def _norm_gsm_pert_status(value: Any, config: AuditConfig) -> str:
    """
    Normalize GSM_Pert for deterministic QA1 logic.

    Only exact controlled values are accepted for auto-logic.
    Other values are treated as unresolved and routed away from auto-correction.
    """
    if is_missing(value, config.treat_na_as_missing):
        return "missing"

    v = _norm_token(value)

    if v == "perturbed":
        return "Perturbed"

    if v == "control":
        return "Control"

    return "other"


def _norm_gse_pert_status(value: Any, config: AuditConfig) -> str:
    """
    Normalize GSE_Pert for deterministic QA1 logic.
    """
    if is_missing(value, config.treat_na_as_missing):
        return "missing"

    v = _norm_token(value)

    if v == "yes":
        return "Yes"

    if v == "no":
        return "No"

    return "other"


def _has_nonempty_perturbation_details(gse_df: pd.DataFrame, config: AuditConfig) -> bool:
    """
    Conservative check for treatment details in an all-control GSE.

    If all GSM_Pert values are Control but perturbation detail fields are present,
    do not auto-set contradictory GSE_Pert values to No; route for review instead.
    """
    detail_cols = [
        "Pert",
        "Pert_Dose",
        "Pert_Freq",
        "Pert_Duration",
        "Route_Admin",
    ]

    control_like = {
        "control",
        "untreated",
        "vehicle",
        "vehicle control",
        "mock",
        "sham",
        "none",
        "no treatment",
        "no-treatment",
        "no perturbation",
    }

    for col in detail_cols:
        if col not in gse_df.columns:
            continue

        for value in gse_df[col].tolist():
            if is_missing(value, config.treat_na_as_missing):
                continue

            v = _norm_token(value)
            if v not in control_like:
                return True

    return False


def apply_gse_pert_consistency_rule(
    *,
    corrected: pd.DataFrame,
    df_original: pd.DataFrame,
    gse_df: pd.DataFrame,
    gse_id_clean: str,
    config: AuditConfig,
    candidate_rows: List[Dict[str, Any]],
    review_rows: List[Dict[str, Any]],
) -> None:
    """
    Deterministic QA1 rule for GSE_Pert based on within-GSE GSM_Pert values.

    Auto-corrects:
      - any GSM_Pert == Perturbed  -> GSE_Pert = Yes
      - all GSM_Pert == Control and GSE_Pert missing -> GSE_Pert = No

    Review only:
      - all GSM_Pert == Control but existing GSE_Pert == Yes
      - unresolved GSM_Pert values
    """
    if "GSE_Pert" not in gse_df.columns or "GSM_Pert" not in gse_df.columns:
        return

    gsm_statuses = [
        _norm_gsm_pert_status(v, config)
        for v in gse_df["GSM_Pert"].tolist()
    ]

    if not gsm_statuses:
        return

    status_counts = {
        status: int(gsm_statuses.count(status))
        for status in sorted(set(gsm_statuses))
    }

    any_perturbed = any(s == "Perturbed" for s in gsm_statuses)
    all_control = all(s == "Control" for s in gsm_statuses)

    target_value = ""
    rule_name = ""
    reason = ""
    allow_overwrite_yes_to_no = False

    if any_perturbed:
        target_value = "Yes"
        rule_name = "GSE_Pert derived from any GSM_Pert Perturbed"
        reason = (
            "High-confidence deterministic correction: at least one GSM in this GSE "
            "has GSM_Pert=Perturbed, so GSE_Pert should be Yes."
        )

    elif all_control:
        target_value = "No"
        rule_name = "GSE_Pert derived from all GSM_Pert Control"
        reason = (
            "High-confidence deterministic fill: all GSMs in this GSE have "
            "GSM_Pert=Control, so missing GSE_Pert can be filled as No."
        )
        allow_overwrite_yes_to_no = False

        # If all samples are Control but perturbation detail fields exist,
        # do not auto-correct to No; route to review.
        if _has_nonempty_perturbation_details(gse_df, config):
            review_rows.append(
                {
                    "Issue_ID": f"{gse_id_clean}__GSE_Pert_GSM_Pert_Detail_Conflict",
                    "GSE_ID": gse_id_clean,
                    "Field": "GSE_Pert",
                    "Issue_Type": "All GSM_Pert Control but perturbation detail fields present",
                    "Review_Priority": "High - Perturbation Review",
                    "Field_Policy": "deterministic_review",
                    "N_Total": int(gse_df.shape[0]),
                    "N_Missing": 0,
                    "Missing_Pct": 0,
                    "Value_Distribution_JSON": json.dumps(status_counts, ensure_ascii=False),
                    "Dominant_Value": "Control",
                    "Dominant_Ratio_NonMissing": 1.0,
                    "Example_Missing_GSMs": "",
                    "LLM_Reviewer_Status": "Pending",
                    "Human_Review_Status": "Pending",
                    "Reviewer_Decision": "",
                    "Reviewer_Reason": "",
                }
            )
            return

    else:
        # Mixed missing/other GSM_Pert statuses are not safe for deterministic correction.
        return

    review_added = False

    for idx in gse_df.index:
        old_value = corrected.at[idx, "GSE_Pert"]
        old_status = _norm_gse_pert_status(old_value, config)

        if old_status == target_value:
            continue

        auto_accept = True

        # Conservative safety rule:
        # do not overwrite an existing GSE_Pert=Yes to No based only on all-control GSM_Pert.
        if target_value == "No" and old_status == "Yes" and not allow_overwrite_yes_to_no:
            auto_accept = False

        # Unknown/non-controlled current values should be reviewed for target No.
        if target_value == "No" and old_status == "other":
            auto_accept = False

        action = "AUTO_ACCEPT_GSE_PERT_RULE" if auto_accept else "REVIEW_REQUIRED"

        try:
            row_index = int(idx)
        except Exception:
            row_index = clean_value(idx)

        candidate_rows.append(
            {
                "GSE_ID": gse_id_clean,
                "GSM_ID": clean_value(df_original.at[idx, config.gsm_col]),
                "Row_Index_0Based": row_index,
                "Field": "GSE_Pert",
                "Old_Value": clean_value(old_value),
                "Suggested_Value": target_value,
                "Correction_Type": rule_name,
                "Confidence": "High" if auto_accept else "Medium",
                "Auto_Accept": "YES" if auto_accept else "NO",
                "Action": action,
                "Evidence": reason,
                "Same_GSE_Value_Distribution_JSON": json.dumps(status_counts, ensure_ascii=False),
                "Dominant_Ratio_NonMissing": 1.0 if all_control else "",
                "Missing_Pct": 0,
                "Accept_Correction": "YES" if auto_accept else "REVIEW",
                "Reviewer_Notes": "",
            }
        )

        if auto_accept:
            corrected.at[idx, "GSE_Pert"] = target_value

        elif not review_added:
            review_rows.append(
                {
                    "Issue_ID": f"{gse_id_clean}__GSE_Pert_GSM_Pert_Consistency",
                    "GSE_ID": gse_id_clean,
                    "Field": "GSE_Pert",
                    "Issue_Type": "GSE_Pert conflicts with within-GSE GSM_Pert distribution",
                    "Review_Priority": "High - Perturbation Review",
                    "Field_Policy": "deterministic_review",
                    "N_Total": int(gse_df.shape[0]),
                    "N_Missing": 0,
                    "Missing_Pct": 0,
                    "Value_Distribution_JSON": json.dumps(status_counts, ensure_ascii=False),
                    "Dominant_Value": target_value,
                    "Dominant_Ratio_NonMissing": 1.0 if all_control else "",
                    "Example_Missing_GSMs": "",
                    "LLM_Reviewer_Status": "Pending",
                    "Human_Review_Status": "Pending",
                    "Reviewer_Decision": "",
                    "Reviewer_Reason": "",
                }
            )
            review_added = True

def build_audit_and_corrections(
    df: pd.DataFrame,
    config: AuditConfig,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if config.gse_col not in df.columns:
        raise ValueError(f"Required GSE column not found: {config.gse_col}")
    if config.gsm_col not in df.columns:
        raise ValueError(f"Required GSM column not found: {config.gsm_col}")

    corrected = df.copy()
    present_fields = [f for f in config.stage1_fields if f in df.columns]
    missing_fields = [f for f in config.stage1_fields if f not in df.columns]

    summary_rows: List[Dict[str, Any]] = []
    candidate_rows: List[Dict[str, Any]] = []
    review_rows: List[Dict[str, Any]] = []

    if missing_fields:
        print(f"WARNING: {len(missing_fields)} configured Stage 1 fields are absent from input: {missing_fields}")

    for gse_id, gse_df in df.groupby(config.gse_col, dropna=False, sort=True):
        gse_id_clean = clean_value(gse_id)
        n_gse = len(gse_df)

        for field in present_fields:
            if field in ID_FIELDS:
                continue

            counts, missing_count, total = compute_distribution(gse_df[field], config)
            dominant_value, dominant_count, dominant_ratio, unique_non_missing = dominant_stats(counts)
            missing_pct = missing_count / total if total else 0.0
            issue_type = determine_issue_type(missing_count, total, counts, unique_non_missing)
            priority = determine_priority(field, issue_type, missing_pct, unique_non_missing, dominant_ratio)
            field_policy = classify_field_policy(field)

            example_missing_gsms = gse_df.loc[
                gse_df[field].apply(lambda x: is_missing(x, config.treat_na_as_missing)), config.gsm_col
            ].astype(str).head(config.max_examples_per_issue).tolist()
            example_values = gse_df[[config.gsm_col, field]].head(config.max_examples_per_issue).to_dict("records")

            summary_rows.append(
                {
                    "GSE_ID": gse_id_clean,
                    "Field": field,
                    "Field_Policy": field_policy,
                    "N_Total": n_gse,
                    "N_Missing": missing_count,
                    "Missing_Pct": round(missing_pct, 4),
                    "N_NonMissing": sum(counts.values()),
                    "Unique_NonMissing_Values": unique_non_missing,
                    "Dominant_Value": dominant_value,
                    "Dominant_Count": dominant_count,
                    "Dominant_Ratio_NonMissing": round(dominant_ratio, 4),
                    "Value_Distribution_JSON": json.dumps(counts, ensure_ascii=False),
                    "Issue_Type": issue_type,
                    "Review_Priority": priority,
                    "Example_Missing_GSMs": "; ".join(example_missing_gsms),
                }
            )

            # Add GSE-level review queue rows for meaningful issues.
            if issue_type != "No Issue" and field not in DEDICATED_QA1_RULE_FIELDS:
                review_rows.append(
                    {
                        "Issue_ID": f"{gse_id_clean}__{field}",
                        "GSE_ID": gse_id_clean,
                        "Field": field,
                        "Issue_Type": issue_type,
                        "Review_Priority": priority,
                        "Field_Policy": field_policy,
                        "N_Total": n_gse,
                        "N_Missing": missing_count,
                        "Missing_Pct": round(missing_pct, 4),
                        "Value_Distribution_JSON": json.dumps(counts, ensure_ascii=False),
                        "Dominant_Value": dominant_value,
                        "Dominant_Ratio_NonMissing": round(dominant_ratio, 4),
                        "Example_Missing_GSMs": "; ".join(example_missing_gsms),
                        "LLM_Reviewer_Status": "Pending" if priority != "None" else "Not Needed",
                        "Human_Review_Status": "Pending" if "Human" in priority else "Not Needed",
                        "Reviewer_Decision": "",
                        "Reviewer_Reason": "",
                    }
                )

            # Cell-level candidates for missing cells only.
            # Dedicated-rule fields such as GSE_Pert are handled by their own
            # deterministic rule below, so avoid duplicate generic candidates.
            if missing_count > 0 and field not in DEDICATED_QA1_RULE_FIELDS:
                missing_idx = gse_df.index[gse_df[field].apply(lambda x: is_missing(x, config.treat_na_as_missing))]
                for idx in missing_idx:
                    old_value = df.at[idx, field]
                    auto_accept, confidence, suggested_value, reason = should_auto_accept(
                        field=field,
                        old_value=old_value,
                        counts=counts,
                        missing_count=missing_count,
                        total=total,
                        config=config,
                    )
                    action = "AUTO_ACCEPT_FILL" if auto_accept else "REVIEW_REQUIRED"
                    candidate_rows.append(
                        {
                            "GSE_ID": gse_id_clean,
                            "GSM_ID": clean_value(df.at[idx, config.gsm_col]),
                            "Row_Index_0Based": int(idx),
                            "Field": field,
                            "Old_Value": clean_value(old_value),
                            "Suggested_Value": suggested_value,
                            "Correction_Type": "Fill missing from within-GSE dominant value" if suggested_value else "No safe value",
                            "Confidence": confidence,
                            "Auto_Accept": "YES" if auto_accept else "NO",
                            "Action": action,
                            "Evidence": reason,
                            "Same_GSE_Value_Distribution_JSON": json.dumps(counts, ensure_ascii=False),
                            "Dominant_Ratio_NonMissing": round(dominant_ratio, 4),
                            "Missing_Pct": round(missing_pct, 4),
                            "Accept_Correction": "YES" if auto_accept else "REVIEW",
                            "Reviewer_Notes": "",
                        }
                    )
                    if auto_accept:
                        corrected.at[idx, field] = suggested_value
        
        apply_gse_pert_consistency_rule(
            corrected=corrected,
            df_original=df,
            gse_df=gse_df,
            gse_id_clean=gse_id_clean,
            config=config,
            candidate_rows=candidate_rows,
            review_rows=review_rows,
        )

    summary_df = pd.DataFrame(summary_rows)
    candidates_df = pd.DataFrame(candidate_rows)
    review_queue_df = pd.DataFrame(review_rows)
    return corrected, summary_df, candidates_df, review_queue_df

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Within-GSE consistency audit and Stage 1 high-confidence correction")
    parser.add_argument("--input", required=True, help="Stage 1 output file (.xlsx, .csv, .tsv)")
    parser.add_argument("--sheet-name", default=None, help="Excel sheet name. Defaults to first sheet.")
    parser.add_argument("--output-dir", required=True, help="Directory for output files")
    parser.add_argument("--run-version", required=True, help="Run version prefix for output file names")
    parser.add_argument("--gse-col", default="GSE_ID")
    parser.add_argument("--gsm-col", default="GSM_ID")
    parser.add_argument(
        "--fields",
        default=None,
        help="Optional comma-separated Stage 1 fields to audit. Defaults to GEOMeta 27 Stage 1 fields.",
    )
    parser.add_argument(
        "--treat-na-as-missing",
        action="store_true",
        help="Treat literal NA/N/A as missing. Default is False to avoid overwriting intentional NA annotations.",
    )
    parser.add_argument("--min-support-default", type=int, default=5)
    parser.add_argument("--min-dominant-ratio-default", type=float, default=1.0)
    parser.add_argument("--max-missing-pct-default", type=float, default=0.30)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stage1_fields = tuple([x.strip() for x in args.fields.split(",") if x.strip()]) if args.fields else tuple(DEFAULT_STAGE1_FIELDS)

    config = AuditConfig(
        gse_col=args.gse_col,
        gsm_col=args.gsm_col,
        stage1_fields=stage1_fields,
        treat_na_as_missing=args.treat_na_as_missing,
        min_support_default=args.min_support_default,
        min_dominant_ratio_default=args.min_dominant_ratio_default,
        max_missing_pct_default=args.max_missing_pct_default,
    )

    print(f"Reading Stage 1 file: {input_path}")
    df = read_table(input_path, sheet_name=args.sheet_name)
    print(f"Rows: {len(df):,}; columns: {len(df.columns):,}")

    corrected, summary_df, candidates_df, review_queue_df = build_audit_and_corrections(df, config)

    report_path = output_dir / f"{args.run_version}_stage1_qa1_consistency_report.xlsx"
    corrected_path = output_dir / f"{args.run_version}_stage1_qa1_corrected_high_confidence.xlsx"
    candidates_path = output_dir / f"{args.run_version}_stage1_qa1_correction_candidates.xlsx"

    write_excel(
        corrected_df=corrected,
        summary_df=summary_df,
        candidates_df=candidates_df,
        review_queue_df=review_queue_df,
        output_report=report_path,
        output_corrected=corrected_path,
        output_candidates=candidates_path,
    )

    n_auto = int((candidates_df["Auto_Accept"] == "YES").sum()) if not candidates_df.empty else 0
    n_review = int((candidates_df["Auto_Accept"] == "NO").sum()) if not candidates_df.empty else 0
    n_issues = int((summary_df["Issue_Type"] != "No Issue").sum()) if not summary_df.empty else 0

    print("Done.")
    print(f"Issue groups: {n_issues:,}")
    print(f"Auto-accepted blank-cell fills: {n_auto:,}")
    print(f"Cell candidates requiring review: {n_review:,}")
    print(f"Report: {report_path}")
    print(f"Corrected Stage 1 for Stage 2 input: {corrected_path}")
    print(f"Correction candidates: {candidates_path}")


if __name__ == "__main__":
    main()
