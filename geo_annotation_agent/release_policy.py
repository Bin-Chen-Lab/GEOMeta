from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Tuple

import pandas as pd


MISSING_TOKENS = {"", "na", "n/a", "nan", "none", "null", "unknown", "not specified", "not reported", "not available", "not applicable"}


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


def is_missing_value(x: Any) -> bool:
    return norm_value(x) in MISSING_TOKENS


def boolish(x: Any) -> bool:
    v = norm_value(x)
    return v in {"true", "1", "yes", "y", "review", "required"}


def join_unique(values: Iterable[Any], sep: str = "; ") -> str:
    out = []
    seen = set()
    for v in values:
        s = clean_value(v)
        if not s:
            continue
        if s not in seen:
            out.append(s)
            seen.add(s)
    return sep.join(out)


def normalize_pubchem_cid(x: Any) -> str:
    v = clean_value(x)
    if is_missing_value(v):
        return ""
    v = re.sub(r"^https?://pubchem\.ncbi\.nlm\.nih\.gov/compound/", "", v, flags=re.I).strip().strip("/")
    if re.fullmatch(r"\d+", v):
        return v
    try:
        f = float(v)
        if f.is_integer():
            return str(int(f))
    except Exception:
        pass
    return v


def has_valid_cp_cid(x: Any) -> bool:
    return bool(normalize_pubchem_cid(x))


def has_valid_cp_smiles(x: Any) -> bool:
    return not is_missing_value(x)


# -----------------------------------------------------------------------------
# Mode A policy flags
# -----------------------------------------------------------------------------

