from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Tuple

import pandas as pd
from .excel_report_utils import format_excel_workbook


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

def _stage3_5_is_blank(x) -> bool:
    v = "" if x is None else str(x).strip()
    return v == "" or v.lower() in {"na", "nan", "none", "unknown", "null"}


def _stage3_5_value_counts_df(
    df: pd.DataFrame,
    column: str,
    label_col: str,
    count_col: str = "Count",
) -> pd.DataFrame:
    if df is None or df.empty or column not in df.columns:
        return pd.DataFrame(columns=[label_col, count_col, "Percent"])

    out = (
        df[column]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace({"": "NA"})
        .value_counts(dropna=False)
        .reset_index()
    )
    out.columns = [label_col, count_col]

    denom = int(out[count_col].sum())
    out["Percent"] = out[count_col].map(lambda x: round((int(x) / denom * 100), 3) if denom else 0)

    return out


def build_stage3_5_pert_dose_duration_summary(
    df_final: pd.DataFrame,
    df_cp_release: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Build summary metrics for final mapped perturbation dose/duration fields.

    NA means no dose/duration information.
    Others means dose/duration information exists but is not a single approved value.
    approved_single means the value passed the final controlled release rule.
    """
    rows = []

    def add_metrics(label: str, df: pd.DataFrame, dose_col: str, duration_col: str):
        n = int(len(df)) if df is not None else 0

        if df is None or df.empty:
            rows.extend(
                [
                    {"Scope": label, "Field": "Mapped_Pert_Dose", "Metric": "Rows", "Value": 0},
                    {"Scope": label, "Field": "Mapped_Pert_Duration", "Metric": "Rows", "Value": 0},
                ]
            )
            return

        for field, col in [
            ("Mapped_Pert_Dose", dose_col),
            ("Mapped_Pert_Duration", duration_col),
        ]:
            if col not in df.columns:
                rows.append({"Scope": label, "Field": field, "Metric": "Column missing", "Value": "True"})
                continue

            s_clean = df[col].fillna("").astype(str).str.strip()
            na_count = int((s_clean.eq("") | s_clean.str.upper().eq("NA")).sum())
            others_count = int(s_clean.eq("Others").sum())
            approved_count = int((~s_clean.isin(["", "NA", "Others"])).sum())

            rows.extend(
                [
                    {"Scope": label, "Field": field, "Metric": "Rows", "Value": n},
                    {"Scope": label, "Field": field, "Metric": "approved_single", "Value": approved_count},
                    {"Scope": label, "Field": field, "Metric": "NA", "Value": na_count},
                    {"Scope": label, "Field": field, "Metric": "Others", "Value": others_count},
                    {
                        "Scope": label,
                        "Field": field,
                        "Metric": "approved_single_percent",
                        "Value": round((approved_count / n * 100), 3) if n else 0,
                    },
                    {
                        "Scope": label,
                        "Field": field,
                        "Metric": "NA_percent",
                        "Value": round((na_count / n * 100), 3) if n else 0,
                    },
                    {
                        "Scope": label,
                        "Field": field,
                        "Metric": "Others_percent",
                        "Value": round((others_count / n * 100), 3) if n else 0,
                    },
                ]
            )

    add_metrics(
        label="stage3_mapped_all_rows",
        df=df_final,
        dose_col="Mapped_Pert_Dose",
        duration_col="Mapped_Pert_Duration",
    )

    if df_cp_release is not None:
        add_metrics(
            label="cp_perturbation_release",
            df=df_cp_release,
            dose_col="Mapped_Pert_Dose",
            duration_col="Mapped_Pert_Duration",
        )

    return pd.DataFrame(rows)


def build_stage3_5_pert_dose_value_counts(df_final: pd.DataFrame) -> pd.DataFrame:
    return _stage3_5_value_counts_df(
        df=df_final,
        column="Mapped_Pert_Dose",
        label_col="Mapped_Pert_Dose",
    )


def build_stage3_5_pert_duration_value_counts(df_final: pd.DataFrame) -> pd.DataFrame:
    return _stage3_5_value_counts_df(
        df=df_final,
        column="Mapped_Pert_Duration",
        label_col="Mapped_Pert_Duration",
    )


def build_stage3_5_pubchem_query_status_summary(df_final: pd.DataFrame) -> pd.DataFrame:
    """
    Summarize PubChem direct-query outcomes.

    Intended interpretation:
      pubchem_direct_title / synonym: accepted
      pubchem_direct_not_found: manual compound-name review
      pubchem_direct_server_busy / request_failed / timeout: rerun PubChem later
      pubchem_direct_unverified: manual review
      pubchem_direct_no_query: fix/query review
    """
    if df_final is None or df_final.empty:
        return pd.DataFrame(columns=["CP_Query_Status", "Count", "Percent", "Action"])

    if "CP_Query_Status" not in df_final.columns:
        return pd.DataFrame(columns=["CP_Query_Status", "Count", "Percent", "Action"])

    work = df_final.copy()

    if "Pert_Type" in work.columns:
        work = work.loc[
            work["Pert_Type"].fillna("").astype(str).str.strip().str.upper().eq("CP")
        ].copy()

    status_counts = _stage3_5_value_counts_df(
        df=work,
        column="CP_Query_Status",
        label_col="CP_Query_Status",
    )

    action_map = {
        "pubchem_direct_title": "Accept PubChem match",
        "pubchem_direct_synonym": "Accept PubChem match",
        "pubchem_direct_not_found": "Manual compound-name verification",
        "pubchem_direct_server_busy": "Rerun PubChem mapping later",
        "pubchem_direct_request_failed": "Rerun PubChem mapping later",
        "pubchem_direct_timeout": "Rerun PubChem mapping later",
        "pubchem_direct_unverified": "Manual review; CID returned but title/synonym did not verify",
        "pubchem_direct_no_query": "Manual review; no valid query term",
        "": "Not available",
        "NA": "Not available",
    }

    if not status_counts.empty:
        status_counts["Action"] = status_counts["CP_Query_Status"].map(
            lambda x: action_map.get(str(x).strip(), "Review")
        )

    return status_counts


def build_stage3_5_pubchem_failed_terms(df_final: pd.DataFrame) -> pd.DataFrame:
    """
    Build term-level PubChem failure/retry report.

    One row per Pert_Post / CP_Query_Status combination.
    """
    cols = [
        "Pert_Post",
        "CP_Query_Status",
        "CP_Query_Error",
        "CP_Query_Attempted_Term",
        "CP_Map_Method",
        "CP_MatchType",
        "CP_Map_Explanation",
        "GSE_ID",
        "GSM_ID",
    ]

    if df_final is None or df_final.empty:
        return pd.DataFrame(columns=cols)

    work = df_final.copy()

    required = {"Pert_Post", "Pert_Type", "CP_Query_Status"}
    if not required.issubset(work.columns):
        return pd.DataFrame(columns=cols)

    cp_mask = work["Pert_Type"].fillna("").astype(str).str.strip().str.upper().eq("CP")

    failed_statuses = {
        "pubchem_direct_not_found",
        "pubchem_direct_server_busy",
        "pubchem_direct_request_failed",
        "pubchem_direct_timeout",
        "pubchem_direct_unverified",
        "pubchem_direct_no_query",
    }

    failed = work.loc[
        cp_mask
        & work["CP_Query_Status"].fillna("").astype(str).str.strip().isin(failed_statuses)
    ].copy()

    if failed.empty:
        return pd.DataFrame(
            columns=[
                "Pert_Post",
                "CP_Query_Status",
                "Recommended_Action",
                "Sample_Count",
                "GSE_Count",
                "Example_GSE_IDs",
                "Example_GSM_IDs",
                "CP_Query_Attempted_Term",
                "CP_Query_Error",
                "CP_Map_Method",
                "CP_MatchType",
                "CP_Map_Explanation",
            ]
        )

    action_map = {
        "pubchem_direct_not_found": "Manual compound-name verification",
        "pubchem_direct_server_busy": "Rerun PubChem mapping later",
        "pubchem_direct_request_failed": "Rerun PubChem mapping later",
        "pubchem_direct_timeout": "Rerun PubChem mapping later",
        "pubchem_direct_unverified": "Manual review; CID returned but title/synonym did not verify",
        "pubchem_direct_no_query": "Manual review; no valid query term",
    }

    def join_unique(s, n=10):
        vals = [
            str(x).strip()
            for x in s.tolist()
            if not _stage3_5_is_blank(x)
        ]
        vals = sorted(set(vals))
        return " | ".join(vals[:n])

    rows = []

    for (pert_post, status), sub in failed.groupby(["Pert_Post", "CP_Query_Status"], dropna=False):
        rows.append(
            {
                "Pert_Post": pert_post,
                "CP_Query_Status": status,
                "Recommended_Action": action_map.get(str(status).strip(), "Review"),
                "Sample_Count": int(sub["GSM_ID"].astype(str).nunique()) if "GSM_ID" in sub.columns else int(len(sub)),
                "GSE_Count": int(sub["GSE_ID"].astype(str).nunique()) if "GSE_ID" in sub.columns else 0,
                "Example_GSE_IDs": join_unique(sub["GSE_ID"], n=10) if "GSE_ID" in sub.columns else "",
                "Example_GSM_IDs": join_unique(sub["GSM_ID"], n=10) if "GSM_ID" in sub.columns else "",
                "CP_Query_Attempted_Term": join_unique(sub["CP_Query_Attempted_Term"], n=5)
                if "CP_Query_Attempted_Term" in sub.columns
                else "",
                "CP_Query_Error": join_unique(sub["CP_Query_Error"], n=3)
                if "CP_Query_Error" in sub.columns
                else "",
                "CP_Map_Method": join_unique(sub["CP_Map_Method"], n=5)
                if "CP_Map_Method" in sub.columns
                else "",
                "CP_MatchType": join_unique(sub["CP_MatchType"], n=5)
                if "CP_MatchType" in sub.columns
                else "",
                "CP_Map_Explanation": join_unique(sub["CP_Map_Explanation"], n=3)
                if "CP_Map_Explanation" in sub.columns
                else "",
            }
        )

    return (
        pd.DataFrame(rows)
        .sort_values(["Recommended_Action", "Sample_Count", "Pert_Post"], ascending=[True, False, True])
        .reset_index(drop=True)
    )

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
        {
            "Metric": "Rows PASS",
            "Value": int((df.get("Global_QC_Status", pd.Series([], dtype=str)).astype(str) == "PASS").sum()),
            "Status": "INFO",
        },
        {
            "Metric": "Rows REVIEW",
            "Value": int((df.get("Global_QC_Status", pd.Series([], dtype=str)).astype(str) == "REVIEW").sum()),
            "Status": "REVIEW",
        },
        {
            "Metric": "Rows FAIL",
            "Value": int((df.get("Global_QC_Status", pd.Series([], dtype=str)).astype(str) == "FAIL").sum()),
            "Status": "FAIL",
        },
    ]

    if "GSM_ID" in df.columns:
        summary_rows.append(
            {
                "Metric": "Duplicated GSM_ID rows",
                "Value": int(df["GSM_ID"].astype(str).duplicated().sum()),
                "Status": "FAIL if >0",
            }
        )

    if cp_excluded_df is not None:
        summary_rows.append(
            {
                "Metric": "CP rows excluded from structure-ready release",
                "Value": int(len(cp_excluded_df)),
                "Status": "REVIEW",
            }
        )

    review_cols = [
        c
        for c in [
            "GSE_ID",
            "GSM_ID",
            "Global_QC_Status",
            "Review_Required",
            "Review_Level",
            "Review_Reason",
            "Release_Action",
            "Disease_Post",
            "Disease_Mapped",
            "Tissue_Post",
            "Tissue_Mapped",
            "RNA_Source_Post",
            "RNA_Source_Mapped",
            "Pert_Type",
            "Pert_Post",
            "Mapped_Pert_Dose",
            "Mapped_Pert_Duration",
            "CP_PubChem_Name",
            "CP_CID",
            "CP_CanonicalSMILES",
            "CP_Query_Status",
            "CP_Query_Error",
            "CP_Query_Attempted_Term",
            "CP_Map_Method",
            "CP_MatchType",
            "CP_Map_Explanation",
        ]
        if c in df.columns
    ]

    if "Review_Required" in df.columns:
        review_required = (
            df["Review_Required"]
            .fillna(False)
            .astype(str)
            .str.strip()
            .str.upper()
        )
        review_mask = review_required.isin(
            {"TRUE", "1", "YES", "Y", "REVIEW", "REQUIRED"}
        )
        review_queue = df.loc[review_mask, review_cols].copy()
    else:
        review_queue = pd.DataFrame(columns=review_cols)

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

    report = build_mode_a_stage3_5_report(
        df_final,
        df_simple_release,
        df_cp_release,
        cp_excluded_df,
    )

    # ------------------------------------------------------------
    # Add perturbation dose/duration and PubChem query-status
    # summaries to the Stage 3.5 final QC workbook.
    # ------------------------------------------------------------
    pert_dose_duration_summary_df = build_stage3_5_pert_dose_duration_summary(
        df_final=df_final,
        df_cp_release=df_cp_release,
    )

    pert_dose_counts_df = build_stage3_5_pert_dose_value_counts(df_final)
    pert_duration_counts_df = build_stage3_5_pert_duration_value_counts(df_final)

    pubchem_query_status_df = build_stage3_5_pubchem_query_status_summary(df_final)
    pubchem_failed_terms_df = build_stage3_5_pubchem_failed_terms(df_final)

    report["pert_dose_duration"] = pert_dose_duration_summary_df
    report["pert_dose_counts"] = pert_dose_counts_df
    report["pert_duration_counts"] = pert_duration_counts_df
    report["pubchem_query_status"] = pubchem_query_status_df
    report["pubchem_failed_terms"] = pubchem_failed_terms_df

    # ------------------------------------------------------------
    # Also add compact headline metrics to Final_QC_Summary.
    # ------------------------------------------------------------
    def _count_approved_single(df: pd.DataFrame, col: str) -> int:
        if df is None or df.empty or col not in df.columns:
            return 0
        s = df[col].fillna("").astype(str).str.strip()
        return int((~s.isin(["", "NA", "Others"])).sum())

    def _count_equal(df: pd.DataFrame, col: str, value: str) -> int:
        if df is None or df.empty or col not in df.columns:
            return 0
        return int(df[col].fillna("").astype(str).str.strip().eq(value).sum())

    def _count_pubchem_statuses(df: pd.DataFrame, statuses: set[str]) -> int:
        if df is None or df.empty or "CP_Query_Status" not in df.columns:
            return 0

        work = df.copy()

        if "Pert_Type" in work.columns:
            work = work.loc[
                work["Pert_Type"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.upper()
                .eq("CP")
            ].copy()

        return int(
            work["CP_Query_Status"]
            .fillna("")
            .astype(str)
            .str.strip()
            .isin(statuses)
            .sum()
        )

    extra_summary_rows = pd.DataFrame(
        [
            {
                "Metric": "Mapped_Pert_Dose approved single values",
                "Value": _count_approved_single(df_final, "Mapped_Pert_Dose"),
                "Status": "INFO",
            },
            {
                "Metric": "Mapped_Pert_Dose NA",
                "Value": _count_equal(df_final, "Mapped_Pert_Dose", "NA"),
                "Status": "INFO",
            },
            {
                "Metric": "Mapped_Pert_Dose Others",
                "Value": _count_equal(df_final, "Mapped_Pert_Dose", "Others"),
                "Status": "REVIEW",
            },
            {
                "Metric": "Mapped_Pert_Duration approved single values",
                "Value": _count_approved_single(df_final, "Mapped_Pert_Duration"),
                "Status": "INFO",
            },
            {
                "Metric": "Mapped_Pert_Duration NA",
                "Value": _count_equal(df_final, "Mapped_Pert_Duration", "NA"),
                "Status": "INFO",
            },
            {
                "Metric": "Mapped_Pert_Duration Others",
                "Value": _count_equal(df_final, "Mapped_Pert_Duration", "Others"),
                "Status": "REVIEW",
            },
            {
                "Metric": "PubChem query statuses requiring rerun later",
                "Value": _count_pubchem_statuses(
                    df_final,
                    {
                        "pubchem_direct_server_busy",
                        "pubchem_direct_request_failed",
                        "pubchem_direct_timeout",
                    },
                ),
                "Status": "RETRY",
            },
            {
                "Metric": "PubChem query statuses requiring manual review",
                "Value": _count_pubchem_statuses(
                    df_final,
                    {
                        "pubchem_direct_not_found",
                        "pubchem_direct_unverified",
                        "pubchem_direct_no_query",
                    },
                ),
                "Status": "REVIEW",
            },
        ]
    )

    if "Final_QC_Summary" in report:
        report["Final_QC_Summary"] = pd.concat(
            [report["Final_QC_Summary"], extra_summary_rows],
            ignore_index=True,
        )
    else:
        report["Final_QC_Summary"] = extra_summary_rows

    fp = review_dir / f"{cfg.run_version}_stage3_5_final_qc_report.xlsx"

    with pd.ExcelWriter(fp, engine="openpyxl") as writer:
        for sheet, d in report.items():
            if d is None:
                d = pd.DataFrame()
            d.to_excel(writer, sheet_name=sheet[:31], index=False)

    format_excel_workbook(fp)

    return fp
