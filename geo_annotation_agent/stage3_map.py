from __future__ import annotations

import json
import re
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

try:
    from rapidfuzz import fuzz
except Exception:
    fuzz = None

from .json_safety import safe_json_loads_with_repair
from .llm_client import make_llm_from_config
from .token_budget import TokenBudget, check_messages_token_budget
from .release_policy import (
    apply_mode_a_rna_source_mapping,
    add_mode_a_final_qc_flags,
    build_mode_a_cp_release,
    build_mode_a_stage3_5_report,
    save_mode_a_stage3_5_report,
)

from .stage4_validate_release import validate_stage3_release_qa


# -------------------------
# Helpers
# -------------------------
def _s(x) -> str:
    if x is None:
        return "NA"
    try:
        if isinstance(x, float) and x != x:
            return "NA"
    except Exception:
        pass

    v = str(x).strip()
    return "NA" if v.lower() in {"", "nan", "none"} else v


def _blank(x) -> str:
    v = _s(x)
    return "" if v in {"NA", "Unknown"} else v


def _mapped_na(x: Any) -> str:
    """Normalize final mapped vocabulary values.

    Final mapped fields use explicit NA for reviewed-but-unmappable or
    not-applicable values. Empty cells are reserved for pre-QA/unprocessed
    values and should not survive into mapped release outputs.
    """
    v = _s(x)
    return "NA" if v in {"", "NA", "Unknown"} else v


def _broad_category_or_na(x: Any) -> str:
    v = _blank(x)
    return v if v else "NA"

def _infer_broad_category_from_disease_text(*values: Any) -> str:
    text = " ".join(_s(v) for v in values).lower()

    if re.search(
        r"\b(cancer|carcinoma|adenocarcinoma|neoplasm|neoplasms|tumou?r|"
        r"melanoma|sarcoma|lymphoma|leukemia|glioma|blastoma)\b",
        text,
    ):
        return "Oncology"

    return ""


def blank_release_na(df_out: pd.DataFrame) -> pd.DataFrame:
    """Legacy display helper retained for compatibility.

    Earlier releases blanked NA-style values in public files. For release QA,
    final mapped fields should keep explicit NA so that reviewed-but-unmappable
    values are distinguishable from unprocessed blanks. Unknown is normalized to
    NA instead of being blanked.
    """
    df_out = df_out.copy()

    # Normalize Unknown only in string-like columns. Avoid DataFrame.replace()
    # here because pandas is deprecating silent dtype downcasting.
    for col in df_out.select_dtypes(include=["object", "string"]).columns:
        unknown_mask = (
            df_out[col]
            .astype("string")
            .eq("Unknown")
            .fillna(False)
        )
        if unknown_mask.any():
            df_out.loc[unknown_mask, col] = "NA"

    return df_out


def _is_release_blank(x: Any) -> bool:
    v = "" if x is None else str(x).strip()
    return v == "" or v.lower() in {"nan", "none", "na", "unknown"}


def _first_nonblank(*values: Any) -> str:
    for v in values:
        if not _is_release_blank(v):
            return str(v).strip()
    return ""


def clean_release_review_reason(x: Any) -> str:
    """Normalize final-release review reasons.

    Keep the public final release concise:
    - remove placeholder NA/Unknown reasons
    - remove redundant RNA_Source_Post-vs-RNA_Source_Mapped detail
    - collapse implementation-specific mapping messages to domain-level review flags
    - de-duplicate reasons while preserving order
    """
    raw = "" if x is None else str(x)
    raw = raw.replace(
        "CP sample lacks valid CP_CID and/or CP_CanonicalSMILES; excluded from CP structure-ready release.",
        "CP mapping requires review.",
    )
    raw = raw.replace(
        "Disease_Post present but Disease_Mapped is missing.",
        "Disease mapping requires review.",
    )
    raw = raw.replace(
        "Tissue_Post present but Tissue_Mapped is missing.",
        "Tissue mapping requires review.",
    )
    raw = raw.replace(
        "RNA_Source_Post present but RNA_Source_Mapped is missing.",
        "",
    )

    parts: List[str] = []
    seen = set()
    for part in raw.split(";"):
        item = part.strip()
        if not item or item.lower() in {"na", "unknown", "nan", "none"}:
            continue
        if item not in seen:
            parts.append(item)
            seen.add(item)

    return "; ".join(parts)


def add_release_display_columns(df_out: pd.DataFrame) -> pd.DataFrame:
    """Add the public RNA_Source column used in all Stage 3 outputs.

    Public rule:
    - RNA_Source is copied directly from RNA_Source_Mapped.
    - Do not use RNA_Source_Post, RNA_Source_Pre, or RNA_Source_Final in release outputs.
    - If RNA_Source_Mapped is blank/NA/Unknown, RNA_Source is blank.
    """
    df_out = df_out.copy()

    if "RNA_Source_Mapped" in df_out.columns:
        df_out["RNA_Source"] = df_out["RNA_Source_Mapped"].map(
            lambda x: "" if _is_release_blank(x) else str(x).strip()
        )
    else:
        df_out["RNA_Source"] = ""

    # Remove legacy/display-only field if present.
    if "RNA_Source_Final" in df_out.columns:
        df_out = df_out.drop(columns=["RNA_Source_Final"])

    if "Review_Reason" in df_out.columns:
        df_out["Review_Reason"] = df_out["Review_Reason"].map(clean_release_review_reason)

    return df_out


def _norm_for_release_qc(x: Any) -> str:
    return "" if x is None else re.sub(r"\s+", " ", str(x).strip().lower())


def _has_release_value(x: Any) -> bool:
    return not _is_release_blank(x)


def _boolish_release_flag(x: Any) -> bool:
    return _norm_for_release_qc(x) in {"true", "1", "yes", "y", "review", "required"}


def refine_mode_a_public_review_flags(df_out: pd.DataFrame) -> pd.DataFrame:
    """Recompute public release review flags after Stage 3 mapping.

    The sensitive Stage 3.5 QC still exports complete review queues, but the
    public automated release should only mark rows as Review_Required when the
    term is truly new/unresolved relative to the reviewed mapping resources.

    Mapping-resource rule:
    - If a term exists in the reviewed disease/tissue/compound/RNA-source mapping
      file, do not add a public "mapping requires review" reason only because its
      mapped output is intentionally blank.
    - Add a public mapping-review reason only for a new term that is not already
      represented in the corresponding reviewed mapping file and still has a
      release-impacting unresolved mapping.
    """
    df_out = df_out.copy()
    if "Review_Reason" not in df_out.columns:
        return df_out

    accepted_blank_tissue_terms = {
        "tumor", "tumour", "urine", "stool", "feces", "faeces",
        "serum", "plasma", "saliva", "culture supernatant", "conditioned media",
    }

    def _split_reasons(x: Any) -> List[str]:
        raw = "" if x is None else str(x)
        return [p.strip() for p in raw.split(";") if p.strip()]

    def _dedupe(parts: List[str]) -> str:
        out: List[str] = []
        seen = set()
        for p in parts:
            if not p or p.lower() in {"na", "unknown", "nan", "none"}:
                continue
            if p not in seen:
                out.append(p)
                seen.add(p)
        return "; ".join(out)

    def _valid_cp_structure(row: pd.Series) -> bool:
        return _has_release_value(row.get("CP_CID", "")) and _has_release_value(row.get("CP_CanonicalSMILES", ""))

    new_reasons: List[str] = []

    for _, row in df_out.iterrows():
        parts = _split_reasons(row.get("Review_Reason", ""))
        kept: List[str] = []

        disease_new = _boolish_release_flag(row.get("Disease_New_Term_Flag", False))
        tissue_new = _boolish_release_flag(row.get("Tissue_New_Term_Flag", False))
        pert_new = _boolish_release_flag(row.get("Pert_New_Term_Flag", False))

        disease_method = _norm_for_release_qc(row.get("Disease_Map_Method", ""))
        tissue_method = _norm_for_release_qc(row.get("Tissue_Map_Method", ""))
        cp_method = _norm_for_release_qc(row.get("CP_Map_Method", ""))

        disease_known_in_mapping_file = (not disease_new) or disease_method in {
        "prior_disease_file",
        "prior_disease_file_semantic_reuse",
        "no_disease_state",
        }

        tissue_known_in_mapping_file = (not tissue_new) or tissue_method in {
        "prior_tissue_file",
        "prior_tissue_file_semantic_reuse",
        }

        cp_known_in_mapping_file = (not pert_new) or cp_method in {
        "prior_cp_file",
        "prior_cp_file_semantic_reuse",
        }

        disease_ok = _has_release_value(row.get("Disease_Mapped", "")) and (
            _has_release_value(row.get("DiseaseID", ""))
            or _norm_for_release_qc(row.get("Disease_Mapped", ""))
            in {"normal", "adjacent normal", "no disease mentioned"}
        )

        tissue_post_norm = _norm_for_release_qc(row.get("Tissue_Post", ""))
        tissue_ok = _has_release_value(row.get("Tissue_Mapped", "")) or tissue_post_norm in accepted_blank_tissue_terms

        rna_source_status = _norm_for_release_qc(row.get("RNA_Source_Mapping_Status", ""))
        rna_source_method = _norm_for_release_qc(row.get("RNA_Source_Mapping_Method", ""))
        rna_source_known_in_mapping_file = (
            rna_source_status.startswith("mapped:")
            or "reviewed mapping" in rna_source_method
            or "mapping file" in rna_source_method
        )
        rna_source_ok = _has_release_value(row.get("RNA_Source_Mapped", "")) or rna_source_known_in_mapping_file

        pert_type = _norm_for_release_qc(row.get("Pert_Type", "")).upper()
        cp_needs_public_review = pert_type == "CP" and (not cp_known_in_mapping_file) and (not _valid_cp_structure(row))

        for part in parts:
            # Missing RNA_Library is retained in QC outputs but is non-blocking for the public release.
            if part == "RNA sequencing row has missing RNA_Library.":
                continue

            # Disease: only public-flag new/unresolved disease terms not already in reviewed mapping resources.
            if part == "Disease mapping requires review.":
                if disease_known_in_mapping_file:
                    continue
                if disease_ok:
                    # Mapped new terms remain in novel-term workbooks; they do not need row-level public Review_Required.
                    continue

            # Tissue: do not flag terms that exist in tissue_mappings, even when intentionally mapped blank.
            if part == "Tissue mapping requires review.":
                if tissue_known_in_mapping_file or tissue_ok:
                    continue

            # RNA source: do not flag terms that exist in the RNA-source mapping file, even when intentionally blank.
            if part == "RNA_Source mapping requires review.":
                if rna_source_ok:
                    continue

            # CP: do not flag terms that exist in the compound mapping file; only flag new unresolved CP terms.
            if part == "CP mapping requires review.":
                if not cp_needs_public_review:
                    continue

            kept.append(part)

        new_reasons.append(_dedupe(kept))

    df_out["Review_Reason"] = new_reasons
    has_reason = df_out["Review_Reason"].fillna("").astype(str).str.strip().ne("")

    if "Review_Required" in df_out.columns:
        df_out["Review_Required"] = has_reason
    if "Global_QC_Status" in df_out.columns:
        df_out["Global_QC_Status"] = has_reason.map(lambda x: "REVIEW" if x else "PASS")
    if "Review_Level" in df_out.columns:
        df_out["Review_Level"] = ""
        high_mask = has_reason & df_out["Review_Reason"].astype(str).str.contains(
            "CP mapping requires review|Disease mapping requires review", regex=True, na=False
        )
        df_out.loc[high_mask, "Review_Level"] = "High"
        df_out.loc[has_reason & ~high_mask, "Review_Level"] = "Medium"

    # Internal RNA-source audit flag should reflect whether the term still needs review.
    # A reviewed reusable mapping-file decision is not a pending review item, even
    # when RNA_Source_Mapped is intentionally blank.
    if "RNA_Source_Review_Required" in df_out.columns:
        rna_status = df_out.get("RNA_Source_Mapping_Status", "").map(_norm_for_release_qc)
        rna_method = df_out.get("RNA_Source_Mapping_Method", "").map(_norm_for_release_qc)
        reviewed_rna_mapping = (
            rna_status.eq("mapped: reviewed reusable mapping")
            | rna_method.eq("reviewed mapping file")
            | rna_method.str.contains("reviewed mapping|mapping file", regex=True, na=False)
        )
        df_out.loc[reviewed_rna_mapping, "RNA_Source_Review_Required"] = False

    # Public release action should be explicit for all non-review/PASS rows.
    if "Release_Action" in df_out.columns:
        action_blank = df_out["Release_Action"].fillna("").astype(str).str.strip().eq("")
        pass_mask = ~has_reason
        if "Global_QC_Status" in df_out.columns:
            pass_mask = pass_mask | df_out["Global_QC_Status"].astype(str).str.upper().eq("PASS")
        if "Review_Required" in df_out.columns:
            pass_mask = pass_mask | ~df_out["Review_Required"].astype(bool)
        df_out.loc[action_blank & pass_mask, "Release_Action"] = "Include"

    return df_out