def initialize_mode_a_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add non-blocking automated-release QC/provenance columns if absent."""
    out = df.copy()
    defaults = {
        "Global_QC_Status": "PASS",
        "Review_Required": False,
        "Review_Level": "None",
        "Review_Reason": "",
        "Release_Action": "Include",
        "Correction_Source": "Stage1 raw / deterministic pipeline",
        "Correction_Confidence": "",
        "Correction_Reason": "",
    }
    for c, v in defaults.items():
        if c not in out.columns:
            out[c] = v
    return out


def _append_flag(out: pd.DataFrame, idx: Any, *, level: str, reason: str, action: str = "Include") -> None:
    current_level = clean_value(out.at[idx, "Review_Level"])
    severity_rank = {"None": 0, "Low": 1, "Medium": 2, "High": 3, "Critical": 4}
    if severity_rank.get(level, 0) > severity_rank.get(current_level, 0):
        out.at[idx, "Review_Level"] = level
    out.at[idx, "Review_Required"] = True
    out.at[idx, "Review_Reason"] = join_unique([out.at[idx, "Review_Reason"], reason])
    if level == "Critical":
        out.at[idx, "Global_QC_Status"] = "FAIL"
        out.at[idx, "Release_Action"] = action
    elif clean_value(out.at[idx, "Global_QC_Status"]) != "FAIL":
        out.at[idx, "Global_QC_Status"] = "REVIEW"
        out.at[idx, "Release_Action"] = action


def add_stage1_qa3_mode_a_flags(
    df_stage1: pd.DataFrame,
    applied_df: pd.DataFrame | None = None,
    human_df: pd.DataFrame | None = None,
    gse_col: str = "GSE_ID",
    gsm_col: str = "GSM_ID",
) -> pd.DataFrame:
    """Add row-level provenance/review flags after QA3 without blocking the run."""
    out = initialize_mode_a_columns(df_stage1)
    for c, v in {
        "Stage1_QA3_Correction_Applied": False,
        "Stage1_QA3_Corrected_Fields": "",
        "Stage1_QA3_Review_Required": False,
        "Stage1_QA3_Review_Reason": "",
    }.items():
        if c not in out.columns:
            out[c] = v

    if applied_df is not None and not applied_df.empty:
        for _, r in applied_df.iterrows():
            if clean_value(r.get("Apply_Status", "")) != "Applied":
                continue
            gse_id = clean_value(r.get("GSE_ID", ""))
            gsm_id = clean_value(r.get("GSM_ID", ""))
            field = clean_value(r.get("Field", ""))
            reason = clean_value(r.get("Apply_Reason", ""))
            mask = out[gse_col].astype(str).str.strip().eq(gse_id) & out[gsm_col].astype(str).str.strip().eq(gsm_id)
            for idx in out.index[mask]:
                out.at[idx, "Stage1_QA3_Correction_Applied"] = True
                out.at[idx, "Stage1_QA3_Corrected_Fields"] = join_unique([out.at[idx, "Stage1_QA3_Corrected_Fields"], field])
                out.at[idx, "Correction_Source"] = join_unique([out.at[idx, "Correction_Source"], "Stage1 QA3 high-confidence evidence rescue"])
                out.at[idx, "Correction_Confidence"] = join_unique([out.at[idx, "Correction_Confidence"], "high"])
                out.at[idx, "Correction_Reason"] = join_unique([out.at[idx, "Correction_Reason"], reason])

    if human_df is not None and not human_df.empty:
        for _, r in human_df.iterrows():
            gse_id = clean_value(r.get("GSE_ID", ""))
            gsm_id = clean_value(r.get("GSM_ID", ""))
            field = clean_value(r.get("LLM_Target_Field", r.get("Target_Field", "")))
            reason = clean_value(r.get("Apply_Reason", r.get("LLM_Reason", r.get("Issue_Type", "QA3 unresolved task"))))
            if not gse_id:
                continue
            if gsm_id:
                mask = out[gse_col].astype(str).str.strip().eq(gse_id) & out[gsm_col].astype(str).str.strip().eq(gsm_id)
            else:
                mask = out[gse_col].astype(str).str.strip().eq(gse_id)
            for idx in out.index[mask]:
                out.at[idx, "Stage1_QA3_Review_Required"] = True
                out.at[idx, "Stage1_QA3_Review_Reason"] = join_unique([out.at[idx, "Stage1_QA3_Review_Reason"], f"{field}: {reason}" if field else reason])
                _append_flag(out, idx, level="Medium", reason=f"Stage1 QA3 unresolved/review task: {field or 'unspecified field'}", action="Include")

    return out


# -----------------------------------------------------------------------------
# RNA source mapping for Mode A
# -----------------------------------------------------------------------------

def normalize_rna_source_key(x: Any) -> str:
    return re.sub(r"\s+", " ", clean_value(x).lower()).strip()


def apply_mode_a_rna_source_mapping(
    df: pd.DataFrame,
    workdir: str | Path,
    source_col: str = "RNA_Source_Post",
    mapping_relpath: str = "mappings/rna_source/RNA_Source_mappings.xlsx",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Apply reviewed RNA-source mapping in non-blocking Mode A.

    Priority:
      1. Exact normalized lookup from mappings/rna_source/RNA_Source_mappings.xlsx.
      2. If the source term already uses a controlled-looking prefix (Cell Line:, Tissue:,
         Other), keep it as a deterministic fallback and flag as candidate-reviewed.
      3. Otherwise leave RNA_Source_Mapped blank and flag for review.
    """
    out = df.copy()
    if source_col not in out.columns:
        out[source_col] = ""

    mapping_path = Path(workdir) / mapping_relpath
    lookup = {}
    if mapping_path.exists():
        try:
            mdf = pd.read_excel(mapping_path, sheet_name="Final_Data", dtype=str, keep_default_na=False)
        except Exception:
            mdf = pd.read_excel(mapping_path, sheet_name=0, dtype=str, keep_default_na=False)
        if {"Original_RNA_Source_Term", "RNA_Source_Mapped"}.issubset(mdf.columns):
            for _, r in mdf.iterrows():
                key = normalize_rna_source_key(r.get("Original_RNA_Source_Term", ""))
                if key and key not in lookup:
                    lookup[key] = clean_value(r.get("RNA_Source_Mapped", ""))

    keys = out[source_col].map(normalize_rna_source_key)
    out["RNA_Source_Pre_Key"] = keys
    out["RNA_Source_Mapped"] = keys.map(lookup).fillna("")
    out["RNA_Source_Mapping_Status"] = "Unmapped: needs review"
    out["RNA_Source_Mapping_Method"] = ""
    out["RNA_Source_Mapping_Confidence"] = ""
    out["RNA_Source_Mapping_Reason"] = ""

    mapped_mask = keys.isin(set(lookup.keys()))
    out.loc[mapped_mask, "RNA_Source_Mapping_Status"] = "Mapped: reviewed reusable mapping"
    out.loc[mapped_mask, "RNA_Source_Mapping_Method"] = "Reviewed mapping file"
    out.loc[mapped_mask, "RNA_Source_Mapping_Confidence"] = "reviewed"
    out.loc[mapped_mask, "RNA_Source_Mapping_Reason"] = "Matched Original_RNA_Source_Term in reusable RNA source mapping file."

    # Conservative deterministic fallback only when the Stage2 term already has a controlled-looking label.
    fallback_mask = (~mapped_mask) & out["RNA_Source_Mapped"].astype(str).str.strip().eq("")
    source_vals = out[source_col].astype(str).str.strip()
    controlled_like = source_vals.str.match(r"^(Cell Line:|Tissue:|Other$)", case=False, na=False)
    fb = fallback_mask & controlled_like
    out.loc[fb, "RNA_Source_Mapped"] = source_vals[fb]
    out.loc[fb, "RNA_Source_Mapping_Status"] = "Mapped: deterministic controlled-label fallback"
    out.loc[fb, "RNA_Source_Mapping_Method"] = "Mode A deterministic fallback"
    out.loc[fb, "RNA_Source_Mapping_Confidence"] = "medium"
    out.loc[fb, "RNA_Source_Mapping_Reason"] = "Stage2 RNA_Source_Post already used a controlled-looking RNA source label."

    out["RNA_Source_Review_Required"] = out["RNA_Source_Mapped"].astype(str).str.strip().eq("") & ~out[source_col].map(is_missing_value)

    review = out.loc[out["RNA_Source_Review_Required"].astype(bool)].copy()
    if review.empty:
        review_queue = pd.DataFrame(columns=[source_col, "n_rows", "Example_GSE_ID", "Example_GSM_ID", "Reason"])
    else:
        agg = {"n_rows": (source_col, "size")}
        if "GSE_ID" in review.columns:
            agg["Example_GSE_ID"] = ("GSE_ID", lambda x: " | ".join(x.dropna().astype(str).head(5)))
        if "GSM_ID" in review.columns:
            agg["Example_GSM_ID"] = ("GSM_ID", lambda x: " | ".join(x.dropna().astype(str).head(5)))
        review_queue = review.groupby(source_col, dropna=False).agg(**agg).reset_index()
        review_queue["Reason"] = "Unmapped RNA_Source_Post term in automated Mode A; final output is flagged but pipeline continues."

    return out, review_queue


