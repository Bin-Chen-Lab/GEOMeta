from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


# -----------------------------------------------------------------------------
# Within-GSE consistency review for GEOMeta
# -----------------------------------------------------------------------------
# Purpose
#   Run after Stage 3 mapping. This module does not silently rewrite the release.
#   It produces:
#     1) a GSE-field summary table,
#     2) a row/cell-level issue table,
#     3) a fixed-candidate table with proposed rescue annotations,
#     4) a changed-cell audit table.
#
# Design principle
#   Most GEO series have a coherent study design. Some fields are expected to be
#   stable within a GSE, while others may vary by sample. This reviewer detects
#   suspicious within-GSE gaps or rare inconsistent labels, especially after
#   Stage 2/3 normalization.
# -----------------------------------------------------------------------------


MISSING_TOKENS = {
    "", "na", "n/a", "nan", "none", "null", "unknown", "not specified",
    "not reported", "not available", "not provided", "unavailable",
}

NO_DISEASE_STATES = {
    "normal", "adjacent normal", "no disease mentioned",
}


def _s(x: Any) -> str:
    if x is None:
        return ""
    try:
        if isinstance(x, float) and x != x:
            return ""
    except Exception:
        pass
    return str(x).strip()


def _norm(x: Any) -> str:
    v = _s(x).strip().lower()
    v = re.sub(r"\s+", " ", v)
    return v


def is_missing(x: Any) -> bool:
    return _norm(x) in MISSING_TOKENS


def clean_value(x: Any) -> str:
    v = _s(x)
    return "" if is_missing(v) else v


def pick_existing_col(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    existing = {c: c for c in df.columns}
    lower = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c in existing:
            return c
        if c.lower() in lower:
            return lower[c.lower()]
    return None


@dataclass
class FieldRule:
    label: str
    candidates: List[str]
    expected: str  # "stable", "quasi_stable", "variable", "audit_only"
    dominant_threshold: float = 0.80
    rare_value_threshold: float = 0.10
    max_missing_rescue_fraction: float = 0.20
    propose_missing_rescue: bool = True
    propose_rare_value_rescue: bool = False
    notes: str = ""


DEFAULT_RULES: List[FieldRule] = [
    # Core stable fields. Multiple values are usually suspicious unless the GSE is truly mixed-platform/mixed-model.
    FieldRule("Organism", ["Organism_Post", "Organism"], "stable", 0.98, 0.02, 0.05, True, False,
              "Should usually be one organism within a strict human-only run."),
    FieldRule("Seq_Type", ["Seq_Type_Post", "Seq_Type"], "quasi_stable", 0.85, 0.10, 0.20, True, False,
              "May vary in mixed-assay GSEs, but rare blanks/minority labels should be reviewed."),
    FieldRule("RNA_Library", ["RNA_Library_Post", "RNA_Library"], "quasi_stable", 0.80, 0.10, 0.25, True, False,
              "Often shared within a sequencing study, but missingness is common."),
    FieldRule("RNA_Source", ["RNA_Source_Post", "RNA_Source"], "quasi_stable", 0.80, 0.10, 0.25, True, False,
              "Often shared within a sequencing study."),
    FieldRule("Experimental_Setting", ["Experimental_Setting_Post", "Experimental_Setting"], "quasi_stable", 0.85, 0.10, 0.20, True, False,
              "Usually stable unless the GSE intentionally mixes in vivo/in vitro contexts."),
    FieldRule("Model_Type", ["Model_Type_Post", "Model_Type"], "quasi_stable", 0.85, 0.10, 0.20, True, False,
              "Usually stable within a GSE."),

    # Biological labels. These can vary by case/control, stage, tissue, or cohort design.
    # Do not blindly overwrite rare values. Only propose rescue for missing cells when a strong dominant label exists.
    FieldRule("Disease", ["Disease_Mapped", "Disease_Post", "Disease"], "variable", 0.75, 0.10, 0.25, True, False,
              "Can vary by case/control or disease stage; rescue only missing minority cells."),
    FieldRule("Tissue", ["Tissue_Mapped", "Tissue_Post", "Organ_Region_Post", "Tissue"], "variable", 0.75, 0.10, 0.25, True, False,
              "Can vary in multi-tissue studies; rescue only missing minority cells."),

    # Sample/model metadata. Variable fields are summarized and flagged mainly for missing-minority rescue.
    FieldRule("SampleType", ["SampleType", "Sample_Type"], "variable", 0.80, 0.10, 0.25, True, False,
              "Can vary but often stable within one GSE."),
    FieldRule("Specimen_Type", ["Specimen_Type_Post", "Specimen_Type"], "variable", 0.80, 0.10, 0.25, True, False,
              "Can vary but often stable within one GSE."),
    FieldRule("Sex", ["Sex_Post", "Sex"], "variable", 0.80, 0.10, 0.25, False, False,
              "Expected to vary in many human cohorts; audit only by default."),
    FieldRule("Age", ["Age_Post", "Age"], "audit_only", 0.80, 0.10, 0.25, False, False,
              "Usually expected to vary; distribution only."),

    # Perturbation context.
    FieldRule("GSE_Pert", ["GSE_Pert_Post", "GSE_Pert"], "stable", 0.98, 0.02, 0.05, True, False,
              "Study-level perturbation indicator should be stable within GSE."),
    FieldRule("GSM_Pert", ["GSM_Pert_Post", "GSM_Pert"], "variable", 0.75, 0.10, 0.25, True, False,
              "Expected to vary by treated/control samples."),
    FieldRule("Pert_Type", ["Pert_Type"], "variable", 0.75, 0.10, 0.25, True, False,
              "Expected to vary by perturbed/control samples."),
]


def load_table(path: Path, sheet_name: Optional[str] = None) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, sheet_name=sheet_name or 0, engine="openpyxl")
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t")
    if suffix == ".parquet":
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported input file type: {path}")


