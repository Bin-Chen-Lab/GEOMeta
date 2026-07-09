#!/usr/bin/env python3
"""
Merge two GEOMeta Stage 3 runs and create audit summaries.

Default use from GEOMeta repo root:

python scripts/merge_stage3_outputs_and_audit.py \
  --workdir . \
  --run1 geometa_may2026_hs_batch1_2_20260615_020000 \
  --run2 geometa_may2026_hs_batch3_4_20260615_074356 \
  --out-prefix GEOMeta_May2026_Homo_sapiens_AllSamples

Outputs are written to artifacts/outputs/ and artifacts/review_queue/.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from collections import Counter
from typing import Any

import pandas as pd

MISSING = {"", "na", "n/a", "nan", "none", "null", "unknown", "not specified", "not reported", "not available", "not applicable"}


def clean(x: Any) -> str:
    if x is None:
        return ""
    try:
        if isinstance(x, float) and x != x:
            return ""
    except Exception:
        pass
    v = str(x).strip()
    return "" if v.lower() in {"nan", "none", "null"} else v


def norm(x: Any) -> str:
    return " ".join(clean(x).lower().split())


def is_missing(x: Any) -> bool:
    return norm(x) in MISSING


def bool_true(x: Any) -> bool:
    return norm(x) in {"true", "1", "yes", "y", "review", "required"}


def value_counts_df(s: pd.Series, name: str, n_total: int | None = None) -> pd.DataFrame:
    vc = s.fillna("").astype(str).str.strip().value_counts(dropna=False).reset_index()
    vc.columns = [name, "Count"]
    if n_total is None:
        n_total = int(vc["Count"].sum())
    vc["Percent"] = (vc["Count"] / n_total * 100).round(3) if n_total else 0
    return vc


def split_review_reasons(df: pd.DataFrame) -> pd.DataFrame:
    ctr = Counter()
    if "Review_Reason" not in df.columns:
        return pd.DataFrame(columns=["Review_Reason_Term", "Count", "Percent"])
    for reason in df["Review_Reason"].fillna("").astype(str):
        for part in [p.strip() for p in reason.split(";") if p.strip()]:
            ctr[part] += 1
    out = pd.DataFrame([{"Review_Reason_Term": k, "Count": v} for k, v in ctr.most_common()])
    if not out.empty:
        out["Percent"] = (out["Count"] / df.shape[0] * 100).round(3)
    return out


def review_mask(df: pd.DataFrame) -> pd.Series:
    if "Review_Required" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["Review_Required"].map(bool_true)


def distribution(s: pd.Series, max_items: int = 8) -> str:
    vals = s.map(clean)
    vals = vals[~vals.map(is_missing)]
    if vals.empty:
        return ""
    vc = vals.value_counts(dropna=False)
    parts = [f"{k}: {int(v)}" for k, v in vc.head(max_items).items()]
    if vc.shape[0] > max_items:
        parts.append(f"... +{vc.shape[0] - max_items} more")
    return " | ".join(parts)


def gse_field_consistency(df: pd.DataFrame) -> pd.DataFrame:
    # Use mapped/post columns when available. This is a non-blocking audit.
    field_candidates = {
        "Organism": ["Organism_Post", "Organism"],
        "Seq_Type": ["Seq_Type_Post", "Seq_Type"],
        "RNA_Library": ["RNA_Library_Post", "RNA_Library"],
        "RNA_Source": ["RNA_Source", "RNA_Source_Mapped", "RNA_Source_Post"],
        "Tissue": ["Tissue_Mapped", "Tissue_Post", "Tissue"],
        "Disease": ["Disease_Mapped", "Disease_Post", "Disease"],
        "Experimental_Setting": ["Experimental_Setting_Post", "Exp_Setting", "Experimental_Setting"],
        "Model_Type": ["Model_Type_Post", "Model_Type"],
        "GSE_Pert": ["GSE_Pert_Post", "GSE_Pert"],
        "GSM_Pert": ["GSM_Pert_Post", "GSM_Pert"],
        "Pert_Type": ["Pert_Type"],
        "Pert": ["Pert_Post", "Pert"],
        "Pert_Dose": ["Pert_Dose_Post", "Pert_Dose"],
        "Pert_Freq": ["Pert_Freq_Post", "Pert_Freq"],
        "Pert_Duration": ["Pert_Duration_Post", "Pert_Duration"],
        "Route_Admin": ["Route_Admin_Post", "Route_Admin"],
        "SampleType": ["SampleType"],
        "Specimen_Type": ["Specimen_Type_Post", "Specimen_Type"],
        "Sex": ["Sex_Post", "Sex"],
        "Age": ["Age_Post", "Age"],
        "Timepoint": ["Timepoint_Post", "Timepoint"],
    }

    stable_like = {"Organism", "GSE_Pert"}
    quasi_stable = {"Seq_Type", "RNA_Library", "Experimental_Setting", "Model_Type"}

    rows = []
    for field, candidates in field_candidates.items():
        col = next((c for c in candidates if c in df.columns), None)
        if col is None:
            continue
        for gse_id, sub in df.groupby("GSE_ID", dropna=False):
            vals = sub[col]
            missing_count = int(vals.map(is_missing).sum())
            nonmiss = vals[~vals.map(is_missing)].map(clean)
            unique_nonmissing = int(nonmiss.nunique(dropna=False))
            dominant = ""
            dominant_count = 0
            dominant_fraction_nonmissing = 0.0
            if not nonmiss.empty:
                vc = nonmiss.value_counts(dropna=False)
                dominant = str(vc.index[0])
                dominant_count = int(vc.iloc[0])
                dominant_fraction_nonmissing = dominant_count / int(vc.sum())
            status = "pass"
            issue = ""
            if missing_count == len(sub):
                status = "info"
                issue = "whole_gse_missing"
            elif missing_count > 0 and unique_nonmissing == 1:
                status = "review"
                issue = "partial_missing_single_nonmissing_value"
            elif missing_count > 0 and unique_nonmissing > 1:
                status = "review"
                issue = "partial_missing_plus_multiple_values"
            elif field in stable_like and unique_nonmissing > 1:
                status = "review"
                issue = "stable_field_multiple_values"
            elif field in quasi_stable and unique_nonmissing > 1 and dominant_fraction_nonmissing < 0.85:
                status = "review"
                issue = "quasi_stable_field_mixed_values"

            if status != "pass":
                rows.append({
                    "GSE_ID": gse_id,
                    "Field": field,
                    "Column_Used": col,
                    "Rows": int(len(sub)),
                    "Missing_Count": missing_count,
                    "Unique_Nonmissing": unique_nonmissing,
                    "Dominant_Value": dominant,
                    "Dominant_Count": dominant_count,
                    "Dominant_Fraction_Nonmissing": round(dominant_fraction_nonmissing, 3),
                    "Issue_Type": issue,
                    "Audit_Status": status,
                    "Distribution": distribution(vals),
                })
    return pd.DataFrame(rows)


def cross_field_issues(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    def col(c):
        return c in df.columns

    for idx, r in df.iterrows():
        gse = clean(r.get("GSE_ID"))
        gsm = clean(r.get("GSM_ID"))
        seq = clean(r.get("Seq_Type_Post", r.get("Seq_Type", "")))
        lib = clean(r.get("RNA_Library_Post", r.get("RNA_Library", "")))
        rna = clean(r.get("RNA_Source", r.get("RNA_Source_Mapped", r.get("RNA_Source_Post", ""))))
        tissue = clean(r.get("Tissue_Mapped", r.get("Tissue", "")))
        sampletype = clean(r.get("SampleType", ""))
        specimen = clean(r.get("Specimen_Type_Post", r.get("Specimen_Type", "")))
        pert_type = clean(r.get("Pert_Type", ""))
        pert = clean(r.get("Pert_Post", r.get("Pert", "")))
        cid = clean(r.get("CP_CID", ""))
        smiles = clean(r.get("CP_CanonicalSMILES", ""))

        def add(rule_id, severity, fields, reason):
            rows.append({
                "GSE_ID": gse, "GSM_ID": gsm, "Rule_ID": rule_id,
                "Severity": severity, "Fields": fields, "Reason": reason
            })

        if seq == "Other" and not is_missing(lib):
            add("CF001", "High", "Seq_Type; RNA_Library", "Seq_Type is Other but RNA_Library is non-missing.")
        if seq in {"SC-RNA", "BULK-RNA"} and is_missing(lib):
            add("CF002", "Medium", "Seq_Type; RNA_Library", "RNA assay has missing RNA_Library.")
        if rna.lower().startswith("cell line:") and sampletype.lower() != "cell line" and specimen.lower() != "cell line":
            add("CF010", "High", "RNA_Source; SampleType; Specimen_Type", "RNA_Source indicates cell line but SampleType/Specimen_Type do not.")
        if not is_missing(rna) and rna.lower().startswith("tissue:") and is_missing(tissue):
            add("CF013", "Medium", "RNA_Source; Tissue", "RNA_Source indicates tissue source but Tissue is missing after mapping.")
        if pert_type == "CP" and (is_missing(cid) or is_missing(smiles)):
            add("CF030", "High", "Pert_Type; CP_CID; CP_CanonicalSMILES", "CP sample lacks valid CID or SMILES.")
        if pert_type in {"NA", "CTL"} and not is_missing(pert) and pert.lower() not in {"control", "vehicle", "untreated", "mock", "none", "no treatment"}:
            add("CF031", "Medium", "Pert_Type; Pert", "Pert_Type is NA/CTL but Pert contains a non-control value.")
    return pd.DataFrame(rows)


def pert_parameter_consistency(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    group_cols = [c for c in ["GSE_ID", "Pert_Post", "Pert_Type"] if c in df.columns]
    if "GSE_ID" not in group_cols or "Pert_Post" not in group_cols:
        return pd.DataFrame()
    fields = [c for c in ["Pert_Dose_Post", "Pert_Freq_Post", "Pert_Duration_Post"] if c in df.columns]
    for keys, sub in df.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        keydict = dict(zip(group_cols, keys))
        if len(sub) < 2:
            continue
        for field in fields:
            vals = sub[field]
            missing_count = int(vals.map(is_missing).sum())
            nonmiss = vals[~vals.map(is_missing)].map(clean)
            if missing_count == 0 or nonmiss.empty:
                continue
            vc = nonmiss.value_counts(dropna=False)
            unique_nonmissing = int(vc.shape[0])
            issue = "partial_missing_single_value_candidate_fill" if unique_nonmissing == 1 else "partial_missing_multiple_values_review"
            rows.append({
                **keydict,
                "Field": field,
                "Rows": int(len(sub)),
                "Missing_Count": missing_count,
                "Unique_Nonmissing": unique_nonmissing,
                "Dominant_Value": str(vc.index[0]),
                "Dominant_Count": int(vc.iloc[0]),
                "Issue_Type": issue,
                "Distribution": distribution(vals),
                "Missing_GSM_IDs": " | ".join(sub.loc[vals.map(is_missing), "GSM_ID"].astype(str).head(50).tolist()) if "GSM_ID" in sub.columns else "",
            })
    return pd.DataFrame(rows)


def review_terms(df: pd.DataFrame, phrase: str, term_col: str) -> pd.DataFrame:
    if "Review_Reason" not in df.columns or term_col not in df.columns:
        return pd.DataFrame()
    mask = review_mask(df) & df["Review_Reason"].fillna("").astype(str).str.contains(phrase, regex=False)
    sub = df.loc[mask].copy()
    if sub.empty:
        return pd.DataFrame(columns=[term_col, "Rows", "GSE_Count", "Example_GSE_IDs"])
    out = (
        sub.groupby(term_col, dropna=False)
        .agg(
            Rows=("GSM_ID", "size"),
            GSE_Count=("GSE_ID", lambda x: x.astype(str).nunique()),
            Example_GSE_IDs=("GSE_ID", lambda x: " | ".join(list(dict.fromkeys(x.astype(str).tolist()))[:8])),
        )
        .reset_index()
        .sort_values("Rows", ascending=False)
    )
    return out


def merge_suffix(workdir: Path, run1: str, run2: str, suffix: str, out_prefix: str, outputs_dir: Path) -> Path | None:
    fp1 = outputs_dir / f"{run1}_{suffix}.xlsx"
    fp2 = outputs_dir / f"{run2}_{suffix}.xlsx"
    if not fp1.exists() or not fp2.exists():
        print(f"[SKIP] Missing {suffix}: {fp1.exists()} {fp2.exists()}")
        return None
    d1 = pd.read_excel(fp1, dtype=object, engine="openpyxl")
    d2 = pd.read_excel(fp2, dtype=object, engine="openpyxl")
    d1.insert(0, "Source_Run", run1)
    d2.insert(0, "Source_Run", run2)
    merged = pd.concat([d1, d2], ignore_index=True, sort=False)
    out = outputs_dir / f"{out_prefix}_{suffix}.xlsx"
    merged.to_excel(out, index=False)
    print(f"[SAVED] {suffix}: {out} rows={merged.shape[0]} cols={merged.shape[1]}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default=".")
    ap.add_argument("--run1", required=True)
    ap.add_argument("--run2", required=True)
    ap.add_argument("--out-prefix", default="GEOMeta_May2026_Homo_sapiens_AllSamples")
    args = ap.parse_args()

    workdir = Path(args.workdir).resolve()
    outputs_dir = workdir / "artifacts" / "outputs"
    review_dir = workdir / "artifacts" / "review_queue"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)

    suffixes = [
        "stage3_mapped",
        "stage3_mapped_filtered",
        "stage3_final_release",
        "stage3_cp_perturbation_release",
    ]
    merged_paths = {}
    for suffix in suffixes:
        path = merge_suffix(workdir, args.run1, args.run2, suffix, args.out_prefix, outputs_dir)
        if path:
            merged_paths[suffix] = path

    mapped_path = merged_paths.get("stage3_mapped")
    if mapped_path is None:
        raise FileNotFoundError("Merged stage3_mapped file was not created; cannot run audit.")

    df = pd.read_excel(mapped_path, dtype=object, engine="openpyxl")
    n = int(df.shape[0])

    summary_rows = [
        {"Metric": "Total rows", "Value": n},
        {"Metric": "Unique GSM_ID", "Value": int(df["GSM_ID"].astype(str).nunique()) if "GSM_ID" in df.columns else "NA"},
        {"Metric": "Duplicated GSM_ID rows", "Value": int(df["GSM_ID"].astype(str).duplicated().sum()) if "GSM_ID" in df.columns else "NA"},
        {"Metric": "Unique GSE_ID", "Value": int(df["GSE_ID"].astype(str).nunique()) if "GSE_ID" in df.columns else "NA"},
    ]
    if "Review_Required" in df.columns:
        n_review = int(review_mask(df).sum())
        summary_rows.extend([
            {"Metric": "Review_Required TRUE rows", "Value": n_review},
            {"Metric": "Review_Required TRUE percent", "Value": round(n_review / n * 100, 3) if n else 0},
        ])

    summary_df = pd.DataFrame(summary_rows)
    review_required_counts = value_counts_df(df["Review_Required"] if "Review_Required" in df.columns else pd.Series(dtype=object), "Review_Required", n)
    review_level_counts = value_counts_df(df["Review_Level"] if "Review_Level" in df.columns else pd.Series(dtype=object), "Review_Level", n)
    review_reason_combo = value_counts_df(df["Review_Reason"] if "Review_Reason" in df.columns else pd.Series(dtype=object), "Review_Reason_Combo", n)
    review_reason_terms = split_review_reasons(df)

    if "GSE_ID" in df.columns:
        rev = review_mask(df)
        by_gse = (
            df.assign(_Review=rev)
            .groupby("GSE_ID", dropna=False)
            .agg(Rows=("GSM_ID", "size"), Review_Rows=("_Review", "sum"))
            .reset_index()
        )
        by_gse["Review_Percent"] = (by_gse["Review_Rows"] / by_gse["Rows"] * 100).round(3)
        by_gse = by_gse.sort_values(["Review_Rows", "Review_Percent"], ascending=False)
    else:
        by_gse = pd.DataFrame()

    rna_terms = review_terms(df, "RNA_Source mapping requires review", "RNA_Source_Post")
    disease_terms = review_terms(df, "Disease mapping requires review", "Disease_Post")
    tissue_terms = review_terms(df, "Tissue mapping requires review", "Tissue_Post")
    cp_terms = review_terms(df, "CP mapping requires review", "Pert_Post")

    gse_consistency = gse_field_consistency(df)
    cross_issues = cross_field_issues(df)
    pert_consistency = pert_parameter_consistency(df)
    duplicate_gsm = df[df["GSM_ID"].astype(str).duplicated(keep=False)].copy() if "GSM_ID" in df.columns else pd.DataFrame()

    audit_path = review_dir / f"{args.out_prefix}_stage3_merged_audit.xlsx"
    with pd.ExcelWriter(audit_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        review_required_counts.to_excel(writer, sheet_name="ReviewRequired_Counts", index=False)
        review_level_counts.to_excel(writer, sheet_name="ReviewLevel_Counts", index=False)
        review_reason_combo.to_excel(writer, sheet_name="ReviewReason_Combos", index=False)
        review_reason_terms.to_excel(writer, sheet_name="ReviewReason_Terms", index=False)
        by_gse.to_excel(writer, sheet_name="Review_by_GSE", index=False)
        rna_terms.to_excel(writer, sheet_name="RNA_Source_Terms", index=False)
        disease_terms.to_excel(writer, sheet_name="Disease_Terms", index=False)
        tissue_terms.to_excel(writer, sheet_name="Tissue_Terms", index=False)
        cp_terms.to_excel(writer, sheet_name="CP_Terms", index=False)
        gse_consistency.to_excel(writer, sheet_name="GSE_Field_Consistency", index=False)
        cross_issues.to_excel(writer, sheet_name="Cross_Field_Issues", index=False)
        pert_consistency.to_excel(writer, sheet_name="Pert_Param_Consistency", index=False)
        duplicate_gsm.to_excel(writer, sheet_name="Duplicate_GSM", index=False)

    print("\n===== SUMMARY =====")
    print(summary_df.to_string(index=False))
    print("\n===== Review_Required counts =====")
    print(review_required_counts.to_string(index=False))
    print("\n===== Review_Reason term counts =====")
    print(review_reason_terms.to_string(index=False))
    print("\n===== Top GSEs by review rows =====")
    print(by_gse.head(20).to_string(index=False) if not by_gse.empty else "No GSE_ID column")
    print("\n===== Top RNA_Source review terms =====")
    print(rna_terms.head(30).to_string(index=False) if not rna_terms.empty else "None")
    print("\n[SAVED] Audit workbook:", audit_path)


if __name__ == "__main__":
    main()