# -----------------------------------------------------------------------------
# Stage 3.5 final QC and CP release policy
# -----------------------------------------------------------------------------

def add_mode_a_final_qc_flags(df_final: pd.DataFrame) -> pd.DataFrame:
    out = initialize_mode_a_columns(df_final)

    # Structural identity checks.
    for idx, row in out.iterrows():
        if is_missing_value(row.get("GSM_ID")) or is_missing_value(row.get("GSE_ID")):
            _append_flag(out, idx, level="Critical", reason="Missing GSM_ID or GSE_ID.", action="Exclude")

    if "GSM_ID" in out.columns:
        dup_mask = out["GSM_ID"].astype(str).str.strip().duplicated(keep=False)
        for idx in out.index[dup_mask]:
            _append_flag(out, idx, level="Critical", reason="Duplicated GSM_ID in final mapped table.", action="Exclude")

    for idx, row in out.iterrows():
        # Mapping completeness checks.
        if not is_missing_value(row.get("Disease_Post")) and is_missing_value(row.get("Disease_Mapped")):
            _append_flag(out, idx, level="High", reason="Disease_Post present but Disease_Mapped is missing.")
        if boolish(row.get("Disease_Review_Required")):
            _append_flag(out, idx, level="Medium", reason="Disease mapping requires review.")
        if not is_missing_value(row.get("Tissue_Post")) and is_missing_value(row.get("Tissue_Mapped")):
            _append_flag(out, idx, level="High", reason="Tissue_Post present but Tissue_Mapped is missing.")
        if boolish(row.get("RNA_Source_Review_Required")):
            _append_flag(out, idx, level="Medium", reason="RNA_Source mapping requires review.")
        if not is_missing_value(row.get("RNA_Source_Post")) and is_missing_value(row.get("RNA_Source_Mapped")):
            _append_flag(out, idx, level="Medium", reason="RNA_Source_Post present but RNA_Source_Mapped is missing.")

        seq = clean_value(row.get("Seq_Type_Post")).upper()
        if seq in {"BULK-RNA", "SC-RNA"} and is_missing_value(row.get("RNA_Library_Post")):
            _append_flag(out, idx, level="Medium", reason="RNA sequencing row has missing RNA_Library.")

        pert_type = clean_value(row.get("Pert_Type")).upper()
        if pert_type == "CP" and not (has_valid_cp_cid(row.get("CP_CID")) and has_valid_cp_smiles(row.get("CP_CanonicalSMILES"))):
            _append_flag(out, idx, level="Medium", reason="CP sample lacks valid CP_CID and/or CP_CanonicalSMILES; excluded from CP structure-ready release.")
        if pert_type != "CP" and (has_valid_cp_cid(row.get("CP_CID")) or has_valid_cp_smiles(row.get("CP_CanonicalSMILES"))):
            _append_flag(out, idx, level="Low", reason="Non-CP row contains compound structure fields.")

    return out