def value_counts_nonmissing(s: pd.Series) -> pd.Series:
    vals = s.map(clean_value)
    vals = vals[vals != ""]
    if vals.empty:
        return pd.Series(dtype="int64")
    return vals.value_counts(dropna=False)


def compact_distribution(vc: pd.Series, max_items: int = 8) -> str:
    if vc.empty:
        return ""
    parts = [f"{idx}: {int(val)}" for idx, val in vc.head(max_items).items()]
    if vc.shape[0] > max_items:
        parts.append(f"... +{vc.shape[0] - max_items} more")
    return " | ".join(parts)


def build_context_columns(df: pd.DataFrame) -> List[str]:
    candidates = [
        "GSM_ID", "GSE_ID", "Title", "Source_Name", "Source Name", "GSM_Info",
        "GSE_Info", "Disease_Pre", "Disease_Post", "Disease_Mapped",
        "Tissue_Pre", "Tissue_Post", "Tissue_Mapped", "Organ_Region_Post",
        "Seq_Type_Pre", "Seq_Type_Post", "RNA_Library_Pre", "RNA_Library_Post",
        "RNA_Source_Pre", "RNA_Source_Post", "Experimental_Setting_Pre", "Experimental_Setting_Post",
        "Model_Type_Pre", "Model_Type_Post", "SampleType", "Specimen_Type_Post",
        "GSE_Pert_Post", "GSM_Pert_Post", "Pert_Post", "Pert_Type",
    ]
    return [c for c in candidates if c in df.columns]