def add_missing_disease_within_mixed_gse_flags(
    df_out: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Flag rows where Disease is missing within a GSE that contains multiple
    non-missing disease states.

    This is a review/audit rule, not an auto-fill rule.
    """
    df_out = df_out.copy()

    # These columns may be bool dtype after refine_mode_a_public_review_flags().
    # Cast to object before adding string-safe review markers.
    for c in ["Review_Required", "Disease_Review_Required"]:
        if c in df_out.columns:
            df_out[c] = df_out[c].astype("object")

    required = {"GSM_ID", "GSE_ID", "Disease_Pre", "Disease_Post", "Disease_Mapped"}

    if not required.issubset(df_out.columns):
        return df_out, pd.DataFrame()

    def disease_value(row: pd.Series) -> str:
        return _first_nonblank(
            row.get("Disease_Post", ""),
            row.get("Disease_Mapped", ""),
            row.get("Disease_Pre", ""),
        )

    work = df_out[["GSM_ID", "GSE_ID", "Disease_Pre", "Disease_Post", "Disease_Mapped"]].copy()
    work["_Disease_Value"] = df_out.apply(disease_value, axis=1)
    work["_Disease_Value_Norm"] = work["_Disease_Value"].map(_norm_for_release_qc)

    missing_mask = (
        df_out["Disease_Pre"].map(_is_release_blank)
        & df_out["Disease_Post"].map(_is_release_blank)
        & df_out["Disease_Mapped"].map(_is_release_blank)
    )

    nonmissing = work.loc[~work["_Disease_Value"].map(_is_release_blank)].copy()

    gse_states = (
        nonmissing.groupby("GSE_ID")["_Disease_Value"]
        .apply(lambda s: sorted(set(str(x).strip() for x in s if not _is_release_blank(x))))
        .to_dict()
    )

    mixed_gses = {gse for gse, states in gse_states.items() if len(states) >= 2}

    flag_mask = missing_mask & df_out["GSE_ID"].astype(str).isin(mixed_gses)

    review_rows = []
    for idx in df_out.index[flag_mask]:
        gse = str(df_out.at[idx, "GSE_ID"])
        states = gse_states.get(gse, [])
        review_rows.append(
            {
                "GSM_ID": df_out.at[idx, "GSM_ID"],
                "GSE_ID": gse,
                "Disease_Pre": df_out.at[idx, "Disease_Pre"],
                "Disease_Post": df_out.at[idx, "Disease_Post"],
                "Disease_Mapped": df_out.at[idx, "Disease_Mapped"],
                "Same_GSE_Disease_States": " | ".join(states),
                "Same_GSE_Disease_State_Count": len(states),
                "Suggested_Action": "Review missing disease annotation; do not auto-fill because GSE contains multiple disease contexts.",
                "GSE_Info": df_out.at[idx, "GSE_Info"] if "GSE_Info" in df_out.columns else "",
                "GSM_Info": df_out.at[idx, "GSM_Info"] if "GSM_Info" in df_out.columns else "",
            }
        )

    review_df = pd.DataFrame(review_rows)

    if not review_df.empty:
        reason = "Disease annotation missing within mixed-disease GSE."

        if "Review_Reason" not in df_out.columns:
            df_out["Review_Reason"] = ""

        def append_reason(x: Any) -> str:
            old = "" if x is None else str(x).strip()
            if not old or old.lower() in {"na", "nan", "none", "unknown"}:
                return reason
            parts = [p.strip() for p in old.split(";") if p.strip()]
            if reason not in parts:
                parts.append(reason)
            return "; ".join(parts)

        df_out.loc[flag_mask, "Review_Reason"] = df_out.loc[flag_mask, "Review_Reason"].map(append_reason)

        if "Review_Required" in df_out.columns:
            df_out.loc[flag_mask, "Review_Required"] = "True"
        if "Global_QC_Status" in df_out.columns:
            df_out.loc[flag_mask, "Global_QC_Status"] = "REVIEW"
        if "Review_Level" in df_out.columns:
            df_out.loc[flag_mask, "Review_Level"] = "High"
        if "Disease_Review_Required" in df_out.columns:
            df_out.loc[flag_mask, "Disease_Review_Required"] = "True"

    return df_out, review_df


def normalize_pubchem_cid(x: Any) -> str:
    """Return PubChem CID as integer-like text for internal logic.

    Internal rule:
    - real CID -> integer-like string
    - blank/NA/Unknown -> ""
    """
    v = _blank(x)
    if not v:
        return ""

    v = str(v).strip()
    v = re.sub(r"^https?://pubchem\.ncbi\.nlm\.nih\.gov/compound/", "", v, flags=re.I)
    v = v.strip().strip("/")

    if re.fullmatch(r"\d+", v):
        return v

    try:
        d = Decimal(v)
    except (InvalidOperation, ValueError):
        return v

    if d == d.to_integral_value():
        return str(int(d))
    return v


def normalize_pubchem_cid_release(x: Any) -> str:
    """Return PubChem CID for release files; blanks/unmappable values become explicit NA."""
    cid = normalize_pubchem_cid(x)
    return cid if cid else "NA"


def normalize_cid_columns(
    df_out: pd.DataFrame,
    release_na: bool = True,
) -> pd.DataFrame:
    """Normalize PubChem CID columns without changing non-CID columns."""
    df_out = df_out.copy()

    norm_fn = normalize_pubchem_cid_release if release_na else normalize_pubchem_cid

    for c in ["CP_CID", "CID"]:
        if c in df_out.columns:
            df_out[c] = df_out[c].map(norm_fn)

    return df_out

def add_cp_mapping_status(df_out: pd.DataFrame) -> pd.DataFrame:
    df_out = df_out.copy()

    if "Pert_Type" not in df_out.columns:
        df_out["CP_Mapping_Status"] = "Not_Applicable"
        return df_out

    def status(row: pd.Series) -> str:
        pert_type = _norm_for_release_qc(row.get("Pert_Type", "")).upper()

        if pert_type != "CP":
            return "Not_Applicable_Non_CP"

        has_cid = _has_release_value(row.get("CP_CID", ""))
        has_smiles = _has_release_value(row.get("CP_CanonicalSMILES", ""))
        has_name = _has_release_value(row.get("CP_PubChem_Name", ""))

        if has_name and has_cid and has_smiles:
            return "Mapped"

        return "Review_Required_CP_Mapping"

    df_out["CP_Mapping_Status"] = df_out.apply(status, axis=1)
    return df_out

def _normalize_pert_release_text(x: Any) -> str:
    """
    Normalize perturbation dose/duration text for final release mapping.
    Blank, NA, and Unknown are returned as empty string.
    """
    v = _blank(x)
    if not v:
        return ""

    v = str(v).strip()
    v = v.replace("μ", "µ")
    v = re.sub(r"\s+", " ", v)
    return v


def map_pert_dose_for_release(x: Any) -> str:
    """
    Final downstream-ready dose field.

    Keep only single-dose entries with approved units:
      Molar concentration:
        pM, nM, µM, mM, M
        nmol/L, µmol/L, mmol/L

      Mass concentration:
        ng/ml, µg/ml, mg/ml

      Body-weight-normalized dose:
        ng/kg, µg/kg, mg/kg, g/kg

      Absolute mass:
        ng, µg, mg

    Return:
      NA      = no dose information
      Others  = dose exists but is not approved or contains multiple values
    """
    v = _normalize_pert_release_text(x)
    if not v:
        return "NA"

    # Multiple numeric values usually indicate dose ranges, dose series,
    # or combination treatments, e.g.:
    #   1, 5, 10 µM
    #   5-10 µM
    #   1 and 10 µM
    #   50 mg/kg/day + 5 mg/kg/day
    nums = re.findall(r"\d+(?:\.\d+)?", v)
    if len(nums) != 1:
        return "Others"

    # Keep only one numeric value followed by one approved unit.
    # Longer slash units must be listed before shorter absolute-mass units
    # so that mg/ml and mg/kg are not confused with bare mg.
    unit_pattern = (
        r"nmol/L|nmol/l|µmol/L|µmol/l|umol/L|umol/l|mmol/L|mmol/l|"
        r"ng/ml|ng/mL|µg/ml|µg/mL|ug/ml|ug/mL|mg/ml|mg/mL|"
        r"ng/kg|µg/kg|ug/kg|mg/kg|g/kg|"
        r"pM|pm|nM|nm|µM|µm|uM|um|mM|mm|M|"
        r"ng|µg|ug|mg"
    )

    m = re.fullmatch(
    rf"\s*(\d+(?:\.\d+)?)\s*({unit_pattern})\s*",
    v,
    flags=re.I,
    )

    if not m:
        return "Others"

    value = m.group(1)
    unit_raw = m.group(2).replace("μ", "µ")
    unit_key = unit_raw.lower()

    unit_map = {
        # Molar concentration
        "pm": "pM",
        "nm": "nM",
        "µm": "µM",
        "um": "µM",
        "mm": "mM",
        "m": "M",

        # mol/L-style concentration
        "nmol/l": "nmol/L",
        "µmol/l": "µmol/L",
        "umol/l": "µmol/L",
        "mmol/l": "mmol/L",

        # Mass concentration
        "ng/ml": "ng/ml",
        "µg/ml": "µg/ml",
        "ug/ml": "µg/ml",
        "mg/ml": "mg/ml",

        # Body-weight-normalized dose
        "ng/kg": "ng/kg",
        "µg/kg": "µg/kg",
        "ug/kg": "µg/kg",
        "mg/kg": "mg/kg",
        "g/kg": "g/kg",

        # Absolute mass
        "ng": "ng",
        "µg": "µg",
        "ug": "µg",
        "mg": "mg",
    }

    unit = unit_map.get(unit_key)
    if not unit:
        return "Others"

    return f"{value} {unit}"


def map_pert_duration_for_release(x: Any) -> str:
    """
    Final downstream-ready duration field.

    Keep only single-duration entries with approved units:
      Minutes, Hours, Days, Weeks, Months

    Return:
      NA      = no duration information
      Others  = duration exists but is not approved or contains multiple values
    """
    v = _normalize_pert_release_text(x)
    if not v:
        return "NA"

    # Convert single hyphenated duration forms such as 24-hour to 24 hour.
    # This does not convert ranges such as 3-5 days.
    v = re.sub(
        r"(\d+(?:\.\d+)?)\s*-\s*(minute|minutes|min|mins|hour|hours|hr|hrs|h|day|days|d|week|weeks|wk|wks|month|months|mo|mos)\b",
        r"\1 \2",
        v,
        flags=re.I,
    )

    nums = re.findall(r"\d+(?:\.\d+)?", v)
    if len(nums) != 1:
        return "Others"

    m = re.fullmatch(
        r"\s*(\d+(?:\.\d+)?)\s*(minute|minutes|min|mins|hour|hours|hr|hrs|h|day|days|d|week|weeks|wk|wks|month|months|mo|mos)\s*",
        v,
        flags=re.I,
    )

    if not m:
        return "Others"

    value = m.group(1)
    unit_raw = m.group(2).lower()

    unit_map = {
        "minute": "Minutes",
        "minutes": "Minutes",
        "min": "Minutes",
        "mins": "Minutes",
        "hour": "Hours",
        "hours": "Hours",
        "hr": "Hours",
        "hrs": "Hours",
        "h": "Hours",
        "day": "Days",
        "days": "Days",
        "d": "Days",
        "week": "Weeks",
        "weeks": "Weeks",
        "wk": "Weeks",
        "wks": "Weeks",
        "month": "Months",
        "months": "Months",
        "mo": "Months",
        "mos": "Months",
    }

    unit = unit_map.get(unit_raw)
    if not unit:
        return "Others"

    return f"{value} {unit}"

def _norm(s: str) -> str:
    return str(s).strip().lower() if s is not None else ""


def normalize_compound_match_key(x: Any) -> str:
    """
    Normalize compound names for tolerant PubChem title/synonym matching.

    This is used only to verify a PubChem result. It intentionally ignores
    case, spaces, hyphens, underscores, and punctuation so that terms such as
    FTX-6746 and FTX6746 can be compared safely.
    """
    v = _blank(x).lower()
    return re.sub(r"[^a-z0-9]", "", v)


def _cp_cache_is_reusable(rec: Any) -> bool:
    """
    Decide whether an existing CP cache record should be reused.

    Reuse curated/prior mappings and verified PubChem mappings. Re-run old
    failed or unverified records so changes to the direct PubChem matcher can
    recover terms that were previously missed.
    """
    if not isinstance(rec, dict):
        return False

    if normalize_pubchem_cid(rec.get("CP_CID", "")):
        return True

    method = _s(rec.get("CP_Map_Method", ""))
    return method in {
        "prior_cp_file",
        "pubchem_direct_title",
        "pubchem_direct_synonym",
    }


def _chunk(xs: List[str], n: int) -> List[List[str]]:
    return [xs[i : i + n] for i in range(0, len(xs), n)]


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def read_prompt_file(prompt_path: str | Path) -> str:
    """Read a prompt from Markdown, plain text, or DOCX.

    Stage 3 public prompts are stored as .md files. DOCX support is retained
    only for backward compatibility.
    """
    path = Path(prompt_path)
    suffix = path.suffix.lower()

    if suffix in {".md", ".txt"}:
        return path.read_text(encoding="utf-8").strip()

    if suffix == ".docx":
        from docx import Document

        doc = Document(str(path))
        paras = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
        return "\n".join(paras).strip()

    raise ValueError(f"Unsupported prompt file type: {path}")


def strip_extract_infer_suffix(x: str) -> str:
    x = _s(x)
    if x in {"NA", "Unknown"}:
        return x
    return re.sub(r"\s*\((Extracted|Inferred)\)\s*$", "", x, flags=re.IGNORECASE).strip()


def normalize_lookup_term(x: str) -> str:
    x = strip_extract_infer_suffix(_s(x))
    if x in {"NA", "Unknown"}:
        return x
    x = re.sub(r"[^\w\s\-\+;/|,]", " ", x)
    x = re.sub(r"\s+", " ", x).strip().lower()
    return x

def lookup_key_variants(x: Any) -> set[str]:
    """
    Generate tolerant lookup keys for reviewed mapping-file reuse.

    Used for Disease, Tissue, and CP mapping files.
    Handles case, punctuation, hyphen/space variation, and parenthetical forms.
    """
    raw = strip_extract_infer_suffix(_s(x))
    if raw in {"", "NA", "Unknown"}:
        return set()

    vals = {raw}

    vals.add(re.sub(r"[\u2010-\u2015]", "-", raw))
    vals.add(re.sub(r"[\u2010-\u2015]", " ", raw))
    vals.add(raw.replace("-", " "))
    vals.add(raw.replace("/", " "))
    vals.add(raw.replace("_", " "))

    # Parenthetical forms:
    # Breast Cancer (Triple-negative Breast Cancer)
    # should also match:
    # Triple-negative Breast Cancer
    # Breast Cancer (Triple-Negative)
    m = re.match(r"^\s*(.*?)\s*\((.*?)\)\s*$", raw)
    if m:
        base = m.group(1).strip()
        inside = m.group(2).strip()
        if base:
            vals.add(base)
        if inside:
            vals.add(inside)

    keys = set()
    for v in vals:
        k = normalize_lookup_term(v)
        if k and k not in {"", "NA", "Unknown", "na", "unknown"}:
            keys.add(k)
            keys.add(k.replace("-", " "))

    return {k for k in keys if k and k not in {"na", "unknown"}}


def disease_lookup_keys_for_prior_mapping(x: Any) -> set[str]:
    """
    Disease-specific wrapper for reviewed disease_mappings.xlsx reuse.

    Keep this generic. Do not hard-code individual disease examples here.
    Deeper semantic equivalence is handled by LLM prior-mapping semantic reuse.
    """
    return lookup_key_variants(x)


def lookup_prior_record(
    term: Any,
    prior_mapping: Dict[str, Dict[str, Any]],
    domain: str = "",
) -> Dict[str, Any] | None:
    """
    Return a reviewed mapping-file record using tolerant lookup keys.
    """
    if domain.lower() == "disease":
        keys = disease_lookup_keys_for_prior_mapping(term)
    else:
        keys = lookup_key_variants(term)

    for key in keys:
        if key in prior_mapping:
            return prior_mapping[key]

    return None

PRIOR_MAPPING_REUSE_SYSTEM = """
You are a strict biomedical mapping-file reuse assistant.

Your job is NOT to invent new mappings.
Your job is to decide whether each incoming term is a semantic variant of one reviewed mapping-file candidate.

Return STRICT JSON only. No markdown.

Input JSON:
{
  "domain": "Disease|Tissue|CP",
  "terms": [
    {
      "term": "...",
      "candidates": [
        {
          "candidate_id": "C0",
          "Original_Term": "...",
          "Standardized_Term": "...",
          "Final_Mapped_Term": "...",
          "Extra": "..."
        }
      ]
    }
  ]
}

Output JSON:
{
  "decisions": [
    {
      "term": "...",
      "reuse": true,
      "candidate_id": "C0",
      "confidence": "high|medium|low",
      "reason": "..."
    }
  ]
}

Rules:
- Return exactly one decision for each input term.
- reuse=true only when the input term is clearly the same concept, synonym, spelling variant, abbreviation, subtype wording variant, or parenthetical rephrasing of a reviewed mapping-file row.
- Do not choose a more specific ontology term if the reviewed mapping file intentionally maps that concept to a broader final mapped term.
- For Disease, the reviewed mapping file is authoritative over CTD/LLM ontology specificity.
- For Tissue, use the reviewed tissue controlled-vocabulary decision when semantically equivalent.
- For CP, reuse only reviewed compound mapping rows; do not invent CID, SMILES, or PubChem names.
- If no candidate is semantically equivalent, return reuse=false and candidate_id=null.
- Accept only high or medium confidence for automatic reuse. Low confidence should be treated as no reuse.
"""


def _candidate_score(term: Any, candidate_text: Any) -> float:
    a = normalize_lookup_term(term)
    b = normalize_lookup_term(candidate_text)
    if not a or not b or a in {"NA", "Unknown"} or b in {"NA", "Unknown"}:
        return 0.0
    return _wratio(a, b)


def _make_prior_candidate_records(path: Path, domain: str) -> list[dict]:
    """
    Load reviewed mapping-file rows as candidate records for semantic reuse.
    """
    if not path.exists():
        print(f"[Stage3 {domain}] prior mapping file not found for semantic reuse: {path}")
        return []

    df = pd.read_excel(path, engine="openpyxl")
    df.columns = df.columns.astype(str).str.strip()

    records = []

    for i, r in df.iterrows():
        if domain == "Disease":
            original = _blank(r.get("Original_Raw_Disease_Term"))
            standardized = _blank(r.get("Standardized_Disease_Term"))
            final_mapped = _blank(r.get("Final_Mapped_Disease_Term"))
            disease_name = _blank(r.get("DiseaseName"))
            final_label = final_mapped if final_mapped else disease_name

            rec = {
                "Disease_Mapped": final_label,
                "DiseaseID": _blank(r.get("DiseaseID")),
                "AltDiseaseIDs": _blank(r.get("AltDiseaseIDs")),
                "Definition": _blank(r.get("Definition")),
                "ParentIDs": _blank(r.get("ParentIDs")),
                "TreeNumbers": _blank(r.get("TreeNumbers")),
                "ParentTreeNumbers": _blank(r.get("ParentTreeNumbers")),
                "Synonyms": _blank(r.get("Synonyms")),
                "SlimMappings": _blank(r.get("SlimMappings")),
                "Broad_Disease_Category": _blank(r.get("Broad_Disease_Category")),
                "Disease_Map_Explanation": "Mapped from prior curated disease mapping file by semantic reuse.",
                "Disease_Review_Required": False,
                "Disease_Map_Method": "prior_disease_file_semantic_reuse",
                "Final_Diease_Term_Flag": "",
                "Comment1": "",
                "Comment2": "",
                "Match_MESHCode": "",
            }

            searchable = " | ".join(
                [
                    original,
                    standardized,
                    final_mapped,
                    disease_name,
                    _blank(r.get("Synonyms")),
                ]
            )

            records.append(
                {
                    "candidate_id": f"D{i}",
                    "domain": domain,
                    "Original_Term": original,
                    "Standardized_Term": standardized,
                    "Final_Mapped_Term": final_label,
                    "Extra": (
                        f"DiseaseName={disease_name}; "
                        f"DiseaseID={_blank(r.get('DiseaseID'))}; "
                        f"Broad={_blank(r.get('Broad_Disease_Category'))}"
                    ),
                    "searchable": searchable,
                    "record": rec,
                }
            )

        elif domain == "Tissue":
            original = _blank(r.get("Original_Tissue_Term"))
            standardized = _blank(r.get("Standardized_Tissue_Term"))
            final_mapped = _blank(r.get("Final_Mapped_Tissue_Term"))

            rec = {
                "Tissue_Mapped": final_mapped,
                "Tissue_Map_Explanation": "Mapped from prior curated tissue mapping file by semantic reuse.",
                "Tissue_Map_Method": "prior_tissue_file_semantic_reuse",
            }

            searchable = " | ".join([original, standardized, final_mapped])

            records.append(
                {
                    "candidate_id": f"T{i}",
                    "domain": domain,
                    "Original_Term": original,
                    "Standardized_Term": standardized,
                    "Final_Mapped_Term": final_mapped,
                    "Extra": "",
                    "searchable": searchable,
                    "record": rec,
                }
            )

        elif domain == "CP":
            original = _blank(r.get("Original_Raw_Compound_Term"))
            standardized = _blank(r.get("Standardized_Compound_Term"))
            final_mapped = _blank(r.get("Final_Mapped_Compound_Name"))

            rec = {
                "CP_PubChem_Name": final_mapped,
                "CP_CID": normalize_pubchem_cid(r.get("CID")),
                "CP_CanonicalSMILES": _blank(r.get("CanonicalSMILES")),
                "CP_PubChemURL": _blank(r.get("PubChemURL")),
                "CP_MatchType": _blank(r.get("MatchType")),
                "CP_Map_Explanation": "Mapped from prior curated compound mapping file by semantic reuse.",
                "CP_Map_Method": "prior_cp_file_semantic_reuse",
            }

            searchable = " | ".join(
                [
                    original,
                    standardized,
                    final_mapped,
                    _blank(r.get("CID")),
                ]
            )

            records.append(
                {
                    "candidate_id": f"C{i}",
                    "domain": domain,
                    "Original_Term": original,
                    "Standardized_Term": standardized,
                    "Final_Mapped_Term": final_mapped,
                    "Extra": f"CID={normalize_pubchem_cid(r.get('CID'))}; MatchType={_blank(r.get('MatchType'))}",
                    "searchable": searchable,
                    "record": rec,
                }
            )

    return records


def _top_prior_candidates_for_term(
    term: Any,
    candidate_records: list[dict],
    top_k: int = 8,
) -> list[dict]:
    scored = []

    for rec in candidate_records:
        score = max(
            _candidate_score(term, rec.get("Original_Term", "")),
            _candidate_score(term, rec.get("Standardized_Term", "")),
            _candidate_score(term, rec.get("Final_Mapped_Term", "")),
            _candidate_score(term, rec.get("searchable", "")),
        )

        if score >= 45:
            scored.append((score, rec))

    scored = sorted(scored, key=lambda x: x[0], reverse=True)[:top_k]

    out = []
    for score, rec in scored:
        out.append(
            {
                "candidate_id": rec["candidate_id"],
                "Original_Term": rec.get("Original_Term", ""),
                "Standardized_Term": rec.get("Standardized_Term", ""),
                "Final_Mapped_Term": rec.get("Final_Mapped_Term", ""),
                "Extra": rec.get("Extra", ""),
                "score": round(float(score), 2),
            }
        )

    return out


def resolve_terms_by_prior_mapping_llm(
    cfg,
    llm,
    terms: list[str],
    candidate_records: list[dict],
    domain: str,
    batch_size: int = 20,
) -> tuple[dict[str, dict], pd.DataFrame]:
    """
    Ask LLM whether unmatched terms should reuse an existing reviewed mapping-file row.

    Returns:
      resolved_records: term -> Stage3 mapping record
      decision_df: audit table of decisions
    """
    terms = [t for t in terms if _s(t) not in {"NA", "Unknown", ""}]
    if not terms or not candidate_records:
        return {}, pd.DataFrame()

    id_to_record = {r["candidate_id"]: r for r in candidate_records}
    resolved: dict[str, dict] = {}
    decision_rows = []

    for bi, chunk_terms in enumerate(_chunk(terms, batch_size)):
        payload_terms = []

        for t in chunk_terms:
            candidates = _top_prior_candidates_for_term(t, candidate_records, top_k=8)
            if not candidates:
                continue

            payload_terms.append(
                {
                    "term": t,
                    "candidates": candidates,
                }
            )

        if not payload_terms:
            continue

        payload = {
            "domain": domain,
            "terms": payload_terms,
        }

        messages = [
            {"role": "system", "content": PRIOR_MAPPING_REUSE_SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]

        check_messages_token_budget(
            messages,
            budget=TokenBudget.from_config(cfg),
            context_label=f"Stage3 prior mapping semantic reuse {domain} batch={bi}",
            action=str(getattr(cfg, "llm_token_budget_action", "raise")),
        )

        txt = llm.chat(messages, temperature=0.0)

        out = safe_json_loads_with_repair(
            txt,
            debug_dir=str(Path(cfg.debug_dir)),
            debug_tag=f"PRIOR_REUSE_{domain}_{bi}",
            llm_chat_fn=lambda msgs, temperature=0.0: llm.chat(msgs, temperature=temperature),
        )

        for d in out.get("decisions", []):
            term = _s(d.get("term"))
            reuse = bool(d.get("reuse", False))
            candidate_id = "" if d.get("candidate_id") is None else str(d.get("candidate_id")).strip()
            confidence = str(d.get("confidence", "")).strip().lower()
            reason = str(d.get("reason", "")).strip()

            accepted = (
                reuse
                and candidate_id in id_to_record
                and confidence in {"high", "medium"}
            )

            row = {
                "domain": domain,
                "term": term,
                "reuse": reuse,
                "candidate_id": candidate_id,
                "confidence": confidence,
                "accepted": accepted,
                "reason": reason,
            }

            if accepted:
                chosen = id_to_record[candidate_id]
                resolved[term] = chosen["record"].copy()
                row["Chosen_Original_Term"] = chosen.get("Original_Term", "")
                row["Chosen_Standardized_Term"] = chosen.get("Standardized_Term", "")
                row["Chosen_Final_Mapped_Term"] = chosen.get("Final_Mapped_Term", "")

            decision_rows.append(row)

    return resolved, pd.DataFrame(decision_rows)

def _wratio(a: str, b: str) -> float:
    if fuzz is None:
        sa, sb = set(a.split()), set(b.split())
        if not sa or not sb:
            return 0.0
        return 100.0 * (len(sa & sb) / max(len(sa), len(sb)))
    return float(fuzz.WRatio(a, b))


def _no_disease_state(x: str) -> bool:
    key = normalize_lookup_term(x)
    return key in {"normal", "adjacent normal", "no disease mentioned", "na", "unknown", ""}


def _no_disease_record(term: str) -> Dict[str, Any]:
    """Return a row-preserving disease mapping record for explicit non-disease states.

    Normal, Adjacent Normal, and No Disease Mentioned are biologically meaningful
    labels in GEOMeta and should not be cleared from Disease_Mapped. True NA/Unknown
    remain NA-style unresolved states.
    """
    key = normalize_lookup_term(term)

    if key == "normal":
        mapped = "Normal"
        category = "Normal"
        explanation = "Explicit healthy/normal disease-free state."
    elif key == "adjacent normal":
        mapped = "Adjacent Normal"
        category = "Adjacent Normal"
        explanation = "Explicit normal tissue from a diseased donor/patient."
    elif key == "no disease mentioned":
        mapped = "No Disease Mentioned"
        category = "No Disease Mentioned"
        explanation = "No disease information was provided for this sample."
    else:
        mapped = "NA"
        category = ""
        explanation = "Disease annotation is unavailable or unresolved."

    return {
        "Disease_Mapped": mapped,
        "DiseaseID": "",
        "AltDiseaseIDs": "",
        "Definition": "",
        "ParentIDs": "",
        "TreeNumbers": "",
        "ParentTreeNumbers": "",
        "Synonyms": "",
        "SlimMappings": "",
        "Broad_Disease_Category": category,
        "Disease_Map_Explanation": explanation,
        "Disease_Review_Required": False,
        "Disease_Map_Method": "no_disease_state",
        "Final_Diease_Term_Flag": "",
        "Comment1": "",
        "Comment2": "",
        "Match_MESHCode": "",
    }


def _is_composite_disease_term(x: str) -> bool:
    """Detect disease strings that contain multiple disease labels.

    Stage 3 ontology mapping expects one disease concept per sample. Composite
    disease labels should be routed to NA/manual review instead of being mapped
    to a single CTD term. This intentionally focuses on separators produced by
    the pipeline, especially semicolon and plus signs, and avoids treating
    disease names such as 'Head And Neck Cancer' as composites.
    """
    v = _s(x)
    if v in {"NA", "Unknown", ""}:
        return False
    vl = v.lower()
    if ";" in v or " + " in v:
        return True
    if re.search(r"\s+\+\s+", v):
        return True
    # Common explicit multi-disease wording from metadata.
    if re.search(r"\b(multiple diseases|mixed diseases|various diseases)\b", vl):
        return True
    return False


def _composite_disease_record(term: str) -> Dict[str, Any]:
    return {
        "Disease_Mapped": "NA",
        "DiseaseID": "",
        "AltDiseaseIDs": "",
        "Definition": "",
        "ParentIDs": "",
        "TreeNumbers": "",
        "ParentTreeNumbers": "",
        "Synonyms": "",
        "SlimMappings": "",
        "Broad_Disease_Category": "",
        "Disease_Map_Explanation": "Composite disease term; not mapped to a single disease concept.",
        "Disease_Review_Required": True,
        "Disease_Map_Method": "composite_disease_term",
        "Final_Diease_Term_Flag": "COMPOSITE_DISEASE_REVIEW",
        "Comment1": f"Composite disease term set to NA for manual review: {_s(term)}",
        "Comment2": "",
        "Match_MESHCode": "",
    }

def preserve_adjacent_normal_before_disease_mapping(df: pd.DataFrame) -> pd.DataFrame:
    """
    Stage 3 safeguard:
    If Stage 2 converted Adjacent Normal to Healthy/Normal, restore
    Disease_Post to Adjacent Normal before disease ontology mapping.
    """
    df = df.copy()

    if {"Disease_Pre", "Disease_Post"}.issubset(df.columns):
        pre_adjacent = df["Disease_Pre"].map(normalize_lookup_term).eq("adjacent normal")
        post_normal_like = df["Disease_Post"].map(normalize_lookup_term).isin(
            {"healthy", "normal"}
        )
        df.loc[pre_adjacent & post_normal_like, "Disease_Post"] = "Adjacent Normal"

    return df

def high_confidence_disease_release_mask(
    df_out: pd.DataFrame,
    disease_col: str = "Disease_Mapped",
    diseaseid_col: str = "DiseaseID",
) -> pd.Series:
    """
    Keep only high-confidence disease rows for public release files.

    Keep rows where:
    - Disease_Mapped is Normal
    - Disease_Mapped is Adjacent Normal
    - Disease_Mapped is No Disease Mentioned
    - or Disease_Mapped is non-empty and has valid DiseaseID
    """
    if disease_col not in df_out.columns:
        return pd.Series(False, index=df_out.index)

    allowed_no_disease = {"normal", "adjacent normal", "no disease mentioned"}

    disease_norm = df_out[disease_col].map(_norm_for_release_qc)
    no_disease_ok = disease_norm.isin(allowed_no_disease)

    if diseaseid_col in df_out.columns:
        has_disease_id = df_out[diseaseid_col].map(_has_release_value)
    else:
        has_disease_id = pd.Series(False, index=df_out.index)

    mapped_present = df_out[disease_col].map(_has_release_value)

    return no_disease_ok | (mapped_present & has_disease_id)


def build_disease_release_excluded_review_queue(
    df_out: pd.DataFrame,
    keep_mask: pd.Series,
) -> pd.DataFrame:
    """Save rows excluded from public disease release files."""
    excluded = df_out.loc[~keep_mask].copy()

    if excluded.empty:
        return pd.DataFrame()

    preferred_cols = [
        "GSM_ID",
        "GSE_ID",
        "Disease_Pre",
        "Disease_Post",
        "Disease_Mapped",
        "DiseaseID",
        "Broad_Disease_Category",
        "Disease_Map_Method",
        "Disease_Map_Explanation",
        "Disease_Review_Required",
        "Review_Required",
        "Review_Reason",
        "GSE_Info",
        "GSM_Info",
    ]

    cols = [c for c in preferred_cols if c in excluded.columns]
    out = excluded.loc[:, cols].copy()

    out.insert(
        0,
        "Disease_Release_Exclusion_Reason",
        "Excluded from public disease release because Disease_Mapped is not Normal, Adjacent Normal, or No Disease Mentioned and does not have a valid DiseaseID.",
    )

    return out

def fill_release_action_for_pass_rows(df_out: pd.DataFrame) -> pd.DataFrame:
    """
    Final release safeguard:
    If a row passed QC and does not require review, blank Release_Action should be Include.
    Handles bool/string variants of Review_Required.
    """
    df_out = df_out.copy()

    if "Release_Action" not in df_out.columns:
        df_out["Release_Action"] = ""

    if "Global_QC_Status" not in df_out.columns or "Review_Required" not in df_out.columns:
        return df_out

    qc_pass = df_out["Global_QC_Status"].fillna("").astype(str).str.strip().str.upper().eq("PASS")

    review_false = (
        df_out["Review_Required"]
        .astype("string")
        .fillna(False)
        .astype(str)
        .str.strip()
        .str.upper()
        .isin({"FALSE", "0", "NO", ""})
    )

    release_blank = (
        df_out["Release_Action"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .isin({"", "NA", "NAN", "NONE", "UNKNOWN"})
    )

    df_out.loc[qc_pass & review_false & release_blank, "Release_Action"] = "Include"

    return df_out



def build_stage3_mapped_output_view(df_out: pd.DataFrame) -> pd.DataFrame:
    """
    Output-facing view for stage3_mapped.xlsx.

    Keep core RNA_Source audit fields:
      - RNA_Source_Pre
      - RNA_Source_Post
      - RNA_Source_Mapped
      - RNA_Source_Mapping_Status
      - RNA_Source_Review_Required

    Drop duplicated public RNA_Source and detailed RNA_Source mapping metadata
    from the main mapped output. Detailed RNA source review evidence remains
 Drop duplicated public RNA_Source and detailed RNA_Source mapping metadata
       in the RNA source review queue.
    """
    df_out = df_out.copy()

    drop_cols = [
        "RNA_Source",
        "RNA_Source_Final",
        "RNA_Source_Mapping_Method",
        "RNA_Source_Mapping_Confidence",
        "RNA_Source_Mapping_Reason",
    ]

    drop_cols = [c for c in drop_cols if c in df_out.columns]
    if drop_cols:
        df_out = df_out.drop(columns=drop_cols)

    return df_out


# -------------------------
# CTD KB
# -------------------------
CTD_META_COLS = [
    "DiseaseName",
    "DiseaseID",
    "AltDiseaseIDs",
    "Definition",
    "ParentIDs",
    "TreeNumbers",
    "ParentTreeNumbers",
    "Synonyms",
    "SlimMappings",
]


def load_ctd_kb(ctd_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(ctd_csv)
    missing = [c for c in CTD_META_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"CTD file missing expected columns: {missing}")

    df = df.copy()
    for c in CTD_META_COLS:
        df[c] = df[c].fillna("").astype(str)

    df["norm_name"] = df["DiseaseName"].map(normalize_lookup_term)
    df["norm_syn"] = df["Synonyms"].fillna("").astype(str).str.lower()
    df["search_text"] = (
        df["DiseaseName"].fillna("").astype(str)
        + " "
        + df["Synonyms"].fillna("").astype(str)
        + " "
        + df["Definition"].fillna("").astype(str)
    ).str.lower()

    return df


# -------------------------
# Prior mapping loaders
# -------------------------
def _ensure_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{label} missing columns: {sorted(missing)}")


def load_prior_disease_mapping(path: Path) -> Dict[str, Dict[str, Any]]:
    """Load curated disease mappings using finalized public schema."""
    if not path.exists():
        print(f"[Stage3] prior_disease_mapping_xlsx not found: {path}")
        return {}

    df = pd.read_excel(path, engine="openpyxl")
    df.columns = df.columns.astype(str).str.strip()

    required = {
        "Original_Raw_Disease_Term",
        "Standardized_Disease_Term",
        "Final_Mapped_Disease_Term",
        "DiseaseName",
        "DiseaseID",
        "AltDiseaseIDs",
        "Definition",
        "ParentIDs",
        "TreeNumbers",
        "ParentTreeNumbers",
        "Synonyms",
        "SlimMappings",
        "Broad_Disease_Category",
    }
    _ensure_columns(df, required, "Prior disease mapping")

    mapping: Dict[str, Dict[str, Any]] = {}

    for _, r in df.iterrows():
        final_mapped = _blank(r.get("Final_Mapped_Disease_Term"))
        disease_name = _blank(r.get("DiseaseName"))
        mapped_label = final_mapped if final_mapped else disease_name

        rec = {
            "Disease_Mapped": mapped_label,
            "DiseaseID": _blank(r.get("DiseaseID")),
            "AltDiseaseIDs": _blank(r.get("AltDiseaseIDs")),
            "Definition": _blank(r.get("Definition")),
            "ParentIDs": _blank(r.get("ParentIDs")),
            "TreeNumbers": _blank(r.get("TreeNumbers")),
            "ParentTreeNumbers": _blank(r.get("ParentTreeNumbers")),
            "Synonyms": _blank(r.get("Synonyms")),
            "SlimMappings": _blank(r.get("SlimMappings")),
            "Broad_Disease_Category": _blank(r.get("Broad_Disease_Category")),
            "Disease_Map_Explanation": "Mapped from prior curated disease mapping file.",
            "Disease_Review_Required": False,
            "Disease_Map_Method": "prior_disease_file",
        }

        for key_source in [
            r.get("Original_Raw_Disease_Term", ""),
            r.get("Standardized_Disease_Term", ""),
            r.get("Final_Mapped_Disease_Term", ""),
            r.get("DiseaseName", ""),
        ]:
            for key in disease_lookup_keys_for_prior_mapping(key_source):
                if key not in {"", "NA", "Unknown", "na", "unknown"}:
                    mapping.setdefault(key, rec)
    return mapping


def load_prior_tissue_mapping(path: Path) -> Dict[str, Dict[str, Any]]:
    """Load curated tissue mappings using finalized public schema."""
    if not path.exists():
        print(f"[Stage3] prior_tissue_mapping_xlsx not found: {path}")
        return {}

    df = pd.read_excel(path, engine="openpyxl")
    df.columns = df.columns.astype(str).str.strip()

    required = {
        "Original_Tissue_Term",
        "Standardized_Tissue_Term",
        "Final_Mapped_Tissue_Term",
    }
    _ensure_columns(df, required, "Prior tissue mapping")

    out: Dict[str, Dict[str, Any]] = {}

    for _, r in df.iterrows():
        keys = set()
        for key_source in [
            r.get("Original_Tissue_Term", ""),
            r.get("Standardized_Tissue_Term", ""),
            r.get("Final_Mapped_Tissue_Term", ""),
        ]:
            keys.update(lookup_key_variants(key_source))

        rec = {
            "Tissue_Mapped": _mapped_na(r.get("Final_Mapped_Tissue_Term")),
            "Tissue_Map_Explanation": _blank(r.get("Comments")) if "Comments" in df.columns else "",
            "Tissue_Map_Method": "prior_tissue_file",
        }

        for k in keys:
            if k not in {"", "NA", "Unknown"} and k not in out:
                out[k] = rec

    return out


def load_prior_cp_mapping(path: Path) -> Dict[str, Dict[str, Any]]:
    """Load curated compound mappings using finalized public schema."""
    if not path.exists():
        print(f"[Stage3] prior_cp_mapping_xlsx not found: {path}")
        return {}

    df = pd.read_excel(path, engine="openpyxl")
    df.columns = df.columns.astype(str).str.strip()

    required = {
        "Original_Raw_Compound_Term",
        "Standardized_Compound_Term",
        "Final_Mapped_Compound_Name",
        "CID",
        "MatchType",
        "CanonicalSMILES",
        "PubChemURL",
    }
    _ensure_columns(df, required, "Prior CP mapping")

    out: Dict[str, Dict[str, Any]] = {}

    for _, r in df.iterrows():
        keys = set()
        for key_source in [
            r.get("Original_Raw_Compound_Term", ""),
            r.get("Standardized_Compound_Term", ""),
            r.get("Final_Mapped_Compound_Name", ""),
        ]:
            keys.update(lookup_key_variants(key_source))

        rec = {
            "CP_PubChem_Name": _blank(r.get("Final_Mapped_Compound_Name")),
            "CP_CID": normalize_pubchem_cid(r.get("CID")),
            "CP_CanonicalSMILES": _blank(r.get("CanonicalSMILES")),
            "CP_PubChemURL": _blank(r.get("PubChemURL")),
            "CP_MatchType": _blank(r.get("MatchType")),
            "CP_Map_Explanation": "Mapped from prior curated compound mapping file.",
            "CP_Map_Method": "prior_cp_file",
        }

        for k in keys:
            if k not in {"", "NA", "Unknown"} and k not in out:
                out[k] = rec

    return out


# -------------------------
# LLM systems
# -------------------------
CTD_LLM_SYSTEM = (
    "You are a biomedical ontology mapping assistant working under a reviewer-governed disease mapping workflow.\n"
    "Return STRICT JSON only. No markdown. No commentary.\n"
    "Input JSON: {\"terms\": [\"...\"], \"candidates\": {\"term\": [{\"DiseaseName\":\"...\",\"DiseaseID\":\"...\",\"score\":99.1}]}}\n"
    "Output JSON: {\"mappings\": [{\"raw\":\"...\",\"DiseaseName\":\"...\",\"DiseaseID\":\"...\",\"explanation\":\"...\"}]}\n"
    "Rules:\n"
    "- Exactly one mapping per input term.\n"
    "- Prefer deterministic reasoning: normalized exact DiseaseName match, normalized synonym match, then generalized match.\n"
    "- Use candidate retrieval only after deterministic matching fails.\n"
    "- Prefer parent/general disease categories over numbered or genetic subtypes unless explicitly required by the input.\n"
    "- Do not overmatch vague descriptors, anatomical phrases, unrelated loci, or context-only similarities.\n"
    "- If no plausible CTD mapping exists, return DiseaseName=NA and DiseaseID=NA.\n"
    "- Never hallucinate a CTD mapping.\n"
)

TISSUE_LLM_SYSTEM = (
    "You are a biomedical tissue mapping assistant working under a controlled tissue mapping workflow.\n"
    "Return STRICT JSON only. No markdown. No commentary.\n"
    "Input JSON: {\"terms\": [..]}\n"
    "Output JSON: {\"mappings\": [{\"raw\":...,\"mapped\":...,\"explanation\":...}]}\n"
    "Rules:\n"
    "- Exactly one mapping per input term.\n"
    "- Map only to allowed HPA-derived tissue categories, supported brain subregions, additional curated tissue categories, Brain, or NA.\n"
    "- For brain-related terms only, map to Brain: [Region] using approved brain subregions when supported.\n"
    "- Outside brain, collapse subregions to the parent tissue.\n"
    "- Apply abbreviation expansion, synonym reduction, singular-over-plural, and title case normalization.\n"
    "- Do not invent categories beyond the controlled vocabulary.\n"
    "- If no valid mapping exists, return mapped=NA.\n"
)

CP_LLM_SYSTEM = (
    "You help normalize chemical perturbation names for PubChem mapping under a curated compound mapping workflow.\n"
    "Return STRICT JSON only. No markdown. No commentary.\n"
    "Input JSON: {\"terms\": [..]}\n"
    "Output JSON: {\"mappings\": [{\"raw\":...,\"query\":...,\"explanation\":...}]}\n"
    "Rules:\n"
    "- Exactly one mapping per input term.\n"
    "- query should be the best canonical compound name to send to PubChem name lookup.\n"
    "- Remove dose, duration, route, and other non-identifying modifiers.\n"
    "- Expand abbreviations and unify synonyms only when supported.\n"
    "- Only map single-compound chemical perturbations.\n"
    "- If the term is not a chemical perturbation or remains ambiguous, return query=NA.\n"
)

# -------------------------
# PubChem helpers
# -------------------------
# PubChem asks programmatic users to stay below 5 requests/second.
# A 0.30 s minimum interval keeps the workflow below both the second-level
# and minute-level request caps, even when title/SMILES/synonym lookups are
# performed for many terms.
PUBCHEM_MIN_INTERVAL_SEC = 0.30
PUBCHEM_YELLOW_SLEEP_SEC = 2.0
PUBCHEM_RED_SLEEP_SEC = 60.0
PUBCHEM_REQUEST_HEADERS = {
    "User-Agent": "GEOMeta/1.0 PubChem-rate-limited-stage3-mapping"
}

_PUBCHEM_SESSION = requests.Session()
_PUBCHEM_LAST_REQUEST_TS = 0.0


def _pubchem_wait_before_request() -> None:
    """Apply a process-level hard delay before every PubChem request."""
    global _PUBCHEM_LAST_REQUEST_TS

    now = time.monotonic()
    elapsed = now - _PUBCHEM_LAST_REQUEST_TS
    wait = PUBCHEM_MIN_INTERVAL_SEC - elapsed

    if wait > 0:
        time.sleep(wait)

    _PUBCHEM_LAST_REQUEST_TS = time.monotonic()


def _pubchem_retry_after_seconds(headers: Any) -> Optional[float]:
    """Read Retry-After header when PubChem/HTTP gateway provides one."""
    try:
        raw = headers.get("Retry-After", "")
    except Exception:
        return None

    raw = str(raw).strip()
    if not raw:
        return None

    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def _pubchem_throttle_state(headers: Any) -> str:
    """Return Green, Yellow, Red, or Unknown from X-Throttling-Control."""
    try:
        raw = str(headers.get("X-Throttling-Control", ""))
    except Exception:
        return "Unknown"

    low = raw.lower()
    if "red" in low:
        return "Red"
    if "yellow" in low:
        return "Yellow"
    if "green" in low:
        return "Green"
    return "Unknown"


def _pubchem_header_delay_seconds(headers: Any) -> float:
    """Convert PubChem throttling headers into a conservative client-side pause."""
    retry_after = _pubchem_retry_after_seconds(headers)
    if retry_after is not None:
        return retry_after

    throttle_state = _pubchem_throttle_state(headers)
    if throttle_state == "Red":
        return PUBCHEM_RED_SLEEP_SEC
    if throttle_state == "Yellow":
        return PUBCHEM_YELLOW_SLEEP_SEC
    return 0.0


def _request_json_with_status(
    url: str,
    timeout: int = 20,
    max_retries: int = 5,
) -> Tuple[Optional[Dict[str, Any]], str, str]:
    """
    PubChem JSON request with hard throttling, retry, and explicit status.

    Returns:
      data, status, error

    status values:
      ok
      not_found
      server_busy
      request_failed
      timeout
      invalid_json

    Rate-limit behavior:
      - wait >= PUBCHEM_MIN_INTERVAL_SEC before every request
      - inspect X-Throttling-Control after every response
      - slow down on Yellow and pause on Red
      - honor Retry-After when provided
    """
    last_error = ""

    # PubChem REST requests time out at about 30 s server-side.
    timeout = min(int(timeout), 30)

    for attempt in range(1, max_retries + 1):
        try:
            _pubchem_wait_before_request()

            r = _PUBCHEM_SESSION.get(
                url,
                timeout=timeout,
                headers=PUBCHEM_REQUEST_HEADERS,
            )
            text = r.text or ""
            throttle_state = _pubchem_throttle_state(r.headers)
            header_delay = _pubchem_header_delay_seconds(r.headers)

            if r.status_code == 200:
                if header_delay > 0:
                    time.sleep(header_delay)
                try:
                    return r.json(), "ok", ""
                except ValueError as e:
                    last_error = f"invalid_json: {e}; throttling={throttle_state}"
                    return None, "invalid_json", last_error

            if r.status_code == 404:
                if header_delay > 0:
                    time.sleep(header_delay)
                return None, "not_found", f"HTTP 404 not found; throttling={throttle_state}"

            if (
                r.status_code in {429, 500, 502, 503, 504}
                or "PUGREST.ServerBusy" in text
                or "too many requests" in text.lower()
                or "server busy" in text.lower()
            ):
                last_error = f"HTTP {r.status_code}; throttling={throttle_state}; body={text[:300]}"
                if attempt < max_retries:
                    time.sleep(max(0.75 * attempt, header_delay))
                    continue
                return None, "server_busy", last_error

            last_error = f"HTTP {r.status_code}; throttling={throttle_state}; body={text[:300]}"
            if attempt < max_retries:
                time.sleep(max(0.75 * attempt, header_delay))
                continue
            return None, "request_failed", last_error

        except requests.Timeout as e:
            last_error = f"timeout: {e}"
            if attempt < max_retries:
                time.sleep(0.75 * attempt)
                continue
            return None, "timeout", last_error

        except requests.RequestException as e:
            last_error = f"request_exception: {e}"
            if attempt < max_retries:
                time.sleep(0.75 * attempt)
                continue
            return None, "request_failed", last_error

    return None, "request_failed", last_error

def _request_json(url: str, timeout: int = 20, max_retries: int = 5):
    """
    Backward-compatible wrapper for older helper calls.
    Existing title/smiles/synonym helpers can keep using _request_json().
    """
    data, _, _ = _request_json_with_status(
        url=url,
        timeout=timeout,
        max_retries=max_retries,
    )
    return data


def pubchem_cid_lookup_from_name(
    term: str,
    timeout: int = 20,
    max_retries: int = 5,
) -> Tuple[Optional[str], str, str]:
    """
    PubChem name-to-CID lookup with explicit status.

    Returns:
      cid, status, error
    """
    if not term or not str(term).strip():
        return None, "pubchem_direct_no_query", "No valid PubChem query term."

    q = requests.utils.quote(str(term).strip())
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{q}/cids/JSON"

    data, request_status, error = _request_json_with_status(
        url=url,
        timeout=timeout,
        max_retries=max_retries,
    )

    if request_status == "not_found":
        return None, "pubchem_direct_not_found", error

    if request_status == "server_busy":
        return None, "pubchem_direct_server_busy", error

    if request_status == "timeout":
        return None, "pubchem_direct_timeout", error

    if request_status != "ok":
        return None, "pubchem_direct_request_failed", error

    cids = data.get("IdentifierList", {}).get("CID", []) if isinstance(data, dict) else []
    if not cids:
        return None, "pubchem_direct_not_found", "PubChem response contained no CID."

    return normalize_pubchem_cid(cids[0]), "pubchem_direct_cid_found", ""

def pubchem_cid_from_name(term: str, timeout: int = 20) -> Optional[str]:
    """
    Backward-compatible CID helper.
    """
    cid, _, _ = pubchem_cid_lookup_from_name(term, timeout=timeout, max_retries=5)
    return cid


def pubchem_cid_from_url(pubchem_url: str) -> str:
    """Extract a CID from common PubChem compound URLs."""
    v = _blank(pubchem_url)
    if not v:
        return ""
    m = re.search(r"/compound/(?:cid/)?(\d+)(?:[/?#]|$)", v, flags=re.I)
    if m:
        return normalize_pubchem_cid(m.group(1))
    return ""


def _find_pubchem_record_smiles(node: Any) -> str:
    """Recursively search a PUG-View record JSON object for canonical SMILES."""
    if isinstance(node, dict):
        heading = str(node.get("TOCHeading", "")).strip().lower()
        if "smiles" in heading:
            info_items = node.get("Information", [])
            if isinstance(info_items, list):
                for item in info_items:
                    value = item.get("Value", {}) if isinstance(item, dict) else {}
                    strings = value.get("StringWithMarkup") if isinstance(value, dict) else None
                    if isinstance(strings, list):
                        for s_item in strings:
                            text = s_item.get("String", "") if isinstance(s_item, dict) else ""
                            if text and " " not in text.strip():
                                return text.strip()
                    sval = value.get("String") if isinstance(value, dict) else None
                    if isinstance(sval, str) and sval.strip():
                        return sval.strip()
        for value in node.values():
            hit = _find_pubchem_record_smiles(value)
            if hit:
                return hit
    elif isinstance(node, list):
        for item in node:
            hit = _find_pubchem_record_smiles(item)
            if hit:
                return hit
    return ""


def pubchem_record_smiles_from_cid(cid: str, timeout: int = 20) -> str:
    cid = normalize_pubchem_cid(cid)
    if not cid:
        return ""
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON"
    data = _request_json(url, timeout=timeout)
    return _find_pubchem_record_smiles(data) if data else ""


def pubchem_title_and_smiles_from_cid(cid: str, timeout: int = 20) -> Dict[str, str]:
    cid = normalize_pubchem_cid(cid)
    fallback = {
        "Title": "",
        "CanonicalSMILES": "",
        "PubChemURL": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}" if cid else "",
    }

    if not cid:
        return fallback

    url = (
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/"
        f"{cid}/property/Title,CanonicalSMILES/JSON"
    )
    data = _request_json(url, timeout=timeout)

    if not data:
        fallback["CanonicalSMILES"] = pubchem_record_smiles_from_cid(cid, timeout=timeout)
        return fallback

    try:
        p = data["PropertyTable"]["Properties"][0]
        smiles = _blank(p.get("CanonicalSMILES"))
        if not smiles:
            smiles = pubchem_record_smiles_from_cid(cid, timeout=timeout)
        return {
            "Title": _blank(p.get("Title")),
            "CanonicalSMILES": smiles,
            "PubChemURL": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
        }
    except Exception:
        fallback["CanonicalSMILES"] = pubchem_record_smiles_from_cid(cid, timeout=timeout)
        return fallback

def pubchem_synonyms_for_cid(cid: str, timeout: int = 20, max_synonyms: int = 500) -> set[str]:
    """Return lower-case PubChem synonyms for a CID using the throttled request helper."""
    cid = normalize_pubchem_cid(cid)
    if not cid:
        return set()

    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/synonyms/JSON"
    data = _request_json(url, timeout=timeout)

    try:
        info = data.get("InformationList", {}).get("Information", [])
        if not info:
            return set()
        syns = info[0].get("Synonym", [])
    except Exception:
        return set()

    out = set()
    for syn in syns[:max_synonyms]:
        v = str(syn).strip().lower()
        if v:
            out.add(v)

    return out

def resolve_cp_term_with_pubchem(query_term: str, timeout: int = 20) -> Dict[str, str]:
    """
    Direct PubChem lookup using the standardized Pert_Post term.

    Accept a PubChem result only when the standardized term matches the
    PubChem title or one of the PubChem synonyms. Matching is case-insensitive
    and also uses a tolerant key that ignores hyphens, spaces, underscores,
    and punctuation.

    PubChem failure states are explicitly labeled so reviewers can distinguish:
      - true not found
      - server busy / request failed / timeout
      - unverified CID
    """
    raw = _blank(query_term)

    base_empty = {
        "CP_PubChem_Name": "",
        "CP_CID": "",
        "CP_CanonicalSMILES": "",
        "CP_PubChemURL": "",
    }

    if not raw:
        return {
            **base_empty,
            "CP_MatchType": "",
            "CP_Map_Explanation": "No valid PubChem query term.",
            "CP_Map_Method": "pubchem_direct_no_query",
            "CP_Query_Status": "pubchem_direct_no_query",
            "CP_Query_Error": "No valid PubChem query term.",
            "CP_Query_Attempted_Term": "",
        }

    cid, cid_status, cid_error = pubchem_cid_lookup_from_name(
    raw,
    timeout=timeout,
    max_retries=5,
    )

    if not cid:
        match_type = {
            "pubchem_direct_not_found": "not_found",
            "pubchem_direct_server_busy": "server_busy",
            "pubchem_direct_timeout": "timeout",
            "pubchem_direct_request_failed": "request_failed",
        }.get(cid_status, "request_failed")

        explanation = {
            "pubchem_direct_not_found": (
                "Direct PubChem lookup returned no CID for standardized Pert_Post term; "
                "manual compound-name verification is required."
            ),
            "pubchem_direct_server_busy": (
                "PubChem server was busy or rate-limited during direct lookup; "
                "rerun PubChem mapping later."
            ),
            "pubchem_direct_timeout": (
                "PubChem direct lookup timed out; rerun PubChem mapping later."
            ),
            "pubchem_direct_request_failed": (
                "PubChem direct lookup failed due to request/response error; "
                "rerun PubChem mapping later."
            ),
        }.get(
            cid_status,
            "Direct PubChem lookup failed for standardized Pert_Post term.",
        )

        return {
            **base_empty,
            "CP_MatchType": match_type,
            "CP_Map_Explanation": explanation,
            "CP_Map_Method": cid_status,
            "CP_Query_Status": cid_status,
            "CP_Query_Error": cid_error,
            "CP_Query_Attempted_Term": raw,
        }

    props = pubchem_title_and_smiles_from_cid(cid, timeout=timeout)
    title = _blank(props.get("Title"))

    raw_lc = raw.lower()
    title_lc = title.lower()
    raw_key = normalize_compound_match_key(raw)
    title_key = normalize_compound_match_key(title)

    if title and (raw_lc == title_lc or raw_key == title_key):
        return {
            "CP_PubChem_Name": title,
            "CP_CID": normalize_pubchem_cid(cid),
            "CP_CanonicalSMILES": _blank(props.get("CanonicalSMILES")),
            "CP_PubChemURL": _blank(props.get("PubChemURL")),
            "CP_MatchType": "exact_title",
            "CP_Map_Explanation": "Direct PubChem lookup matched standardized Pert_Post to PubChem title.",
            "CP_Map_Method": "pubchem_direct_title",
            "CP_Query_Status": "pubchem_direct_title",
            "CP_Query_Error": "",
            "CP_Query_Attempted_Term": raw,
        }

    syns = pubchem_synonyms_for_cid(cid, timeout=timeout)
    syn_keys = {normalize_compound_match_key(s) for s in syns}

    if raw_lc in syns or raw_key in syn_keys:
        return {
            "CP_PubChem_Name": title if title else raw,
            "CP_CID": normalize_pubchem_cid(cid),
            "CP_CanonicalSMILES": _blank(props.get("CanonicalSMILES")),
            "CP_PubChemURL": _blank(props.get("PubChemURL")),
            "CP_MatchType": "synonym",
            "CP_Map_Explanation": "Direct PubChem lookup matched standardized Pert_Post to PubChem synonym.",
            "CP_Map_Method": "pubchem_direct_synonym",
            "CP_Query_Status": "pubchem_direct_synonym",
            "CP_Query_Error": "",
            "CP_Query_Attempted_Term": raw,
        }

    return {
        **base_empty,
        "CP_MatchType": "unverified",
        "CP_Map_Explanation": (
            "PubChem returned a CID, but the standardized Pert_Post term did not match "
            "the PubChem title or synonyms after tolerant normalization."
        ),
        "CP_Map_Method": "pubchem_direct_unverified",
        "CP_Query_Status": "pubchem_direct_unverified",
        "CP_Query_Error": "",
        "CP_Query_Attempted_Term": raw,
    }

def backfill_cp_smiles_from_existing_ids(df: pd.DataFrame, timeout: int = 20) -> pd.DataFrame:
    """Backfill missing CP_CanonicalSMILES from existing CP_CID or CP_PubChemURL.

    This function only changes rows that already have compound identifiers/URLs
    and an empty CP_CanonicalSMILES value. It also normalizes CP_CID to
    integer-like text before returning.
    """
    df = df.copy()
    for c in ["CP_CID", "CP_CanonicalSMILES", "CP_PubChemURL"]:
        if c not in df.columns:
            df[c] = ""

    df["CP_CID"] = df["CP_CID"].map(normalize_pubchem_cid)

    smiles_cache: Dict[str, str] = {}
    for idx in df.index:
        current_smiles = _blank(df.at[idx, "CP_CanonicalSMILES"])
        if current_smiles:
            continue

        cid = normalize_pubchem_cid(df.at[idx, "CP_CID"])
        if not cid:
            cid = pubchem_cid_from_url(df.at[idx, "CP_PubChemURL"])
            if cid:
                df.at[idx, "CP_CID"] = cid

        if not cid:
            continue

        if cid not in smiles_cache:
            props = pubchem_title_and_smiles_from_cid(cid, timeout=timeout)
            smiles_cache[cid] = _blank(props.get("CanonicalSMILES"))

        if smiles_cache[cid]:
            df.at[idx, "CP_CanonicalSMILES"] = smiles_cache[cid]
            if "CP_Map_Method" in df.columns and not _blank(df.at[idx, "CP_Map_Method"]):
                df.at[idx, "CP_Map_Method"] = "pubchem_cid_smiles_backfill"
            if "CP_Map_Explanation" in df.columns and not _blank(df.at[idx, "CP_Map_Explanation"]):
                df.at[idx, "CP_Map_Explanation"] = "CanonicalSMILES backfilled from existing PubChem CID/URL."

    return df


# -------------------------
# Candidate retrieval
# -------------------------
def ctd_candidates_for_term(
    term: str,
    ctd_df: pd.DataFrame,
    vectorizer: TfidfVectorizer,
    tfidf_matrix,
    top_k: int = 8,
) -> List[Dict[str, Any]]:
    raw = _s(term)
    norm = normalize_lookup_term(raw)

    if norm in {"NA", "Unknown"}:
        return []

    exact = ctd_df[ctd_df["norm_name"] == norm]
    if not exact.empty:
        return [
            {
                "DiseaseName": r["DiseaseName"],
                "DiseaseID": r["DiseaseID"],
                "score": 100.0,
            }
            for _, r in exact.head(top_k).iterrows()
        ]

    syn_hits = ctd_df[
        ctd_df["norm_syn"].str.contains(re.escape(norm), regex=True, na=False)
        | ctd_df["search_text"].str.contains(re.escape(norm), regex=True, na=False)
    ]

    rows: List[Dict[str, Any]] = []
    seen = set()

    for _, r in syn_hits.head(top_k).iterrows():
        key = (r["DiseaseName"], r["DiseaseID"])
        if key in seen:
            continue
        seen.add(key)
        score = max(
            _wratio(norm, normalize_lookup_term(r["DiseaseName"])),
            _wratio(norm, normalize_lookup_term(r["Synonyms"])),
        )
        rows.append(
            {
                "DiseaseName": r["DiseaseName"],
                "DiseaseID": r["DiseaseID"],
                "score": round(score, 2),
            }
        )

    if rows:
        return rows[:top_k]

    query_vec = vectorizer.transform([norm])
    sims = cosine_similarity(query_vec, tfidf_matrix)[0]
    idxs = sims.argsort()[::-1][:top_k]

    out: List[Dict[str, Any]] = []
    seen = set()

    for idx in idxs:
        r = ctd_df.iloc[int(idx)]
        key = (r["DiseaseName"], r["DiseaseID"])
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "DiseaseName": r["DiseaseName"],
                "DiseaseID": r["DiseaseID"],
                "score": round(float(sims[idx]) * 100.0, 2),
            }
        )

    return out


def _ctd_row_to_disease_record(
    row: pd.Series,
    method: str,
    explanation: str,
    review_required: bool = False,
) -> Dict[str, Any]:
    """
    Convert one CTD/MEDIC row into the Stage 3 disease mapping record format.
    """
    slim = _blank(row.get("SlimMappings"))
    broad = _broad_category_or_na(infer_broad_disease_category_from_slim_mappings(slim))

    return {
        "Disease_Mapped": _blank(row.get("DiseaseName")),
        "DiseaseID": _blank(row.get("DiseaseID")),
        "AltDiseaseIDs": _blank(row.get("AltDiseaseIDs")),
        "Definition": _blank(row.get("Definition")),
        "ParentIDs": _blank(row.get("ParentIDs")),
        "TreeNumbers": _blank(row.get("TreeNumbers")),
        "ParentTreeNumbers": _blank(row.get("ParentTreeNumbers")),
        "Synonyms": _blank(row.get("Synonyms")),
        "SlimMappings": slim,
        "Broad_Disease_Category": broad,
        "Disease_Map_Explanation": explanation,
        "Disease_Review_Required": review_required,
        "Disease_Map_Method": method,
        "Final_Diease_Term_Flag": "NEW_TERM_REFERENCE" if method.startswith("ctd_reference") else "",
        "Comment1": "",
        "Comment2": "",
        "Match_MESHCode": "",
    }


def infer_broad_disease_category_from_slim_mappings(slim_mappings: Any) -> str:
    """
    Infer broad GEOMeta disease category from CTD/MEDIC SlimMappings.
    Used only when the disease term is not already in disease_mappings.xlsx.
    """
    text = _blank(slim_mappings).lower()

    if not text:
        return ""

    if "cancer" in text or "neoplasm" in text:
        return "Oncology"
    if "immune" in text or "autoimmune" in text:
        return "Immune"
    if "infection" in text or "infectious" in text or "viral" in text or "bacterial" in text:
        return "Infection"
    if "cardiovascular" in text or "heart" in text or "vascular" in text:
        return "Cardiovascular"
    if "respiratory" in text or "lung" in text:
        return "Respiratory"
    if "digestive" in text or "gastrointestinal" in text:
        return "Digestive"
    if "genetic" in text or "congenital" in text:
        return "Genetic"
    if "nervous system" in text or "mental disorder" in text:
        return "Neurology"
    if "metabolic" in text or "endocrine" in text:
        return "Metabolic"
    if "urogenital" in text or "reproductive" in text:
        return "Genitourinary/Urogenital"
    if "musculoskeletal" in text:
        return "Musculoskeletal"
    if "skin" in text:
        return "Dermatology"
    if "signs and symptoms" in text or "pathology" in text:
        return "Signs/symptoms"

    return ""


def build_ctd_exact_synonym_lookup(ctd_df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    """
    Build exact normalized lookup from CTD/MEDIC DiseaseName and Synonyms.
    """
    lookup: Dict[str, Dict[str, Any]] = {}

    for _, row in ctd_df.iterrows():
        keys = set()
        keys.update(lookup_key_variants(row.get("DiseaseName", "")))

        syns = _blank(row.get("Synonyms", ""))
        if syns:
            for syn in re.split(r"\|", syns):
                keys.update(lookup_key_variants(syn))

        rec = _ctd_row_to_disease_record(
            row,
            method="ctd_reference_exact_or_synonym",
            explanation="Mapped by exact normalized match to CTD/MEDIC DiseaseName or Synonyms.",
            review_required=False,
        )

        for k in keys:
            if k and k not in lookup:
                lookup[k] = rec

    return lookup


def lookup_ctd_reference_record(term: Any, ctd_exact_lookup: Dict[str, Dict[str, Any]]) -> Dict[str, Any] | None:
    """
    Check CTD/MEDIC reference using DiseaseName/Synonyms.
    """
    for key in lookup_key_variants(term):
        if key in ctd_exact_lookup:
            return ctd_exact_lookup[key]
    return None

def repair_invalid_disease_mappings_against_ctd(
    df: pd.DataFrame,
    ctd_df: pd.DataFrame,
    ctd_exact_lookup: Dict[str, Dict[str, Any]],
) -> pd.DataFrame:
    """
    Final Stage 3 disease safeguard.

    If Disease_Mapped came from a prior mapping file but is not a valid
    CTD/MEDIC DiseaseName, try to repair it using CTD exact/synonym lookup
    from Disease_Post or the current Disease_Mapped label.
    """
    df = df.copy()

    if "Disease_Mapped" not in df.columns:
        return df

    valid_ctd_names = set(ctd_df["DiseaseName"].fillna("").astype(str).str.strip())
    allowed_non_disease = {
        "NA",
        "Normal",
        "Adjacent Normal",
        "No Disease Mentioned",
    }

    disease_payload_cols = [
        "Disease_Mapped",
        "DiseaseID",
        "AltDiseaseIDs",
        "Definition",
        "ParentIDs",
        "TreeNumbers",
        "ParentTreeNumbers",
        "Synonyms",
        "SlimMappings",
        "Broad_Disease_Category",
        "Disease_Map_Explanation",
        "Disease_Review_Required",
        "Disease_Map_Method",
        "Final_Diease_Term_Flag",
        "Comment1",
        "Comment2",
        "Match_MESHCode",
    ]

    for idx in df.index:
        mapped = _mapped_na(df.at[idx, "Disease_Mapped"])
        if mapped in allowed_non_disease or mapped in valid_ctd_names:
            continue

        disease_post = df.at[idx, "Disease_Post"] if "Disease_Post" in df.columns else ""

        rec = (
            lookup_ctd_reference_record(disease_post, ctd_exact_lookup)
            or lookup_ctd_reference_record(mapped, ctd_exact_lookup)
        )

        if rec is None:
            # Keep the value so Stage 4 can flag it, but force broad category
            # for obvious cancer-like labels below.
            continue

        for col in disease_payload_cols:
            if col in df.columns:
                df.at[idx, col] = rec.get(col, False if col == "Disease_Review_Required" else "")

        df.at[idx, "Disease_Map_Method"] = (
            str(df.at[idx, "Disease_Map_Method"]) + "|ctd_reference_rescue"
            if "Disease_Map_Method" in df.columns
            else "ctd_reference_rescue"
        )

    return df


# -------------------------
# Novel term helpers
# -------------------------
def _build_novel_term_df(terms: List[str], domain: str) -> pd.DataFrame:
    if not terms:
        return pd.DataFrame(columns=["domain", "raw_term"])
    return pd.DataFrame({"domain": [domain] * len(terms), "raw_term": sorted(set(terms))})


def _mapping_cache_to_review_df(cache: Dict[str, Any], domain: str, methods: set[str]) -> pd.DataFrame:
    rows = []
    for raw, rec in cache.items():
        if not isinstance(rec, dict):
            continue
        method = _s(
            rec.get("Disease_Map_Method")
            or rec.get("Tissue_Map_Method")
            or rec.get("CP_Map_Method")
        )
        if method not in methods:
            continue
        row = {"domain": domain, "raw_term": raw, "map_method": method}
        row.update(rec)
        rows.append(row)
    return pd.DataFrame(rows)


def save_stage3_novel_term_workbooks(
    cfg,
    novel_dir: Path,
    novel_disease_df: pd.DataFrame,
    novel_tissue_df: pd.DataFrame,
    novel_pert_df: pd.DataFrame,
    disease_cache: Dict[str, Any],
    tissue_cache: Dict[str, Any],
    cp_cache: Dict[str, Any],
) -> Path:
    """Save manual-review workbooks for newly mapped or unresolved Stage3 terms.

    The combined workbook has separate sheets by domain and includes both the raw
    novel term queues and enriched LLM/composite mapping records. Separate per-domain
    workbooks are also saved for easier manual review.
    """
    novel_dir.mkdir(parents=True, exist_ok=True)
    run_version = cfg.run_version

    disease_review_df = _mapping_cache_to_review_df(
        disease_cache,
        "Disease",
        {"llm_ctd", "llm_no_match", "llm_invalid", "llm_missing", "composite_disease_term"},
    )
    tissue_review_df = _mapping_cache_to_review_df(
        tissue_cache,
        "Tissue",
        {"llm_tissue", "llm_missing"},
    )
    pert_review_df = _mapping_cache_to_review_df(
        cp_cache,
        "Pert",
        {
            "pubchem_direct_not_found",
            "pubchem_direct_server_busy",
            "pubchem_direct_request_failed",
            "pubchem_direct_timeout",
            "pubchem_direct_unverified",
            "pubchem_direct_no_query",
        },
    )

    combined_raw_df = pd.concat([novel_disease_df, novel_tissue_df, novel_pert_df], ignore_index=True)
    combined_review_df = pd.concat([disease_review_df, tissue_review_df, pert_review_df], ignore_index=True)

    combined_fp = novel_dir / f"{run_version}_stage3_novel_terms.xlsx"
    disease_fp = novel_dir / f"{run_version}_stage3_novel_disease_terms.xlsx"
    tissue_fp = novel_dir / f"{run_version}_stage3_novel_tissue_terms.xlsx"
    pert_fp = novel_dir / f"{run_version}_stage3_novel_pert_terms.xlsx"

    with pd.ExcelWriter(combined_fp, engine="openpyxl") as writer:
        combined_raw_df.to_excel(writer, sheet_name="novel_raw_terms", index=False)
        disease_review_df.to_excel(writer, sheet_name="disease_review", index=False)
        tissue_review_df.to_excel(writer, sheet_name="tissue_review", index=False)
        pert_review_df.to_excel(writer, sheet_name="pert_review", index=False)
        combined_review_df.to_excel(writer, sheet_name="all_review_terms", index=False)

    disease_review_df.to_excel(disease_fp, index=False)
    tissue_review_df.to_excel(tissue_fp, index=False)
    pert_review_df.to_excel(pert_fp, index=False)

    return combined_fp


# -------------------------
# Review / correction
# -------------------------
def _review_and_correct_stage3(
    df: pd.DataFrame,
    prior_tissue: Dict[str, Dict[str, Any]],
    prior_cp: Dict[str, Dict[str, Any]],
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    review_rows: List[Dict[str, Any]] = []

    def record(gsm_id: str, field: str, old: str, new: str, reason: str):
        review_rows.append(
            {
                "GSM_ID": _s(gsm_id),
                "field": field,
                "old_value": _s(old),
                "new_value": _s(new),
                "reason": reason,
            }
        )

    for field in ["Disease_Pre", "Disease_Post", "Tissue_Pre", "Tissue_Post", "Pert_Pre", "Pert_Post"]:
        if field in df.columns:
            old_vals = df[field].copy()
            df[field] = df[field].map(strip_extract_infer_suffix)
            for idx in df.index:
                old = _s(old_vals.loc[idx])
                new = _s(df.at[idx, field])
                if old != new:
                    record(df.at[idx, "GSM_ID"], field, old, new, "strip_extract_infer_suffix")

    if {"Tissue_Post", "Tissue_Mapped"}.issubset(df.columns):
        for idx in df.index:
            prior_rec = lookup_prior_record(df.at[idx, "Tissue_Post"], prior_tissue, domain="tissue")
            if prior_rec is not None:
                wanted = _blank(prior_rec.get("Tissue_Mapped"))
                if wanted and _blank(df.at[idx, "Tissue_Mapped"]) != wanted:
                    old = _s(df.at[idx, "Tissue_Mapped"])
                    df.at[idx, "Tissue_Mapped"] = wanted

                    if "Tissue_Map_Explanation" in df.columns:
                        df.at[idx, "Tissue_Map_Explanation"] = _blank(
                            prior_rec.get("Tissue_Map_Explanation")
                        )
                    if "Tissue_Map_Method" in df.columns:
                        df.at[idx, "Tissue_Map_Method"] = "prior_tissue_file"

                    record(df.at[idx, "GSM_ID"], "Tissue_Mapped", old, wanted, "prior_tissue_mapping_override")

    disease_payload_cols = [
        "Disease_Mapped",
        "DiseaseID",
        "AltDiseaseIDs",
        "Definition",
        "ParentIDs",
        "TreeNumbers",
        "ParentTreeNumbers",
        "Synonyms",
        "SlimMappings",
    ]

    if "Disease_Post" in df.columns:
        for idx in df.index:
            disease_post = df.at[idx, "Disease_Post"]

            if _no_disease_state(disease_post):
                rec = _no_disease_record(disease_post)
                for col in disease_payload_cols + ["Broad_Disease_Category", "Disease_Map_Explanation", "Disease_Map_Method", "Disease_Review_Required"]:
                    if col in df.columns:
                        wanted = rec.get(col, False if col == "Disease_Review_Required" else "")
                        old = df.at[idx, col]
                        if _s(old) != _s(wanted):
                            df.at[idx, col] = wanted
                            record(df.at[idx, "GSM_ID"], col, old, wanted, "preserve_explicit_no_disease_state")

            elif _is_composite_disease_term(disease_post):
                rec = _composite_disease_record(disease_post)
                for col in disease_payload_cols + [
                    "Broad_Disease_Category", "Disease_Map_Explanation", "Disease_Map_Method",
                    "Disease_Review_Required", "Final_Diease_Term_Flag", "Comment1", "Comment2", "Match_MESHCode"
                ]:
                    if col in df.columns:
                        wanted = rec.get(col, False if col == "Disease_Review_Required" else "")
                        old = df.at[idx, col]
                        if _s(old) != _s(wanted):
                            df.at[idx, col] = wanted
                            record(df.at[idx, "GSM_ID"], col, old, wanted, "set_composite_disease_to_na")

    if {"Pert_Post", "Pert_Type"}.issubset(df.columns):
        for idx in df.index:
            if _s(df.at[idx, "Pert_Type"]) == "CP":
                rec = lookup_prior_record(df.at[idx, "Pert_Post"], prior_cp, domain="cp")
                if rec is not None:
                    for col in [
                        "CP_PubChem_Name",
                        "CP_CID",
                        "CP_CanonicalSMILES",
                        "CP_PubChemURL",
                        "CP_MatchType",
                        "CP_Map_Explanation",
                    ]:
                        if col in df.columns:
                            wanted = _blank(rec.get(col))
                            if wanted and _blank(df.at[idx, col]) != wanted:
                                old = _s(df.at[idx, col])
                                df.at[idx, col] = wanted
                                record(df.at[idx, "GSM_ID"], col, old, wanted, "prior_cp_mapping_override")

                    if "CP_Map_Method" in df.columns:
                        df.at[idx, "CP_Map_Method"] = "prior_cp_file"

    return df, pd.DataFrame(review_rows)


# -------------------------
# Stage 3 main
# -------------------------

RNA_SOURCE_AUTOMAP_SYSTEM = """
You are a strict RNA source mapping assistant.

Use the provided RNA source mapping prompt as the source of truth.
Return STRICT JSON only. No markdown. No commentary.

Input JSON:
{
  "terms": [
    {
      "RNA_Source_Pre": "...",
      "count": 10,
      "example_GSE_IDs": ["..."],
      "examples": [
        {"GSM_ID": "...", "GSE_ID": "...", "GSE_Info": "...", "GSM_Info": "..."}
      ]
    }
  ]
}

Output JSON:
{
  "mappings": [
    {
      "RNA_Source_Pre": "...",
      "Standardized_Term": "...",
      "RNA_Source_Mapped": "... or null",
      "Reasoning": "...",
      "Confidence": "high|medium|low"
    }
  ]
}

Rules:
- Return exactly one mapping for each input term.
- Use only these final label formats:
  Tissue: xx
  Cells: xx
  Cell Line: xx
  Biofluid: xx
  Other
  null
- Use null only when the RNA source should intentionally be blank according to the prompt.
- Do not invent unsupported labels.
- Do not simply copy the input unless it already satisfies the mapping rules.
"""

def normalize_cell_line_key(x: Any) -> str:
    """
    Normalize cell-line names for matching:
    HeLa, HELA, HeLa cells, Cell Line: HeLa -> hela
    NIH:OVCAR-3 -> nihovcar3
    """
    v = _blank(x)
    if not v:
        return ""

    v = re.sub(r"^(cell line|cells?)\s*:\s*", "", v, flags=re.I).strip()
    v = re.sub(r"\bcells?\b$", "", v, flags=re.I).strip()

    return re.sub(r"[^a-z0-9]", "", v.lower())


def load_cell_line_reference_lookup(path: Path) -> Dict[str, Dict[str, Any]]:
    """
    Load cell-line reference file for RNA_Source mapping.

    Expected useful columns:
      CellLineName, StrippedCellLineName, CCLEName, ModelIDAlias, RRID, ModelID
    """
    if not path.exists():
        print(f"[Stage3 RNA_Source] cell line reference not found: {path}")
        return {}

    ref = pd.read_csv(path)
    ref.columns = ref.columns.astype(str).str.strip()

    lookup: Dict[str, Dict[str, Any]] = {}

    name_cols = [
        "CellLineName",
        "StrippedCellLineName",
        "CCLEName",
        "ModelIDAlias",
        "RRID",
        "ModelID",
    ]

    for _, r in ref.iterrows():
        canonical = _blank(r.get("CellLineName"))
        if not canonical:
            canonical = _blank(r.get("StrippedCellLineName"))
        if not canonical:
            continue

        rec = {
            "RNA_Source_Mapped": f"Cell Line: {canonical}",
            "RNA_Source_Mapping_Status": "Mapped: cell-line reference match",
            "RNA_Source_Mapping_Method": "cell_line_reference_file",
            "RNA_Source_Mapping_Confidence": "high",
            "RNA_Source_Mapping_Reason": (
                "RNA_Source_Post matched cell-line reference file "
                f"(ModelID={_blank(r.get('ModelID'))}; RRID={_blank(r.get('RRID'))})."
            ),
            "RNA_Source_Review_Required": False,
        }

        for c in name_cols:
            val = _blank(r.get(c))
            if not val:
                continue

            keys = {normalize_cell_line_key(val)}

            # CCLEName often looks like A549_LUNG; also add A549.
            if c == "CCLEName" and "_" in val:
                keys.add(normalize_cell_line_key(val.split("_")[0]))

            # ModelIDAlias may contain multiple aliases.
            for part in re.split(r"[;|,]", val):
                keys.add(normalize_cell_line_key(part))

            for key in keys:
                if key and key not in lookup:
                    lookup[key] = rec

    return lookup


def apply_cell_line_reference_to_rna_source(
    df: pd.DataFrame,
    cell_line_lookup: Dict[str, Dict[str, Any]],
    source_col: str = "RNA_Source_Post",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    For unresolved RNA_Source terms, identify known cell lines using reference file.
    """
    df = df.copy()

    if not cell_line_lookup or source_col not in df.columns:
        return df, pd.DataFrame()

    for c in [
        "RNA_Source_Mapped",
        "RNA_Source_Mapping_Status",
        "RNA_Source_Mapping_Method",
        "RNA_Source_Mapping_Confidence",
        "RNA_Source_Mapping_Reason",
        "RNA_Source_Review_Required",
    ]:
        if c not in df.columns:
            df[c] = False if c == "RNA_Source_Review_Required" else ""

    mapped_blank = (
        df["RNA_Source_Mapped"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
        .isin({"", "na", "nan", "none", "unknown", "null"})
    )

    source_present = (
        df[source_col]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
        .map(lambda x: x not in {"", "na", "nan", "none", "unknown", "null"})
    )

    update_mask = mapped_blank & source_present

    decisions = []

    for idx in df.index[update_mask]:
        raw = str(df.at[idx, source_col]).strip()
        key = normalize_cell_line_key(raw)

        rec = cell_line_lookup.get(key)

        # Also try removing controlled prefix, e.g. "Cells: A549".
        if rec is None and ":" in raw:
            rec = cell_line_lookup.get(normalize_cell_line_key(raw.split(":", 1)[1]))

        if rec is None:
            continue

        for col, val in rec.items():
            df.at[idx, col] = val

        decisions.append(
            {
                "GSM_ID": df.at[idx, "GSM_ID"] if "GSM_ID" in df.columns else "",
                "GSE_ID": df.at[idx, "GSE_ID"] if "GSE_ID" in df.columns else "",
                "RNA_Source_Post": raw,
                "RNA_Source_Mapped": rec["RNA_Source_Mapped"],
                "RNA_Source_Mapping_Method": rec["RNA_Source_Mapping_Method"],
                "RNA_Source_Mapping_Reason": rec["RNA_Source_Mapping_Reason"],
            }
        )

    return df, pd.DataFrame(decisions)

def _valid_rna_source_mapped_value(x: Any) -> bool:
    """Validate final RNA_Source_Mapped against allowed prompt formats."""
    if x is None:
        return True

    v = str(x).strip()
    if not v or v.lower() in {"null", "none", "nan", "na", "unknown"}:
        return True

    if v == "Other":
        return True

    return bool(re.match(r"^(Tissue|Cells|Cell Line|Biofluid):\s*.+$", v))


def _clean_rna_source_mapped_value(x: Any) -> str:
    """Convert prompt null to blank; preserve valid mapped labels."""
    if x is None:
        return ""

    v = str(x).strip()
    if not v or v.lower() in {"null", "none", "nan", "na", "unknown"}:
        return ""

    return v


def _truncate_context_text(x: Any, max_chars: int = 1200) -> str:
    v = "" if x is None else str(x)
    v = re.sub(r"\s+", " ", v).strip()
    return v[:max_chars]


def _build_rna_source_term_payload(
    df: pd.DataFrame,
    source_col: str = "RNA_Source_Post",
    max_examples_per_term: int = 3,
) -> list[dict]:
    """
    Build one payload record per unresolved RNA_Source term.
    This keeps the LLM mapping task term-level rather than row-level.
    """
    source = df[source_col].fillna("").astype(str).str.strip()

    mapped = df.get("RNA_Source_Mapped", pd.Series("", index=df.index)).fillna("").astype(str).str.strip()
    status = df.get("RNA_Source_Mapping_Status", pd.Series("", index=df.index)).fillna("").astype(str)

    unresolved = (
        source.ne("")
        & ~source.str.lower().isin({"na", "nan", "none", "unknown"})
        & mapped.eq("")
        & status.str.contains("unmapped|needs review", case=False, regex=True, na=False)
    )

    work = df.loc[unresolved].copy()
    if work.empty:
        return []

    payload = []
    for term, sub in work.groupby(source_col, dropna=False):
        term = str(term).strip()
        if not term or term.lower() in {"na", "nan", "none", "unknown"}:
            continue

        examples = []
        for _, r in sub.head(max_examples_per_term).iterrows():
            examples.append(
                {
                    "GSM_ID": str(r.get("GSM_ID", "")),
                    "GSE_ID": str(r.get("GSE_ID", "")),
                    "GSE_Info": _truncate_context_text(r.get("GSE_Info", "")),
                    "GSM_Info": _truncate_context_text(r.get("GSM_Info", "")),
                }
            )

        payload.append(
            {
                "RNA_Source_Pre": term,
                "count": int(sub.shape[0]),
                "example_GSE_IDs": sorted(sub["GSE_ID"].astype(str).unique().tolist())[:10]
                if "GSE_ID" in sub.columns
                else [],
                "examples": examples,
            }
        )

    return payload


def map_unresolved_rna_source_terms_with_prompt(
    cfg,
    llm,
    df: pd.DataFrame,
    source_col: str = "RNA_Source_Post",
    batch_size: int = 20,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Map new RNA_Source terms using the same RNA source mapping prompt/rules
    used to build the reviewed mapping file.

    Reviewed mapping-file results are not changed.
    Only currently unmapped terms are processed.
    """
    df = df.copy()

    prompt_path = Path(cfg.workdir) / "mappings" / "rna_source" / "rna_source_mapping_prompt.md"
    if not prompt_path.exists():
        print(f"[Stage3 RNA_Source] Prompt not found; skipping GPT RNA source auto-mapping: {prompt_path}")
        return df, pd.DataFrame()

    prompt_text = read_prompt_file(prompt_path)

    term_payload = _build_rna_source_term_payload(df, source_col=source_col)
    if not term_payload:
        return df, pd.DataFrame()

    all_results = []

    for bi, chunk_terms in enumerate(_chunk(term_payload, batch_size)):
        payload = {"terms": chunk_terms}

        messages = [
            {
                "role": "system",
                "content": RNA_SOURCE_AUTOMAP_SYSTEM + "\n\nRNA source mapping prompt:\n" + prompt_text,
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]

        check_messages_token_budget(
            messages,
            budget=TokenBudget.from_config(cfg),
            context_label=f"Stage3 RNA_Source prompt-rule auto-map batch={bi}",
            action=str(getattr(cfg, "llm_token_budget_action", "raise")),
        )

        txt = llm.chat(messages, temperature=0.0)

        out = safe_json_loads_with_repair(
            txt,
            debug_dir=str(Path(cfg.debug_dir)),
            debug_tag=f"RNA_SOURCE_AUTOMAP_{bi}",
            llm_chat_fn=lambda msgs, temperature=0.0: llm.chat(msgs, temperature=temperature),
        )

        for r in out.get("mappings", []):
            raw = str(r.get("RNA_Source_Pre", "")).strip()
            mapped_raw = r.get("RNA_Source_Mapped", None)
            mapped = _clean_rna_source_mapped_value(mapped_raw)
            confidence = str(r.get("Confidence", "")).strip().lower()
            reasoning = str(r.get("Reasoning", "")).strip()
            standardized = str(r.get("Standardized_Term", "")).strip()

            if confidence not in {"high", "medium", "low"}:
                confidence = "low"

            valid = _valid_rna_source_mapped_value(mapped_raw)

            if not raw:
                continue

            all_results.append(
                {
                    "RNA_Source_Post": raw,
                    "Standardized_Term": standardized,
                    "RNA_Source_Mapped": mapped if valid else "Other",
                    "RNA_Source_Mapping_Status": (
                        "Mapped: LLM prompt-rule RNA source mapping"
                        if valid
                        else "Mapped: LLM prompt-rule fallback to Other after invalid output"
                    ),
                    "RNA_Source_Mapping_Method": "LLM RNA source mapping prompt",
                    "RNA_Source_Mapping_Confidence": confidence,
                    "RNA_Source_Mapping_Reason": reasoning if reasoning else "Mapped using RNA source mapping prompt.",
                    "RNA_Source_Review_Required": confidence == "low",
                    "GPT_Output_Valid": valid,
                }
            )

    result_df = pd.DataFrame(all_results)
    if result_df.empty:
        return df, result_df

    # If duplicate mappings are returned for the same term, keep highest confidence.
    conf_rank = {"high": 3, "medium": 2, "low": 1}
    result_df["_rank"] = result_df["RNA_Source_Mapping_Confidence"].map(conf_rank).fillna(0)
    result_df = (
        result_df.sort_values(["RNA_Source_Post", "_rank"], ascending=[True, False])
        .drop_duplicates("RNA_Source_Post", keep="first")
        .drop(columns=["_rank"])
        .reset_index(drop=True)
    )

    result_lookup = result_df.set_index("RNA_Source_Post").to_dict(orient="index")

    source = df[source_col].fillna("").astype(str).str.strip()
    mapped = df.get("RNA_Source_Mapped", pd.Series("", index=df.index)).fillna("").astype(str).str.strip()
    status = df.get("RNA_Source_Mapping_Status", pd.Series("", index=df.index)).fillna("").astype(str)

    update_mask = (
        source.isin(result_lookup.keys())
        & mapped.eq("")
        & status.str.contains("unmapped|needs review", case=False, regex=True, na=False)
    )

    for idx in df.index[update_mask]:
        term = str(df.at[idx, source_col]).strip()
        rec = result_lookup.get(term)
        if not rec:
            continue

        df.at[idx, "RNA_Source_Mapped"] = rec["RNA_Source_Mapped"]
        df.at[idx, "RNA_Source_Mapping_Status"] = rec["RNA_Source_Mapping_Status"]
        df.at[idx, "RNA_Source_Mapping_Method"] = rec["RNA_Source_Mapping_Method"]
        df.at[idx, "RNA_Source_Mapping_Confidence"] = rec["RNA_Source_Mapping_Confidence"]
        df.at[idx, "RNA_Source_Mapping_Reason"] = rec["RNA_Source_Mapping_Reason"]
        df.at[idx, "RNA_Source_Review_Required"] = bool(rec["RNA_Source_Review_Required"])

    return df, result_df

def reconcile_rna_source_status_after_automap(df_out: pd.DataFrame) -> pd.DataFrame:
    """
    Clean RNA_Source mapping status after reviewed mapping, cell-line reference
    mapping, and LLM prompt-rule automapping.

    Distinguish:
    1. RNA_Source_Post missing: mapping skipped, not review-required.
    2. RNA_Source_Post present but LLM/rules accepted null: intentional blank.
    3. stale unmapped status but mapped value exists: accepted automated mapping.
    """
    df_out = df_out.copy()

    required_cols = [
        "RNA_Source_Post",
        "RNA_Source_Mapped",
        "RNA_Source_Mapping_Status",
        "RNA_Source_Review_Required",
        "RNA_Source_Mapping_Method",
        "RNA_Source_Mapping_Confidence",
        "RNA_Source_Mapping_Reason",
    ]

    for c in required_cols:
        if c not in df_out.columns:
            df_out[c] = False if c == "RNA_Source_Review_Required" else ""

    source = (
        df_out["RNA_Source_Post"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    mapped = (
        df_out["RNA_Source_Mapped"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    status_unmapped = (
        df_out["RNA_Source_Mapping_Status"]
        .fillna("")
        .astype(str)
        .str.contains("Unmapped", case=False, na=False)
    )

    review_false = (
        df_out["RNA_Source_Review_Required"]
        .astype("string")
        .fillna("")
        .str.strip()
        .str.upper()
        .isin({"FALSE", "0", "NO", ""})
    )

    source_blank = source.str.lower().isin({"", "na", "nan", "none", "unknown", "null"})
    mapped_blank = mapped.str.lower().isin({"", "na", "nan", "none", "unknown", "null"})

    # Case 1: RNA_Source_Post is genuinely missing.
    # This is not an unresolved mapping term.
    missing_source_mask = status_unmapped & review_false & source_blank

    df_out.loc[missing_source_mask, "RNA_Source_Mapping_Status"] = (
        "Mapping skipped: RNA_Source_Post missing"
    )
    df_out.loc[missing_source_mask, "RNA_Source_Mapping_Method"] = (
        "not_applicable_missing_source"
    )
    df_out.loc[missing_source_mask, "RNA_Source_Mapping_Confidence"] = ""
    df_out.loc[missing_source_mask, "RNA_Source_Mapping_Reason"] = (
        "RNA_Source_Post is blank or unavailable; no RNA source mapping was attempted."
    )
    df_out.loc[missing_source_mask, "RNA_Source_Review_Required"] = False

    # Case 2: RNA_Source_Post exists, but the accepted mapping is null.
    # This means blank RNA_Source_Mapped is intentional under the RNA source rules.
    accepted_null_mask = status_unmapped & review_false & (~source_blank) & mapped_blank

    df_out.loc[accepted_null_mask, "RNA_Source_Mapping_Status"] = (
        "Mapped: LLM prompt-rule accepted null"
    )
    df_out.loc[accepted_null_mask, "RNA_Source_Mapping_Method"] = (
        "LLM RNA source mapping prompt"
    )

    confidence_blank = (
        df_out.loc[accepted_null_mask, "RNA_Source_Mapping_Confidence"]
        .fillna("")
        .astype(str)
        .str.strip()
        .isin({"", "NA", "nan", "None"})
    )
    accepted_null_idx = df_out.loc[accepted_null_mask].index
    df_out.loc[accepted_null_idx[confidence_blank], "RNA_Source_Mapping_Confidence"] = "medium"

    df_out.loc[accepted_null_mask, "RNA_Source_Mapping_Reason"] = (
        "RNA source mapped to null according to RNA source mapping prompt; "
        "blank RNA_Source_Mapped is intentional and not review-required."
    )
    df_out.loc[accepted_null_mask, "RNA_Source_Review_Required"] = False

    # Case 3: stale unmapped status but a mapped value exists.
    mapped_present_mask = status_unmapped & review_false & (~source_blank) & (~mapped_blank)

    df_out.loc[mapped_present_mask, "RNA_Source_Mapping_Status"] = (
        "Mapped: accepted automated RNA source mapping"
    )
    df_out.loc[mapped_present_mask, "RNA_Source_Mapping_Method"] = (
        "LLM RNA source mapping prompt"
    )
    df_out.loc[mapped_present_mask, "RNA_Source_Review_Required"] = False

    confidence_blank = (
        df_out.loc[mapped_present_mask, "RNA_Source_Mapping_Confidence"]
        .fillna("")
        .astype(str)
        .str.strip()
        .isin({"", "NA", "nan", "None"})
    )
    mapped_present_idx = df_out.loc[mapped_present_mask].index
    df_out.loc[mapped_present_idx[confidence_blank], "RNA_Source_Mapping_Confidence"] = "medium"

    return df_out

def rebuild_rna_source_review_queue_after_automap(df: pd.DataFrame) -> pd.DataFrame:
    """Rebuild RNA source review queue after LLM prompt-rule mapping."""
    if "RNA_Source_Review_Required" not in df.columns:
        return pd.DataFrame()

    review_mask = (
        df["RNA_Source_Review_Required"]
        .astype("string")
        .fillna("")
        .str.strip()
        .str.upper()
        .isin({"TRUE", "1", "YES"})
    )

    cols = [
        "GSM_ID",
        "GSE_ID",
        "Seq_Type_Post",
        "RNA_Source_Pre",
        "RNA_Source_Post",
        "RNA_Source_Mapped",
        "RNA_Source_Mapping_Status",
        "RNA_Source_Mapping_Method",
        "RNA_Source_Mapping_Confidence",
        "RNA_Source_Mapping_Reason",
        "RNA_Source_Review_Required",
        "GSE_Info",
        "GSM_Info",
    ]
    cols = [c for c in cols if c in df.columns]

    return df.loc[review_mask, cols].copy()



def run_stage3_mapping(cfg, df_stage2: pd.DataFrame) -> pd.DataFrame:
    cfg.validate_env()

    required = {"GSM_ID", "GSE_ID", "Disease_Post", "Tissue_Post", "Pert_Type", "Pert_Post"}
    missing = required - set(df_stage2.columns)
    if missing:
        raise ValueError(f"Stage2 output missing required columns for Stage3: {sorted(missing)}")

    llm = make_llm_from_config(cfg)

    outdir = Path(cfg.outputs_dir)
    mapdir = Path(cfg.mapping_cache_dir)
    debugdir = Path(cfg.debug_dir)
    reviewdir = Path(cfg.review_dir)
    novel_dir = Path(cfg.novel_term_dir)

    for d in [outdir, mapdir, debugdir, reviewdir, novel_dir]:
        d.mkdir(parents=True, exist_ok=True)

    df = df_stage2.copy()

    for col in ["Disease_Pre", "Disease_Post", "Tissue_Pre", "Tissue_Post", "Pert_Pre", "Pert_Post"]:
        if col in df.columns:
            df[col] = df[col].map(strip_extract_infer_suffix)

    # Disease canonicalization is handled in Stage 2. Stage 3 only maps Disease_Post.

    ctd_df = load_ctd_kb(Path(cfg.ctd_csv))
    ctd_exact_lookup = build_ctd_exact_synonym_lookup(ctd_df)

    prior_disease = load_prior_disease_mapping(Path(cfg.prior_disease_mapping_xlsx))
    prior_tissue = load_prior_tissue_mapping(Path(cfg.prior_tissue_mapping_xlsx))
    prior_cp = load_prior_cp_mapping(Path(cfg.prior_cp_mapping_xlsx))

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
    tfidf_matrix = vectorizer.fit_transform(ctd_df["search_text"].tolist())

    # -------------------------
    # Disease mapping
    # -------------------------
    disease_vals = df["Disease_Post"].map(_s).tolist()
    disease_uniq = sorted({v for v in disease_vals if v not in {"NA", "Unknown"}})
    disease_cache_fp = mapdir / "DiseasePost_to_CTD.json"
    disease_cache = _load_json(disease_cache_fp)

    need_terms: List[str] = []
    disease_prior_semantic_terms: List[str] = []

    # Step 1: exact/tolerant reviewed disease mapping-file reuse.
    for t in disease_uniq:
        prior_rec = lookup_prior_record(t, prior_disease, domain="disease")

        if prior_rec is not None:
            # Reviewed disease_mappings.xlsx overrides stale cache and CTD/LLM output.
            disease_cache[t] = prior_rec
            continue

        if _no_disease_state(t):
            disease_cache[t] = _no_disease_record(t)
            continue

        if _is_composite_disease_term(t):
            disease_cache[t] = _composite_disease_record(t)
            continue

        # Do not trust stale cache yet. First check whether this is a semantic
        # variant of a reviewed disease_mappings.xlsx row.
        disease_prior_semantic_terms.append(t)

    # Step 2: LLM semantic reuse against reviewed disease_mappings.xlsx rows.
    disease_candidate_records = _make_prior_candidate_records(
        Path(cfg.prior_disease_mapping_xlsx),
        domain="Disease",
    )

    disease_semantic_hits, disease_semantic_decision_df = resolve_terms_by_prior_mapping_llm(
        cfg=cfg,
        llm=llm,
        terms=disease_prior_semantic_terms,
        candidate_records=disease_candidate_records,
        domain="Disease",
        batch_size=min(int(getattr(cfg, "term_batch_size", 20)), 20),
    )

    disease_semantic_fp = reviewdir / f"{cfg.run_version}_stage3_disease_prior_mapping_semantic_reuse_decisions.xlsx"
    disease_semantic_decision_df.to_excel(disease_semantic_fp, index=False)
    print("[SAVED] Stage3 disease prior semantic reuse decisions:", disease_semantic_fp)

    # Step 3: CTD/MEDIC exact DiseaseName/Synonym reference lookup.
    for t in disease_prior_semantic_terms:
        if t in disease_semantic_hits:
            disease_cache[t] = disease_semantic_hits[t]
            continue

        ctd_ref_rec = lookup_ctd_reference_record(t, ctd_exact_lookup)
        if ctd_ref_rec is not None:
            disease_cache[t] = ctd_ref_rec
            continue

        if t in disease_cache:
            continue

        # Step 4: true new disease term; send to CTD candidate retrieval + LLM.
        need_terms.append(t)

    _save_json(disease_cache_fp, disease_cache)
    print(f"[Stage3 CTD] Unique={len(disease_uniq)} Need={len(need_terms)}")

    novel_disease_df = _build_novel_term_df(need_terms, "Disease")

    if need_terms:
        extra_disease_guidance = ""
        try:
            p = Path(cfg.disease_mapping_prompt_docx)
            if p.exists():
                extra_disease_guidance = "\n\n" + read_prompt_file(p)
        except Exception:
            pass

        new_results: Dict[str, Dict[str, Any]] = {}

        for bi, chunk_terms in enumerate(_chunk(need_terms, min(cfg.term_batch_size, 20))):
            cand_payload = {
                t: ctd_candidates_for_term(t, ctd_df, vectorizer, tfidf_matrix, top_k=8)
                for t in chunk_terms
            }
            payload = {"terms": chunk_terms, "candidates": cand_payload}
            messages = [
                {"role": "system", "content": CTD_LLM_SYSTEM + extra_disease_guidance},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]

            check_messages_token_budget(
                messages,
                budget=TokenBudget.from_config(cfg),
                context_label=f"Stage3 disease CTD mapping batch={bi}",
                action=str(getattr(cfg, "llm_token_budget_action", "raise")),
            )

            txt = llm.chat(messages, temperature=0.0)
            out = safe_json_loads_with_repair(
                txt,
                debug_dir=str(debugdir),
                debug_tag=f"CTD_{bi}",
                llm_chat_fn=lambda msgs, temperature=0.0: llm.chat(msgs, temperature=temperature),
            )

            got = set()

            for r in out.get("mappings", []):
                raw = _s(r.get("raw"))
                mapped_name = _s(r.get("DiseaseName"))
                mapped_id = _s(r.get("DiseaseID"))
                expl = _s(r.get("explanation"))
                got.add(raw)

                if raw in {"NA", ""}:
                    continue

                if mapped_name in {"NA", "Unknown"} or mapped_id in {"NA", "Unknown"}:
                    new_results[raw] = {
                        "Disease_Mapped": "",
                        "DiseaseID": "",
                        "AltDiseaseIDs": "",
                        "Definition": "",
                        "ParentIDs": "",
                        "TreeNumbers": "",
                        "ParentTreeNumbers": "",
                        "Synonyms": "",
                        "SlimMappings": "",
                        "Broad_Disease_Category": "",
                        "Disease_Map_Explanation": expl if expl not in {"NA", "Unknown"} else "",
                        "Disease_Review_Required": True,
                        "Disease_Map_Method": "llm_no_match",
                        "Final_Diease_Term_Flag": "NEW_TERM_REVIEW",
                        "Comment1": "LLM no good disease mapping found.",
                        "Comment2": "",
                        "Match_MESHCode": "",
                    }
                    continue

                hit = ctd_df[
                    (ctd_df["DiseaseName"].astype(str) == mapped_name)
                    & (ctd_df["DiseaseID"].astype(str) == mapped_id)
                ]

                if hit.empty:
                    new_results[raw] = {
                        "Disease_Mapped": "",
                        "DiseaseID": "",
                        "AltDiseaseIDs": "",
                        "Definition": "",
                        "ParentIDs": "",
                        "TreeNumbers": "",
                        "ParentTreeNumbers": "",
                        "Synonyms": "",
                        "SlimMappings": "",
                        "Broad_Disease_Category": "",
                        "Disease_Map_Explanation": "LLM selected CTD term not found in KB.",
                        "Disease_Review_Required": True,
                        "Disease_Map_Method": "llm_invalid",
                        "Final_Diease_Term_Flag": "NEW_TERM_REVIEW",
                        "Comment1": "LLM invalid CTD selection.",
                        "Comment2": "",
                        "Match_MESHCode": "",
                    }
                    continue

                row0 = hit.iloc[0]
                new_results[raw] = {
                    "Disease_Mapped": _blank(row0.get("DiseaseName")),
                    "DiseaseID": _blank(row0.get("DiseaseID")),
                    "AltDiseaseIDs": _blank(row0.get("AltDiseaseIDs")),
                    "Definition": _blank(row0.get("Definition")),
                    "ParentIDs": _blank(row0.get("ParentIDs")),
                    "TreeNumbers": _blank(row0.get("TreeNumbers")),
                    "ParentTreeNumbers": _blank(row0.get("ParentTreeNumbers")),
                    "Synonyms": _blank(row0.get("Synonyms")),
                    "SlimMappings": _blank(row0.get("SlimMappings")),
                    "Broad_Disease_Category": _broad_category_or_na(
                        infer_broad_disease_category_from_slim_mappings(row0.get("SlimMappings"))
                    ),
                    "Disease_Map_Explanation": expl if expl not in {"NA", "Unknown"} else "",
                    "Disease_Review_Required": True,
                    "Disease_Map_Method": "llm_ctd",
                    "Final_Diease_Term_Flag": "NEW_TERM_LLM",
                    "Comment1": "Mapped by LLM after prior mapping miss.",
                    "Comment2": "",
                    "Match_MESHCode": "",
                }

            missing_terms = set(chunk_terms) - got
            for m in missing_terms:
                new_results[m] = {
                    "Disease_Mapped": "",
                    "DiseaseID": "",
                    "AltDiseaseIDs": "",
                    "Definition": "",
                    "ParentIDs": "",
                    "TreeNumbers": "",
                    "ParentTreeNumbers": "",
                    "Synonyms": "",
                    "SlimMappings": "",
                    "Broad_Disease_Category": "",
                    "Disease_Map_Explanation": "No mapping returned.",
                    "Disease_Review_Required": True,
                    "Disease_Map_Method": "llm_missing",
                    "Final_Diease_Term_Flag": "NEW_TERM_REVIEW",
                    "Comment1": "No LLM mapping returned.",
                    "Comment2": "",
                    "Match_MESHCode": "",
                }

        for t, rec in new_results.items():
            prior_rec = lookup_prior_record(t, prior_disease, domain="disease")
            if prior_rec is not None:
                disease_cache[t] = prior_rec
            else:
                disease_cache[t] = rec

        _save_json(disease_cache_fp, disease_cache)

    disease_records = [disease_cache.get(v, {}) for v in disease_vals]
    disease_cols = [
        "Disease_Mapped",
        "DiseaseID",
        "AltDiseaseIDs",
        "Definition",
        "ParentIDs",
        "TreeNumbers",
        "ParentTreeNumbers",
        "Synonyms",
        "SlimMappings",
        "Broad_Disease_Category",
        "Disease_Map_Explanation",
        "Disease_Review_Required",
        "Disease_Map_Method",
        "Final_Diease_Term_Flag",
        "Comment1",
        "Comment2",
        "Match_MESHCode",
    ]

    for c in disease_cols:
        default_val = False if c == "Disease_Review_Required" else ""
        df[c] = [rec.get(c, default_val) for rec in disease_records]


    # Final disease mapping safeguard:
    # prior mapping files must not leave invalid free-text disease labels
    # in Disease_Mapped when a CTD/MEDIC exact/synonym rescue is available.
    df = repair_invalid_disease_mappings_against_ctd(
        df=df,
        ctd_df=ctd_df,
        ctd_exact_lookup=ctd_exact_lookup,
    )

    # -------------------------
    # Tissue mapping
    # -------------------------
    tissue_vals = df["Tissue_Post"].map(_s).tolist()
    tissue_uniq = sorted({v for v in tissue_vals if v not in {"NA", "Unknown"}})
    tissue_cache_fp = mapdir / "TissuePost_to_Mapped.json"
    tissue_cache = _load_json(tissue_cache_fp)

    tissue_need: List[str] = []
    tissue_prior_semantic_terms: List[str] = []

    for t in tissue_uniq:
        prior_rec = lookup_prior_record(t, prior_tissue, domain="tissue")

        if prior_rec is not None:
            tissue_cache[t] = prior_rec
            continue

        # Do not trust stale cache until semantic reuse has had a chance.
        tissue_prior_semantic_terms.append(t)

    tissue_candidate_records = _make_prior_candidate_records(
        Path(cfg.prior_tissue_mapping_xlsx),
        domain="Tissue",
    )

    tissue_semantic_hits, tissue_semantic_decision_df = resolve_terms_by_prior_mapping_llm(
        cfg=cfg,
        llm=llm,
        terms=tissue_prior_semantic_terms,
        candidate_records=tissue_candidate_records,
        domain="Tissue",
        batch_size=min(int(getattr(cfg, "term_batch_size", 20)), 20),
    )

    tissue_semantic_fp = reviewdir / f"{cfg.run_version}_stage3_tissue_prior_mapping_semantic_reuse_decisions.xlsx"
    tissue_semantic_decision_df.to_excel(tissue_semantic_fp, index=False)
    print("[SAVED] Stage3 tissue prior semantic reuse decisions:", tissue_semantic_fp)

    for t in tissue_prior_semantic_terms:
        if t in tissue_semantic_hits:
            tissue_cache[t] = tissue_semantic_hits[t]
            continue

        if t in tissue_cache:
            continue

        tissue_need.append(t)

    _save_json(tissue_cache_fp, tissue_cache)
    print(f"[Stage3 Tissue] Unique={len(tissue_uniq)} Need={len(tissue_need)}")

    novel_tissue_df = _build_novel_term_df(tissue_need, "Tissue")

    if tissue_need:
        extra_tissue_guidance = ""
        try:
            p = Path(cfg.tissue_mapping_prompt_docx)
            if p.exists():
                extra_tissue_guidance = "\n\n" + read_prompt_file(p)
        except Exception:
            pass

        for bi, chunk_terms in enumerate(_chunk(tissue_need, min(cfg.term_batch_size, 20))):
            payload = {"terms": chunk_terms}
            messages = [
                {"role": "system", "content": TISSUE_LLM_SYSTEM + extra_tissue_guidance},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]
            check_messages_token_budget(
                messages,
                budget=TokenBudget.from_config(cfg),
                context_label=f"Stage3 tissue mapping batch={bi}",
                action=str(getattr(cfg, "llm_token_budget_action", "raise")),
            )

            txt = llm.chat(messages, temperature=0.0)
            out = safe_json_loads_with_repair(
                txt,
                debug_dir=str(debugdir),
                debug_tag=f"TISSUE_{bi}",
                llm_chat_fn=lambda msgs, temperature=0.0: llm.chat(msgs, temperature=temperature),
            )

            got = set()

            for r in out.get("mappings", []):
                raw = _s(r.get("raw"))
                mapped = _s(r.get("mapped"))
                expl = _s(r.get("explanation"))
                got.add(raw)

                if raw in {"NA", ""}:
                    continue

                tissue_cache[raw] = {
                    "Tissue_Mapped": _mapped_na(mapped),
                    "Tissue_Map_Explanation": "" if expl == "NA" else expl,
                    "Tissue_Map_Method": "llm_tissue",
                }

            missing_terms = set(chunk_terms) - got
            for m in missing_terms:
                tissue_cache[m] = {
                    "Tissue_Mapped": "NA",
                    "Tissue_Map_Explanation": "No mapping returned.",
                    "Tissue_Map_Method": "llm_missing",
                }

        _save_json(tissue_cache_fp, tissue_cache)

    df["Tissue_Mapped"] = [tissue_cache.get(v, {}).get("Tissue_Mapped", "") for v in tissue_vals]
    df["Tissue_Map_Explanation"] = [
        tissue_cache.get(v, {}).get("Tissue_Map_Explanation", "") for v in tissue_vals
    ]
    df["Tissue_Map_Method"] = [tissue_cache.get(v, {}).get("Tissue_Map_Method", "") for v in tissue_vals]

    # -------------------------
    # Pert / PubChem mapping
    # -------------------------
    pert_vals = df["Pert_Post"].map(_s).tolist()
    pert_uniq = sorted({v for v in pert_vals if v not in {"NA", "Unknown"}})
    cp_cache_fp = mapdir / "PertPost_to_PubChem.json"
    cp_cache = _load_json(cp_cache_fp)

    cp_need: List[str] = []
    cp_prior_semantic_terms: List[str] = []

    for t in pert_uniq:
        rows = df.loc[df["Pert_Post"] == t, "Pert_Type"]
        is_cp = not rows.empty and _s(rows.iloc[0]) == "CP"

        if not is_cp:
            continue

        prior_rec = lookup_prior_record(t, prior_cp, domain="cp")

        if prior_rec is not None:
            cp_cache[t] = prior_rec
            continue

        # Do not trust stale cache until semantic reuse has had a chance.
        cp_prior_semantic_terms.append(t)

    cp_candidate_records = _make_prior_candidate_records(
        Path(cfg.prior_cp_mapping_xlsx),
        domain="CP",
    )

    cp_semantic_hits, cp_semantic_decision_df = resolve_terms_by_prior_mapping_llm(
        cfg=cfg,
        llm=llm,
        terms=cp_prior_semantic_terms,
        candidate_records=cp_candidate_records,
        domain="CP",
        batch_size=min(int(getattr(cfg, "term_batch_size", 20)), 20),
    )

    cp_semantic_fp = reviewdir / f"{cfg.run_version}_stage3_cp_prior_mapping_semantic_reuse_decisions.xlsx"
    cp_semantic_decision_df.to_excel(cp_semantic_fp, index=False)
    print("[SAVED] Stage3 CP prior semantic reuse decisions:", cp_semantic_fp)

    for t in cp_prior_semantic_terms:
        if t in cp_semantic_hits:
            cp_cache[t] = cp_semantic_hits[t]
            continue

        if t in cp_cache and _cp_cache_is_reusable(cp_cache.get(t)):
            continue

        cp_need.append(t)

    _save_json(cp_cache_fp, cp_cache)

    unique_cp_terms = len(
        [
            t for t in pert_uniq
            if not df.loc[df["Pert_Post"] == t, "Pert_Type"].empty
            and _s(df.loc[df["Pert_Post"] == t, "Pert_Type"].iloc[0]) == "CP"
        ]
    )
    print(f"[Stage3 Pert/CP] Unique_CP_terms={unique_cp_terms} Need={len(cp_need)}")

    novel_pert_df = _build_novel_term_df(cp_need, "Pert")

    if cp_need:
        # Direct PubChem matching only. Do not ask the LLM to remap compound names.
        # Standardized Pert_Post is used as the authoritative query term; PubChem
        # matches are accepted only when title/synonym verification succeeds.
        for raw in cp_need:
            cp_cache[raw] = resolve_cp_term_with_pubchem(
                raw,
                timeout=int(cfg.pubchem_timeout_sec),
            )

        _save_json(cp_cache_fp, cp_cache)

    def apply_cp_row(pert_type: str, pert_post: str) -> Dict[str, str]:
        if _s(pert_type) != "CP":
            return {
                "CP_PubChem_Name": "",
                "CP_CID": "",
                "CP_CanonicalSMILES": "",
                "CP_PubChemURL": "",
                "CP_MatchType": "",
                "CP_Map_Explanation": "",
                "CP_Map_Method": "",
                "CP_Query_Status": "",
                "CP_Query_Error": "",
                "CP_Query_Attempted_Term": "",
            }

        rec = cp_cache.get(_s(pert_post), {})
        return {
            "CP_PubChem_Name": rec.get("CP_PubChem_Name", ""),
            "CP_CID": rec.get("CP_CID", ""),
            "CP_CanonicalSMILES": rec.get("CP_CanonicalSMILES", ""),
            "CP_PubChemURL": rec.get("CP_PubChemURL", ""),
            "CP_MatchType": rec.get("CP_MatchType", ""),
            "CP_Map_Explanation": rec.get("CP_Map_Explanation", ""),
            "CP_Map_Method": rec.get("CP_Map_Method", ""),
            "CP_Query_Status": rec.get("CP_Query_Status", rec.get("CP_Map_Method", "")),
            "CP_Query_Error": rec.get("CP_Query_Error", ""),
            "CP_Query_Attempted_Term": rec.get("CP_Query_Attempted_Term", _s(pert_post)),
        }

    df_cp = pd.DataFrame(
        [apply_cp_row(pt, pp) for pt, pp in zip(df["Pert_Type"].tolist(), df["Pert_Post"].tolist())]
    )
    df = pd.concat([df, df_cp], axis=1)

    # -------------------------
    # New-term flags for manual review
    # -------------------------
    df["Disease_New_Term_Flag"] = df["Disease_Post"].map(
        lambda x: (
            lookup_prior_record(x, prior_disease, domain="disease") is None
            and _s(x) not in {"NA", "Unknown"}
            and not _no_disease_state(x)
            and x not in disease_semantic_hits
        )
    )

    df["Tissue_New_Term_Flag"] = df["Tissue_Post"].map(
        lambda x: (
            lookup_prior_record(x, prior_tissue, domain="tissue") is None
            and _s(x) not in {"NA", "Unknown"}
            and x not in tissue_semantic_hits
        )
    )

    df["Pert_New_Term_Flag"] = df.apply(
        lambda r: (
            lookup_prior_record(r["Pert_Post"], prior_cp, domain="cp") is None
            and r["Pert_Post"] not in cp_semantic_hits
            if _s(r["Pert_Type"]) == "CP" and _s(r["Pert_Post"]) not in {"NA", "Unknown"}
            else False
        ),
        axis=1,
    )

    # -------------------------
    # Save novel/manual-review term workbooks
    # -------------------------
    novel_fp = save_stage3_novel_term_workbooks(
        cfg=cfg,
        novel_dir=novel_dir,
        novel_disease_df=novel_disease_df,
        novel_tissue_df=novel_tissue_df,
        novel_pert_df=novel_pert_df,
        disease_cache=disease_cache,
        tissue_cache=tissue_cache,
        cp_cache=cp_cache,
    )

    # -------------------------
    # Review / correct
    # -------------------------
    df, review_df = _review_and_correct_stage3(df, prior_tissue, prior_cp)

    # -------------------------
    # Backfill missing CP_CanonicalSMILES from existing CP_CID or CP_PubChemURL
    # and normalize CP_CID before final outputs are assembled.
    # -------------------------
    df = backfill_cp_smiles_from_existing_ids(df, timeout=int(cfg.pubchem_timeout_sec))
    df = add_cp_mapping_status(df)

    # -------------------------
    # Final perturbation dose/duration release mapping
    # -------------------------
    if "Pert_Dose_Post" not in df.columns:
        df["Pert_Dose_Post"] = "NA"

    if "Pert_Duration_Post" not in df.columns:
        df["Pert_Duration_Post"] = "NA"

    df["Mapped_Pert_Dose"] = df["Pert_Dose_Post"].map(map_pert_dose_for_release)
    df["Mapped_Pert_Duration"] = df["Pert_Duration_Post"].map(map_pert_duration_for_release)

    dose_na = int(df["Mapped_Pert_Dose"].eq("NA").sum())
    dose_others = int(df["Mapped_Pert_Dose"].eq("Others").sum())
    dose_approved = int((~df["Mapped_Pert_Dose"].isin(["NA", "Others"])).sum())

    duration_na = int(df["Mapped_Pert_Duration"].eq("NA").sum())
    duration_others = int(df["Mapped_Pert_Duration"].eq("Others").sum())
    duration_approved = int((~df["Mapped_Pert_Duration"].isin(["NA", "Others"])).sum())

    print(
        "[Stage3 Pert dose] "
        f"rows={len(df)}; "
        f"Mapped_Pert_Dose: approved_single={dose_approved}, NA={dose_na}, Others={dose_others}",
        flush=True,
    )

    print(
        "[Stage3 Pert duration] "
        f"rows={len(df)}; "
        f"Mapped_Pert_Duration: approved_single={duration_approved}, NA={duration_na}, Others={duration_others}",
        flush=True,
    )

    # -------------------------
    # RNA_Source mapping for automated Mode A release.
    # This is non-blocking: unmapped terms are flagged and exported for review,
    # but final files are still produced.
    # -------------------------
    if "RNA_Source_Post" not in df.columns and "RNA_Source_Pre" in df.columns:
        df["RNA_Source_Post"] = df["RNA_Source_Pre"]
    df, rna_source_review_df = apply_mode_a_rna_source_mapping(
        df,
        workdir=cfg.workdir,
        source_col="RNA_Source_Post",
    )

    # Cell-line reference lookup before LLM RNA_Source automapping.
    cell_line_ref_path = Path(
        getattr(
            cfg,
            "cell_line_reference_csv",
            Path(cfg.workdir) / "mappings" / "rna_source" / "cell_line_model_reference.csv",
        )
    )

    cell_line_lookup = load_cell_line_reference_lookup(cell_line_ref_path)

    df, rna_source_cell_line_df = apply_cell_line_reference_to_rna_source(
        df,
        cell_line_lookup=cell_line_lookup,
        source_col="RNA_Source_Post",
    )

    rna_source_cell_line_fp = reviewdir / f"{cfg.run_version}_stage3_rna_source_cell_line_reference_decisions.xlsx"
    rna_source_cell_line_df.to_excel(rna_source_cell_line_fp, index=False)
    print("[SAVED] Stage3 RNA source cell-line reference decisions:", rna_source_cell_line_fp)

    # For new RNA_Source terms not found in the reviewed mapping file or cell-line reference,
    # apply the same RNA source mapping prompt/rules at unique-term level.
    df, rna_source_auto_df = map_unresolved_rna_source_terms_with_prompt(
        cfg=cfg,
        llm=llm,
        df=df,
        source_col="RNA_Source_Post",
        batch_size=min(int(getattr(cfg, "term_batch_size", 20)), 20),
    )

    df = reconcile_rna_source_status_after_automap(df)

    # Rebuild review queue after prompt-rule mapping.
    rna_source_review_df = rebuild_rna_source_review_queue_after_automap(df)

    rna_source_auto_fp = reviewdir / f"{cfg.run_version}_stage3_rna_source_auto_mapping_decisions.xlsx"
    rna_source_review_fp = reviewdir / f"{cfg.run_version}_stage3_rna_source_review_queue.xlsx"

    rna_source_auto_df.to_excel(rna_source_auto_fp, index=False)
    rna_source_review_df.to_excel(rna_source_review_fp, index=False)

    print("[SAVED] Stage3 RNA source LLM auto mapping decisions:", rna_source_auto_fp)
    print("[SAVED] Stage3 RNA source review queue:", rna_source_review_fp)

    # -------------------------
    # Backfill Broad_Disease_Category using prior disease mapping
    # This is needed when Disease_Mapped was generated by LLM CTD mapping
    # but the broad disease category exists in the curated disease mapping file.
    # -------------------------
    disease_category_lookup = {}

    for rec in prior_disease.values():
        mapped = normalize_lookup_term(rec.get("Disease_Mapped", ""))
        category = _blank(rec.get("Broad_Disease_Category", ""))

        if mapped and mapped not in {"na", "unknown"} and category:
            disease_category_lookup[mapped] = category

    if "Broad_Disease_Category" in df.columns and "Disease_Mapped" in df.columns:
        for idx in df.index:
            current_cat = _blank(df.at[idx, "Broad_Disease_Category"])
            mapped_key = normalize_lookup_term(df.at[idx, "Disease_Mapped"])

            if not current_cat and mapped_key in disease_category_lookup:
                df.at[idx, "Broad_Disease_Category"] = disease_category_lookup[mapped_key]

    # Cancer-like disease fallback for broad category only.
    # This does not fix invalid Disease_Mapped terms; Stage 4 still checks CTD validity.
    if {"Broad_Disease_Category", "Disease_Post", "Disease_Mapped"}.issubset(df.columns):
        broad_blank = df["Broad_Disease_Category"].map(_is_release_blank)

        inferred_broad = df.apply(
            lambda r: _infer_broad_category_from_disease_text(
                r.get("Disease_Post", ""),
                r.get("Disease_Mapped", ""),
            ),
            axis=1,
        )

        df.loc[broad_blank & inferred_broad.eq("Oncology"), "Broad_Disease_Category"] = "Oncology"

    if "Broad_Disease_Category" in df.columns:
        df["Broad_Disease_Category"] = df["Broad_Disease_Category"].map(_broad_category_or_na)

    # -------------------------
    # Final safeguard: GSM_Pert_Post must mirror GSM_Pert_Pre
    # Allowed final values: Control / Perturbed / NA
    # -------------------------
    def _normalize_gsm_pert_from_pre(x):
        x = str(x).strip().lower()
        if x in {"control", "ctrl", "no", "false", "0"}:
            return "Control"
        if x in {"perturbed", "treated", "yes", "true", "1"}:
            return "Perturbed"
        if x in {"na", "unknown", ""}:
            return "NA"
        return "NA"

    if "GSM_Pert_Pre" in df.columns:
        df["GSM_Pert_Post"] = df["GSM_Pert_Pre"].apply(_normalize_gsm_pert_from_pre)

    # -------------------------
    # Final columns
    # -------------------------
    final_cols = [
        "GSM_ID",
        "GSE_ID",
        "Seq_Type_Pre",
        "Seq_Type_Post",
        "Organism_Pre",
        "Organism_Post",
        "Strain_Pre",
        "Strain_Post",
        "Genotype_Pre",
        "Genotype_Post",
        "Cell_Line_Post",
        "RNA_Library_Pre",
        "RNA_Library_Post",
        "RNA_Source_Pre",
        "RNA_Source_Post",
        "RNA_Source_Mapped",
        "RNA_Source",
        "RNA_Source_Mapping_Status",
        "RNA_Source_Mapping_Method",
        "RNA_Source_Mapping_Confidence",
        "RNA_Source_Mapping_Reason",
        "RNA_Source_Review_Required",
        "Tissue_Pre",
        "Tissue_Post",
        "Tissue_Mapped",
        "Tissue_Map_Explanation",
        "Tissue_Map_Method",
        "Experimental_Setting_Pre",
        "Experimental_Setting_Post",
        "Model_Type_Pre",
        "Model_Type_Post",
        "Disease_Pre",
        "Disease_Post",
        "Disease_Mapped",
        "DiseaseID",
        "AltDiseaseIDs",
        "Definition",
        "ParentIDs",
        "TreeNumbers",
        "ParentTreeNumbers",
        "Synonyms",
        "SlimMappings",
        "Final_Diease_Term_Flag",
        "Comment1",
        "Comment2",
        "Match_MESHCode",
        "Broad_Disease_Category",
        "Disease_Map_Explanation",
        "Disease_Review_Required",
        "Disease_Map_Method",
        "Disease_New_Term_Flag",
        "Tissue_New_Term_Flag",
        "Pert_New_Term_Flag",
        "GSE_Pert_Pre",
        "GSE_Pert_Post",
        "GSM_Pert_Pre",
        "GSM_Pert_Post",
        "Pert_Pre",
        "Pert_Post",
        "Pert_Type",
        "CP_Mapping_Status",
        "CP_PubChem_Name",
        "CP_CID",
        "CP_CanonicalSMILES",
        "CP_PubChemURL",
        "CP_MatchType",
        "CP_Map_Explanation",
        "CP_Map_Method",
        "CP_Query_Status",
        "CP_Query_Error",
        "CP_Query_Attempted_Term",
        "Pert_Dose_Pre",
        "Pert_Dose_Post",
        "Mapped_Pert_Dose",
        "Pert_Freq_Pre",
        "Pert_Freq_Post",
        "Pert_Duration_Pre",
        "Pert_Duration_Post",
        "Mapped_Pert_Duration",
        "Route_Admin_Pre",
        "Route_Admin_Post",
        "SampleType",
        "Specimen_Type_Pre",
        "Specimen_Type_Post",
        "Race_Pre",
        "Race_Post",
        "Ethnicity_Pre",
        "Ethnicity_Post",
        "Age_Pre",
        "Age_Post",
        "Age_Group_Post",
        "Sex_Pre",
        "Sex_Inferred_from_Tissue",
        "Sex_Post",
        "Timepoint_Pre",
        "Timepoint_Post",
        "Outcome_Pre",
        "Outcome_Post",
        "Global_QC_Status",
        "Review_Required",
        "Review_Level",
        "Review_Reason",
        "Release_Action",
        "Correction_Source",
        "Correction_Confidence",
        "Correction_Reason",
        "GSE_Info",
        "GSM_Info",
    ]

    blank_cols = {
        "Tissue_Mapped",
        "Tissue_Map_Explanation",
        "Tissue_Map_Method",
        "Disease_Mapped",
        "DiseaseID",
        "AltDiseaseIDs",
        "Definition",
        "ParentIDs",
        "TreeNumbers",
        "ParentTreeNumbers",
        "Synonyms",
        "SlimMappings",
        "Final_Diease_Term_Flag",
        "Comment1",
        "Comment2",
        "Match_MESHCode",
        "Broad_Disease_Category",
        "Disease_Map_Explanation",
        "Disease_Map_Method",
        "CP_PubChem_Name",
        "CP_CID",
        "CP_CanonicalSMILES",
        "CP_PubChemURL",
        "CP_MatchType",
        "CP_Map_Explanation",
        "CP_Map_Method",
        "CP_Query_Status",
        "CP_Query_Error",
        "CP_Query_Attempted_Term",
        "RNA_Source_Mapped",
        "RNA_Source",
        "RNA_Source_Mapping_Status",
        "RNA_Source_Mapping_Method",
        "RNA_Source_Mapping_Confidence",
        "RNA_Source_Mapping_Reason",
        "GSE_Info",
        "GSM_Info",
    }

    flag_cols = {
        "Disease_Review_Required",
        "Disease_New_Term_Flag",
        "Tissue_New_Term_Flag",
        "Pert_New_Term_Flag",
        "RNA_Source_Review_Required",
        "Review_Required",
    }

    mapped_na_cols = {
    "Tissue_Mapped",
    "Disease_Mapped",
    "DiseaseID",
    "AltDiseaseIDs",
    "Broad_Disease_Category",
    "CP_PubChem_Name",
    "CP_CID",
    "CP_CanonicalSMILES",
    "CP_PubChemURL",
    "CP_MatchType",
    "Mapped_Pert_Dose",
    "Mapped_Pert_Duration",
    }

    for c in final_cols:
        if c not in df.columns:
            if c in flag_cols:
                df[c] = False
            elif c in mapped_na_cols:
                df[c] = "NA"
            elif c in blank_cols:
                df[c] = ""
            else:
                df[c] = "NA"

    for c in mapped_na_cols:
        if c in df.columns:
            df[c] = df[c].map(_mapped_na)

    df_final = df.loc[:, final_cols].copy()
    df_final = add_mode_a_final_qc_flags(df_final)
    df_final = add_release_display_columns(df_final)
    df_final = refine_mode_a_public_review_flags(df_final)

    # Stage 3.5 disease missingness audit.
    df_final, missing_disease_review_df = add_missing_disease_within_mixed_gse_flags(df_final)

    # Stage 4 deterministic release QA:
    # - closed-vocabulary validation for Disease/Tissue/Broad Disease Category
    # - explicit NA normalization for reviewed-but-unmappable mapped fields
    # - global and within-GSE consistency checks for key release fields
    stage4_qa_xlsx = ""

    if bool(getattr(cfg, "stage4_release_mapping_qa_enabled", True)):
        df_final, stage4_qa_xlsx = validate_stage3_release_qa(cfg, df_final)
    else:
        df_final["Mapping_QA_Status"] = "NOT_RUN"
        df_final["Mapping_QA_Issue"] = ""
        df_final["Release_Ready"] = "True"


    # ============================================================
    # Filtered mapped release file
    # ============================================================

    release_cols = [
        "GSM_ID",
        "GSE_ID",
        "Seq_Type_Pre",	
        "Seq_Type_Post",	
        "Organism_Pre",
        "Organism_Post",
        "RNA_Library_Pre",
        "RNA_Library_Post",
        "RNA_Source_Pre",
        "RNA_Source_Post",
        "RNA_Source_Mapped",
        "RNA_Source_Review_Required",
        "Experimental_Setting_Pre",
        "Experimental_Setting_Post",
        "GSE_Pert_Pre",
        "GSE_Pert_Post",
        "GSM_Pert_Pre",
        "GSM_Pert_Post",
        "Disease_Pre",
        "Disease_Post",
        "Disease_Mapped",
        "DiseaseID",
        "AltDiseaseIDs",
        "Definition",
        "ParentIDs",
        "TreeNumbers",
        "ParentTreeNumbers",
        "Synonyms",
        "SlimMappings",
        "Broad_Disease_Category",
        "Tissue_Pre",
        "Tissue_Post",
        "Tissue_Mapped",
        "Age_Pre",
        "Age_Post",
        "Age_Group_Post",
        "Sex_Pre",
        "Sex_Inferred_from_Tissue",
        "Sex_Post",
        "Global_QC_Status",
        "Review_Required",
        "Review_Level",
        "Review_Reason",
        "Release_Action",
        "Mapping_QA_Status",
        "Mapping_QA_Issue",
        "Release_Ready",
        "GSE_Info",
        "GSM_Info",
    ]

    for c in release_cols:
        if c not in df_final.columns:
            df_final[c] = ""

    df_release = df_final.loc[:, release_cols].copy()
    df_release = df_release.rename(columns={"RNA_Source_Mapped": "RNA_Source"})



   # ============================================================
    # Final simplified release file with renamed columns
    # ============================================================

    simple_release_cols = [
        "GSM_ID",
        "GSE_ID",
        "Seq_Type_Post",
        "Organism_Post",
        "RNA_Library_Post",
        "RNA_Source_Mapped",
        "Experimental_Setting_Post",
        "GSE_Pert_Post",
        "GSM_Pert_Post",
        "Disease_Mapped",
        "DiseaseID",	
        "AltDiseaseIDs",
        "Broad_Disease_Category",
        "Tissue_Mapped",
        "Age_Post",
        "Age_Group_Post",
        "Sex_Post",
        #"Global_QC_Status",
        #"Review_Required",
        #"Review_Level",
        #"Review_Reason",
        #"Release_Action",
        #"Mapping_QA_Status",
        #"Mapping_QA_Issue",
        #"Release_Ready",
        "GSE_Info",
        "GSM_Info",
    ]

    for c in simple_release_cols:
        if c not in df_final.columns:
            df_final[c] = ""

    df_simple_release = df_final.loc[:, simple_release_cols].copy()

    # Public disease-release filter:
    # Keep only high-confidence disease rows in:
    # - stage3_mapped_filtered.xlsx
    # - stage3_final_release.xlsx
    # The full stage3_mapped.xlsx remains complete for audit/provenance.
    disease_release_keep_mask = high_confidence_disease_release_mask(df_final)

    disease_release_excluded_df = build_disease_release_excluded_review_queue(
        df_final,
        disease_release_keep_mask,
    )

    df_release = df_release.loc[disease_release_keep_mask].copy()
    df_simple_release = df_simple_release.loc[disease_release_keep_mask].copy()

    df_simple_release = df_simple_release.rename(
        columns={
            "Seq_Type_Post": "Seq_Type",
            "Organism_Post": "Organism",
            "RNA_Library_Post": "RNA_Library",
            "RNA_Source_Mapped": "RNA_Source", 
            "Experimental_Setting_Post": "Exp_Setting",
            "GSE_Pert_Post": "GSE_Pert",
            "GSM_Pert_Post": "GSM_Pert",
            "Disease_Mapped": "Disease",
            "Tissue_Mapped": "Tissue",
            "Age_Post": "Age",
            "Age_Group_Post": "Age_Group",
            "Sex_Post": "Sex",
        }
    )

    # ============================================================
    # CP perturbation GSE release file with renamed columns
    # Keep all GSMs from any GSE containing at least one CP sample.
    # ============================================================

    cp_release_cols = [
        "GSM_ID",
        "GSE_ID",
        "Seq_Type_Post",
        "Organism_Post",
        "RNA_Library_Post",
        "RNA_Source_Mapped",
        "Experimental_Setting_Post",
        "GSE_Pert_Post",
        "GSM_Pert_Post",
        "Disease_Mapped",
        "DiseaseID",	
        "AltDiseaseIDs",
        "Broad_Disease_Category",
        "Tissue_Mapped",
        "Age_Post",
        "Age_Group_Post",
        "Sex_Post",
        "Pert_Post",
        "Pert_Type",
        "Mapped_Pert_Dose",
        "Mapped_Pert_Duration",
        #"CP_Mapping_Status",
        "CP_PubChem_Name",
        "CP_CID",
        "CP_CanonicalSMILES",
        "CP_PubChemURL",
        #"Global_QC_Status",
        #"Review_Required",
        #"Review_Level",
        #"Review_Reason",
        #"Mapping_QA_Status",
        #"Mapping_QA_Issue",
        #"Release_Ready",
        "GSE_Info",
        "GSM_Info",
    ]

    for c in cp_release_cols:
        if c not in df_final.columns:
            df_final[c] = ""

    df_cp_release, cp_excluded_df = build_mode_a_cp_release(df_final, cp_release_cols)

    df_cp_release = df_cp_release.rename(
        columns={
            "Seq_Type_Post": "Seq_Type",	
            "Organism_Post": "Organism",
            "RNA_Library_Post": "RNA_Library",
            "RNA_Source_Mapped": "RNA_Source",
            "Experimental_Setting_Post": "Exp_Setting",
            "GSE_Pert_Post": "GSE_Pert",
            "GSM_Pert_Post": "GSM_Pert",
            "Disease_Mapped": "Disease",
            "Tissue_Mapped": "Tissue",
            "Pert_Post": "Perturbation",
            "Age_Post": "Age",
            "Age_Group_Post": "Age_Group",
            "Sex_Post": "Sex",
        }
    )

    df_final = normalize_cid_columns(df_final)
    df_release = normalize_cid_columns(blank_release_na(df_release))
    df_simple_release = normalize_cid_columns(blank_release_na(df_simple_release))
    df_cp_release = normalize_cid_columns(blank_release_na(df_cp_release))

    # Final release-action safeguard after NA blanking and release dataframe construction.
    df_final = fill_release_action_for_pass_rows(df_final)
    df_release = fill_release_action_for_pass_rows(df_release)
    df_simple_release = fill_release_action_for_pass_rows(df_simple_release)
    df_cp_release = fill_release_action_for_pass_rows(df_cp_release)

    # Public release files are already filtered/release-facing.
    # Keep Release_Action explicit rather than blank.
    for _df in [df_simple_release, df_cp_release]:
        if "Release_Action" not in _df.columns:
            _df["Release_Action"] = "Include"
        else:
            _df["Release_Action"] = _df["Release_Action"].map(
                lambda x: "Include" if _is_release_blank(x) else str(x).strip()
            )

    # Blank selected NA-style fields in the full mapped output
    full_output_blank_cols = [
        "Cell_Line_Post",
    ]
    for c in full_output_blank_cols:
        if c in df_final.columns:
            df_final[c] = df_final[c].replace({"NA": "", "Unknown": ""})

    out_xlsx = outdir / f"{cfg.run_version}_stage3_mapped.xlsx"
    release_xlsx = outdir / f"{cfg.run_version}_stage3_mapped_filtered.xlsx"
    simple_release_xlsx = outdir / f"{cfg.run_version}_stage3_final_release.xlsx"
    cp_release_xlsx = outdir / f"{cfg.run_version}_stage3_cp_perturbation_release.xlsx"

    review_xlsx = reviewdir / f"{cfg.run_version}_stage3_post_mapping_review_corrections.xlsx"
    cp_excluded_xlsx = reviewdir / f"{cfg.run_version}_stage3_cp_release_excluded_review_queue.xlsx"
    disease_excluded_xlsx = reviewdir / f"{cfg.run_version}_stage3_disease_release_excluded_review_queue.xlsx"
    missing_disease_xlsx = reviewdir / f"{cfg.run_version}_stage3_missing_disease_within_mixed_gse_review_queue.xlsx"

    final_qc_xlsx = save_mode_a_stage3_5_report(
        cfg=cfg,
        review_dir=reviewdir,
        df_final=df_final,
        df_simple_release=df_simple_release,
        df_cp_release=df_cp_release,
        cp_excluded_df=cp_excluded_df,
    )

    df_stage3_mapped_out = build_stage3_mapped_output_view(df_final)

    # Public CP perturbation release column names.
    # Keep df_cp_release internally unchanged for Stage 3.5 QC/reporting,
    # but write public-facing Pert_Dose and Pert_Duration column names.
    df_cp_release_public = df_cp_release.rename(
        columns={
            "Mapped_Pert_Dose": "Pert_Dose",
            "Mapped_Pert_Duration": "Pert_Duration",
        }
    )

    df_stage3_mapped_out.to_excel(out_xlsx, index=False)
    df_release.to_excel(release_xlsx, index=False)
    df_simple_release.to_excel(simple_release_xlsx, index=False)
    df_cp_release_public.to_excel(cp_release_xlsx, index=False)

    review_df.to_excel(review_xlsx, index=False)
    cp_excluded_df.to_excel(cp_excluded_xlsx, index=False)
    disease_release_excluded_df.to_excel(disease_excluded_xlsx, index=False)
    missing_disease_review_df.to_excel(missing_disease_xlsx, index=False)

    print("[SAVED] Stage3 mapped Excel:", out_xlsx)
    print("[SAVED] Stage3 filtered release Excel:", release_xlsx)
    print("[SAVED] Stage3 final simplified release Excel:", simple_release_xlsx)
    print("[SAVED] Stage3 CP perturbation GSE release Excel:", cp_release_xlsx)

    print("[SAVED] Stage3 post-mapping review corrections:", review_xlsx)
    print("[SAVED] Stage3 CP release excluded review queue:", cp_excluded_xlsx)
    print("[SAVED] Stage3 disease release excluded review queue:", disease_excluded_xlsx)
    print("[SAVED] Stage3 missing disease within mixed-GSE review queue:", missing_disease_xlsx)
    print("[SAVED] Stage3.5 final QC report:", final_qc_xlsx)
    if stage4_qa_xlsx:
        print("[SAVED] Stage4 release mapping QA:", stage4_qa_xlsx)
    else:
        print("[SKIPPED] Stage4 release mapping QA disabled.")

    print("[SAVED] Stage3 novel terms:", novel_fp)

    return df_final