def build_mode_a_cp_release(df_final: pd.DataFrame, cp_release_cols: list[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Structure-ready CP release: non-blocking, strict inclusion, explicit excluded queue."""
    df = df_final.copy()
    for c in cp_release_cols:
        if c not in df.columns:
            df[c] = ""

    pt = df["Pert_Type"].astype(str).str.upper().str.strip() if "Pert_Type" in df.columns else pd.Series("", index=df.index)
    valid_cp = pt.eq("CP") & df["CP_CID"].map(has_valid_cp_cid) & df["CP_CanonicalSMILES"].map(has_valid_cp_smiles)
    selected_gses = set(df.loc[valid_cp, "GSE_ID"].dropna().astype(str)) if "GSE_ID" in df.columns else set()
    in_selected_gse = df["GSE_ID"].astype(str).isin(selected_gses) if "GSE_ID" in df.columns else pd.Series(False, index=df.index)
    keep = in_selected_gse & (pt.eq("CTL") | valid_cp)

    release = df.loc[keep, cp_release_cols].copy()

    excluded = df.loc[in_selected_gse & ~keep].copy()
    if not excluded.empty:
        excluded["CP_Release_Exclusion_Reason"] = "Within selected CP GSE, row is neither CTL nor CP with valid CP_CID + CP_CanonicalSMILES."
    missing_structure = df.loc[pt.eq("CP") & ~valid_cp].copy()
    if not missing_structure.empty:
        missing_structure["CP_Release_Exclusion_Reason"] = "CP row missing valid CP_CID and/or CP_CanonicalSMILES."
    excluded = pd.concat([excluded, missing_structure], axis=0).drop_duplicates(subset=[c for c in ["GSE_ID", "GSM_ID"] if c in df.columns])

    return release, excluded


def build_mode_a_stage3_5_report(
    df_final: pd.DataFrame,
    df_simple_release: pd.DataFrame,
    df_cp_release: pd.DataFrame,
    cp_excluded_df: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    df = df_final.copy()
    summary_rows = [
        {"Metric": "Stage3 mapped rows", "Value": int(len(df)), "Status": "INFO"},
        {"Metric": "Final release rows", "Value": int(len(df_simple_release)), "Status": "INFO"},
        {"Metric": "CP release rows", "Value": int(len(df_cp_release)), "Status": "INFO"},
        {"Metric": "Rows PASS", "Value": int((df.get("Global_QC_Status", pd.Series([], dtype=str)).astype(str) == "PASS").sum()), "Status": "INFO"},
        {"Metric": "Rows REVIEW", "Value": int((df.get("Global_QC_Status", pd.Series([], dtype=str)).astype(str) == "REVIEW").sum()), "Status": "REVIEW"},
        {"Metric": "Rows FAIL", "Value": int((df.get("Global_QC_Status", pd.Series([], dtype=str)).astype(str) == "FAIL").sum()), "Status": "FAIL"},
    ]
    if "GSM_ID" in df.columns:
        summary_rows.append({"Metric": "Duplicated GSM_ID rows", "Value": int(df["GSM_ID"].astype(str).duplicated().sum()), "Status": "FAIL if >0"})
    if cp_excluded_df is not None:
        summary_rows.append({"Metric": "CP rows excluded from structure-ready release", "Value": int(len(cp_excluded_df)), "Status": "REVIEW"})

    review_cols = [c for c in [
        "GSE_ID", "GSM_ID", "Global_QC_Status", "Review_Required", "Review_Level", "Review_Reason", "Release_Action",
        "Disease_Post", "Disease_Mapped", "Tissue_Post", "Tissue_Mapped", "RNA_Source_Post", "RNA_Source_Mapped",
        "Pert_Type", "Pert_Post", "CP_CID", "CP_CanonicalSMILES",
    ] if c in df.columns]
    review_queue = df.loc[df.get("Review_Required", False).astype(bool), review_cols].copy() if "Review_Required" in df.columns else pd.DataFrame(columns=review_cols)

    return {
        "Final_QC_Summary": pd.DataFrame(summary_rows),
        "Final_Review_Queue": review_queue,
        "CP_Release_Excluded": cp_excluded_df if cp_excluded_df is not None else pd.DataFrame(),
    }


def save_mode_a_stage3_5_report(
    cfg: Any,
    review_dir: str | Path,
    df_final: pd.DataFrame,
    df_simple_release: pd.DataFrame,
    df_cp_release: pd.DataFrame,
    cp_excluded_df: pd.DataFrame | None = None,
) -> Path:
    review_dir = Path(review_dir)
    review_dir.mkdir(parents=True, exist_ok=True)
    report = build_mode_a_stage3_5_report(df_final, df_simple_release, df_cp_release, cp_excluded_df)
    fp = review_dir / f"{cfg.run_version}_stage3_5_final_qc_report.xlsx"
    with pd.ExcelWriter(fp, engine="openpyxl") as writer:
        for sheet, d in report.items():
            d.to_excel(writer, sheet_name=sheet[:31], index=False)
    return fp