def review_within_gse(
    df: pd.DataFrame,
    rules: List[FieldRule] = DEFAULT_RULES,
    min_gse_size: int = 3,
    apply_missing_rescue: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Return:
      - fixed_candidate_df
      - flagged_cells_df
      - gse_field_summary_df
      - changed_cells_df
    """
    if "GSE_ID" not in df.columns or "GSM_ID" not in df.columns:
        raise ValueError("Input dataframe must contain GSE_ID and GSM_ID.")

    out = df.copy()
    out["GSE_ID"] = out["GSE_ID"].astype(str).str.strip()
    out["GSM_ID"] = out["GSM_ID"].astype(str).str.strip()

    flagged_rows: List[Dict[str, Any]] = []
    summary_rows: List[Dict[str, Any]] = []
    changed_rows: List[Dict[str, Any]] = []

    context_cols = build_context_columns(out)

    resolved_rules = []
    for rule in rules:
        col = pick_existing_col(out, rule.candidates)
        if col:
            resolved_rules.append((rule, col))

    for gse_id, sub_idx in out.groupby("GSE_ID", dropna=False).groups.items():
        idx_list = list(sub_idx)
        sub = out.loc[idx_list].copy()
        n = int(sub.shape[0])
        if n < min_gse_size:
            continue

        for rule, col in resolved_rules:
            values = sub[col]
            missing_mask = values.map(is_missing)
            missing_count = int(missing_mask.sum())
            vc = value_counts_nonmissing(values)
            nonmissing_count = int(vc.sum()) if not vc.empty else 0
            unique_nonmissing = int(vc.shape[0])
            dominant_value = str(vc.index[0]) if not vc.empty else ""
            dominant_count = int(vc.iloc[0]) if not vc.empty else 0
            dominant_fraction_all = dominant_count / n if n else 0.0
            dominant_fraction_nonmissing = dominant_count / nonmissing_count if nonmissing_count else 0.0
            missing_fraction = missing_count / n if n else 0.0

            gse_status = "pass"
            issue_types = []

            if unique_nonmissing > 1 and rule.expected == "stable":
                gse_status = "review"
                issue_types.append("unexpected_stable_field_heterogeneity")

            elif unique_nonmissing > 1 and rule.expected == "quasi_stable":
                if dominant_fraction_nonmissing < rule.dominant_threshold:
                    gse_status = "review"
                    issue_types.append("quasi_stable_field_mixed_values")
                else:
                    # Rare minority labels under strong dominant context.
                    issue_types.append("rare_minority_value_under_dominant_context")

            if (
                rule.propose_missing_rescue
                and missing_count > 0
                and dominant_value
                and dominant_fraction_nonmissing >= rule.dominant_threshold
                and missing_fraction <= rule.max_missing_rescue_fraction
            ):
                gse_status = "review" if gse_status == "pass" else gse_status
                issue_types.append("missing_minority_under_dominant_context")

            summary_rows.append({
                "GSE_ID": gse_id,
                "Field_Label": rule.label,
                "Column": col,
                "Expected_Behavior": rule.expected,
                "GSE_Size": n,
                "Nonmissing_Count": nonmissing_count,
                "Missing_Count": missing_count,
                "Unique_Nonmissing_Values": unique_nonmissing,
                "Dominant_Value": dominant_value,
                "Dominant_Count": dominant_count,
                "Dominant_Fraction_All": round(dominant_fraction_all, 4),
                "Dominant_Fraction_Nonmissing": round(dominant_fraction_nonmissing, 4),
                "Missing_Fraction": round(missing_fraction, 4),
                "Distribution": compact_distribution(vc),
                "QC_Status": gse_status,
                "Issue_Types": "; ".join(sorted(set(issue_types))),
                "Rule_Notes": rule.notes,
            })

            # Flag missing cells that can be rescued by dominant within-GSE context.
            if (
                rule.propose_missing_rescue
                and missing_count > 0
                and dominant_value
                and dominant_fraction_nonmissing >= rule.dominant_threshold
                and missing_fraction <= rule.max_missing_rescue_fraction
            ):
                for row_idx in sub.loc[missing_mask].index:
                    original = out.at[row_idx, col]
                    issue = {
                        "GSE_ID": gse_id,
                        "GSM_ID": out.at[row_idx, "GSM_ID"],
                        "Field_Label": rule.label,
                        "Column": col,
                        "Issue_Type": "missing_minority_under_dominant_context",
                        "Severity": "medium",
                        "Original_Value": _s(original),
                        "Suggested_Value": dominant_value,
                        "Recommended_Action": "rescue_missing_candidate" if not apply_missing_rescue else "applied_missing_rescue",
                        "Rationale": (
                            f"Within {gse_id}, {dominant_count}/{nonmissing_count} non-missing samples "
                            f"have {col}={dominant_value}; this row is missing."
                        ),
                        "Dominant_Value": dominant_value,
                        "Dominant_Count": dominant_count,
                        "Nonmissing_Count": nonmissing_count,
                        "GSE_Size": n,
                        "Distribution": compact_distribution(vc),
                    }
                    # Add compact source context from same row.
                    for c in context_cols:
                        issue[f"Context_{c}"] = out.at[row_idx, c]
                    flagged_rows.append(issue)

                    audit_col_original = f"{col}__Before_GSE_QC"
                    audit_col_suggested = f"{col}__GSE_QC_Suggested"
                    audit_col_action = f"{col}__GSE_QC_Action"
                    for c in [audit_col_original, audit_col_suggested, audit_col_action]:
                        if c not in out.columns:
                            out[c] = ""
                    out.at[row_idx, audit_col_original] = _s(original)
                    out.at[row_idx, audit_col_suggested] = dominant_value
                    out.at[row_idx, audit_col_action] = issue["Recommended_Action"]

                    if apply_missing_rescue:
                        out.at[row_idx, col] = dominant_value
                        changed_rows.append({
                            "GSE_ID": gse_id,
                            "GSM_ID": out.at[row_idx, "GSM_ID"],
                            "Column": col,
                            "Field_Label": rule.label,
                            "Original_Value": _s(original),
                            "New_Value": dominant_value,
                            "Change_Type": "applied_missing_rescue_from_within_gse_dominant_value",
                            "Rationale": issue["Rationale"],
                        })

            # Flag rare minority values under stable/quasi-stable fields; do not auto-fix.
            if unique_nonmissing > 1 and rule.expected in {"stable", "quasi_stable"} and dominant_value:
                for value, count in vc.items():
                    if value == dominant_value:
                        continue
                    frac_all = int(count) / n
                    if rule.expected == "stable" or frac_all <= rule.rare_value_threshold:
                        minority_mask = values.map(clean_value) == str(value)
                        for row_idx in sub.loc[minority_mask].index:
                            issue = {
                                "GSE_ID": gse_id,
                                "GSM_ID": out.at[row_idx, "GSM_ID"],
                                "Field_Label": rule.label,
                                "Column": col,
                                "Issue_Type": "minority_value_under_dominant_context",
                                "Severity": "medium" if rule.expected == "stable" else "low",
                                "Original_Value": _s(out.at[row_idx, col]),
                                "Suggested_Value": "",
                                "Recommended_Action": "manual_review_or_rerun_field",
                                "Rationale": (
                                    f"Within {gse_id}, dominant {col}={dominant_value} "
                                    f"({dominant_count}/{nonmissing_count} non-missing); this row has minority value {value}."
                                ),
                                "Dominant_Value": dominant_value,
                                "Dominant_Count": dominant_count,
                                "Nonmissing_Count": nonmissing_count,
                                "GSE_Size": n,
                                "Distribution": compact_distribution(vc),
                            }
                            for c in context_cols:
                                issue[f"Context_{c}"] = out.at[row_idx, c]
                            flagged_rows.append(issue)

    flagged_cells_df = pd.DataFrame(flagged_rows)
    gse_field_summary_df = pd.DataFrame(summary_rows)
    changed_cells_df = pd.DataFrame(changed_rows)

    return out, flagged_cells_df, gse_field_summary_df, changed_cells_df


def write_outputs(
    output_path: Path,
    fixed_candidate_df: pd.DataFrame,
    flagged_cells_df: pd.DataFrame,
    gse_field_summary_df: pd.DataFrame,
    changed_cells_df: pd.DataFrame,
    run_config: Dict[str, Any],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    readme = pd.DataFrame([
        {"Item": "Purpose", "Value": "Within-GSE consistency review after Stage 3 mapping."},
        {"Item": "Default behavior", "Value": "Does not overwrite annotations unless apply_missing_rescue=True."},
        {"Item": "Main review output", "Value": "Flagged_Cells and GSE_Field_Summary sheets."},
        {"Item": "Fixed candidate", "Value": "Fixed_Candidate contains original rows plus QC suggestion audit columns."},
        {"Item": "Missing rescue", "Value": "Only proposed when a field has a strong dominant value within the GSE and a small minority of missing cells."},
        {"Item": "Rare minority values", "Value": "Flagged for review; not auto-fixed."},
        {"Item": "Run config", "Value": json.dumps(run_config, ensure_ascii=False)},
    ])

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        readme.to_excel(writer, sheet_name="README", index=False)
        gse_field_summary_df.to_excel(writer, sheet_name="GSE_Field_Summary", index=False)
        flagged_cells_df.to_excel(writer, sheet_name="Flagged_Cells", index=False)
        changed_cells_df.to_excel(writer, sheet_name="Changed_Cells", index=False)
        fixed_candidate_df.to_excel(writer, sheet_name="Fixed_Candidate", index=False)


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 3.5 within-GSE consistency review for GEOMeta outputs.")
    ap.add_argument("--input", required=True, help="Stage 3 mapped file: .xlsx, .csv, .tsv, or .parquet")
    ap.add_argument("--sheet", default=None, help="Excel sheet name/index to read. Default: first sheet.")
    ap.add_argument("--output", required=True, help="Output QC workbook .xlsx")
    ap.add_argument("--min-gse-size", type=int, default=3, help="Minimum samples per GSE for review. Default: 3")
    ap.add_argument(
        "--apply-missing-rescue",
        action="store_true",
        help="If set, apply high-confidence missing-cell rescue in Fixed_Candidate. Default: suggest only.",
    )
    args = ap.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    df = load_table(input_path, sheet_name=args.sheet)
    fixed, flagged, summary, changed = review_within_gse(
        df=df,
        min_gse_size=args.min_gse_size,
        apply_missing_rescue=bool(args.apply_missing_rescue),
    )

    run_config = {
        "input": str(input_path),
        "sheet": args.sheet,
        "output": str(output_path),
        "min_gse_size": args.min_gse_size,
        "apply_missing_rescue": bool(args.apply_missing_rescue),
        "input_rows": int(df.shape[0]),
        "input_gse_count": int(df["GSE_ID"].nunique()) if "GSE_ID" in df.columns else None,
        "flagged_cells": int(flagged.shape[0]),
        "changed_cells": int(changed.shape[0]),
    }

    write_outputs(
        output_path=output_path,
        fixed_candidate_df=fixed,
        flagged_cells_df=flagged,
        gse_field_summary_df=summary,
        changed_cells_df=changed,
        run_config=run_config,
    )

    print("[SAVED]", output_path)
    print(json.dumps(run_config, indent=2))


if __name__ == "__main__":
    main()
