from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Tuple

import pandas as pd


NA_LABEL = "NA"

ALLOWED_NON_DISEASE_LABELS = {
    "NA",
    "Normal",
    "Adjacent Normal",
    "No Disease Mentioned",
}

DEFAULT_BROAD_DISEASE_CATEGORIES = {
    "NA",
    "Normal",
    "Adjacent Normal",
    "No Disease Mentioned",
    "Oncology",
    "Genetic",
    "Infection",
    "Immune",
    "Cardiovascular",
    "Metabolic",
    "Signs/symptoms",
    "Neurology",
    "Psychiatry",
    "Digestive",
    "Congenital",
    "Respiratory",
    "Ophthalmology",
    "Musculoskeletal",
    "Reproductive/Fertility",
    "Injury/Trauma/Burns",
    "Dermatology",
    "Pregnancy complications",
    "Genitourinary/Urogenital",
    "Nephrology",
    "Endocrine",
    "Haematology",
    "Dental/Oral",
    "Environmental/Exposure",
}

MAPPED_VALUE_COLUMNS = [
    "RNA_Source_Mapped",
    "RNA_Source",
    "Disease_Mapped",
    "Tissue_Mapped",
    "Broad_Disease_Category",
    "CP_PubChem_Name",
    "CP_CID",
    "CP_CanonicalSMILES",
    "CP_PubChemURL",
    "CP_MatchType",
]

KEY_FIELD_TRIPLETS = [
    ("RNA_Library", "RNA_Library_Pre", "RNA_Library_Post", None),
    ("RNA_Source", "RNA_Source_Pre", "RNA_Source_Post", "RNA_Source_Mapped"),
    ("Disease", "Disease_Pre", "Disease_Post", "Disease_Mapped"),
    ("Tissue", "Tissue_Pre", "Tissue_Post", "Tissue_Mapped"),
    ("Perturbation", "Pert_Pre", "Pert_Post", "CP_PubChem_Name"),
    ("Age", "Age_Pre", "Age_Post", "Age_Group_Post"),
    ("Sex", "Sex_Pre", "Sex_Post", None),
]


def _norm(x: Any) -> str:
    if x is None:
        return ""
    v = str(x).strip()
    if v.lower() in {"", "nan", "none", "null", "unknown"}:
        return ""
    return v


def _norm_key(x: Any) -> str:
    v = _norm(x)
    if not v or v.upper() == NA_LABEL:
        return ""
    v = re.sub(r"\s+", " ", v).strip().lower()
    return v


def _na_if_blank(x: Any) -> str:
    v = _norm(x)
    if not v or v.lower() in {"na", "n/a", "nan", "none", "null", "unknown"}:
        return NA_LABEL
    return v


def _append_issue(existing: Any, issue: str) -> str:
    old = "" if existing is None else str(existing).strip()
    parts = [p.strip() for p in old.split(";") if p.strip() and p.strip().lower() not in {"na", "nan", "none"}]
    if issue not in parts:
        parts.append(issue)
    return "; ".join(parts)

def normalize_final_mapped_na_values(df: pd.DataFrame) -> pd.DataFrame:
    """Use explicit NA for reviewed/unmappable final mapped fields."""
    df = df.copy()
    for col in MAPPED_VALUE_COLUMNS:
        if col in df.columns:
            df[col] = df[col].map(_na_if_blank)
    return df


def load_ctd_disease_names(ctd_csv: Path) -> set[str]:
    if not Path(ctd_csv).exists():
        return set()
    ref = pd.read_csv(ctd_csv, dtype=str, keep_default_na=False)
    if "DiseaseName" not in ref.columns:
        return set()
    return set(ref["DiseaseName"].map(_norm).loc[lambda s: s.ne("")])


def load_tissue_category_vocabulary(tissue_category_xlsx: Path) -> set[str]:
    """Load tissue vocabulary from a master sheet or from separate tissue/brain sheets.

    Expected preferred format:
      sheet=Allowed_Tissue_Categories
      columns: Tissue_Category, Category_Group

    Backward-compatible behavior:
      collect non-empty values from columns named Tissue_Category, brain_subregions,
      or the first column of each sheet.
    """
    path = Path(tissue_category_xlsx)
    if not path.exists():
        return {NA_LABEL}

    sheets = pd.read_excel(path, sheet_name=None, dtype=str, keep_default_na=False)
    terms: set[str] = set()

    for _, sheet in sheets.items():
        if sheet.empty:
            continue

        sheet = sheet.copy()
        sheet.columns = [str(c).strip() for c in sheet.columns]

        candidate_cols = [
            c for c in sheet.columns
            if c.strip().lower() in {"tissue_category", "brain_subregions", "brain_subregion", "category"}
        ]

        if not candidate_cols:
            candidate_cols = [sheet.columns[0]]

        for col in candidate_cols:
            values = sheet[col].map(_norm)
            terms.update(v for v in values if v)

    terms.add(NA_LABEL)
    return terms


def load_broad_category_vocabulary(prior_disease_mapping_xlsx: Path) -> set[str]:
    cats = set(DEFAULT_BROAD_DISEASE_CATEGORIES)

    path = Path(prior_disease_mapping_xlsx)
    if path.exists():
        try:
            df = pd.read_excel(path, dtype=str, keep_default_na=False)
            if "Broad_Disease_Category" in df.columns:
                cats.update(
                    v for v in df["Broad_Disease_Category"].map(_norm)
                    if v and v.upper() != "N/A"
                )
        except Exception:
            pass

    cats.add(NA_LABEL)
    return cats


def disease_family_key(term: Any) -> str:
    """Normalize disease-like labels for similarity-consistency checks."""
    v = _norm_key(term)
    if not v:
        return ""

    v = re.sub(r"\s*\((extracted|inferred)\)\s*$", "", v, flags=re.I)
    v = re.sub(r"[-_/]", " ", v)
    v = re.sub(r"\b(cancers|cancer|carcinomas|carcinoma|neoplasms|neoplasm|tumours|tumour|tumors|tumor)\b", "neoplasm", v)
    v = re.sub(r"\s+", " ", v).strip()
    return v


def _make_issue_row(
    row: pd.Series,
    field: str,
    check_type: str,
    severity: str,
    issue: str,
    expected: Any = "",
    observed: Any = "",
) -> Dict[str, Any]:
    return {
        "GSM_ID": row.get("GSM_ID", ""),
        "GSE_ID": row.get("GSE_ID", ""),
        "Field": field,
        "Check_Type": check_type,
        "Severity": severity,
        "Issue": issue,
        "Expected_Value": expected,
        "Observed_Value": observed,
        "Pre_Value": row.get(f"{field}_Pre", ""),
        "Post_Value": row.get(f"{field}_Post", ""),
        "Mapped_Value": row.get(f"{field}_Mapped", row.get(field, "")),
    }


def check_disease_mapped_vocabulary(df: pd.DataFrame, valid_disease_names: set[str]) -> pd.DataFrame:
    rows = []
    if "Disease_Mapped" not in df.columns:
        return pd.DataFrame()

    valid = set(valid_disease_names) | ALLOWED_NON_DISEASE_LABELS

    for _, row in df.iterrows():
        mapped = _na_if_blank(row.get("Disease_Mapped", ""))
        disease_id = _norm(row.get("DiseaseID", ""))

        if mapped not in valid:
            rows.append(
                _make_issue_row(
                    row,
                    field="Disease",
                    check_type="closed_vocabulary",
                    severity="ERROR",
                    issue="Disease_Mapped is not a CTD/MEDIC DiseaseName or approved non-disease/NA label.",
                    expected="CTD/MEDIC DiseaseName, Normal, Adjacent Normal, No Disease Mentioned, or NA",
                    observed=mapped,
                )
            )
            continue

        if mapped not in ALLOWED_NON_DISEASE_LABELS and not disease_id:
            rows.append(
                _make_issue_row(
                    row,
                    field="Disease",
                    check_type="missing_reference_id",
                    severity="ERROR",
                    issue="Disease_Mapped is a disease label but DiseaseID is missing.",
                    expected="DiseaseID present",
                    observed=f"Disease_Mapped={mapped}; DiseaseID={disease_id}",
                )
            )

    return pd.DataFrame(rows)


def check_tissue_mapped_vocabulary(df: pd.DataFrame, valid_tissue_terms: set[str]) -> pd.DataFrame:
    rows = []
    if "Tissue_Mapped" not in df.columns:
        return pd.DataFrame()

    for _, row in df.iterrows():
        mapped = _na_if_blank(row.get("Tissue_Mapped", ""))
        if mapped not in valid_tissue_terms:
            rows.append(
                _make_issue_row(
                    row,
                    field="Tissue",
                    check_type="closed_vocabulary",
                    severity="ERROR",
                    issue="Tissue_Mapped is not in the approved tissue-category vocabulary.",
                    expected="Approved tissue category or NA",
                    observed=mapped,
                )
            )

    return pd.DataFrame(rows)


def check_broad_category_vocabulary(df: pd.DataFrame, valid_categories: set[str]) -> pd.DataFrame:
    rows = []
    if "Broad_Disease_Category" not in df.columns:
        return pd.DataFrame()

    for _, row in df.iterrows():
        cat = _na_if_blank(row.get("Broad_Disease_Category", ""))
        if cat not in valid_categories:
            rows.append(
                _make_issue_row(
                    row,
                    field="Broad_Disease_Category",
                    check_type="closed_vocabulary",
                    severity="ERROR",
                    issue="Broad_Disease_Category is not in the approved broad-category vocabulary.",
                    expected="Approved broad disease category or NA",
                    observed=cat,
                )
            )

    return pd.DataFrame(rows)

def check_cp_mapping_integrity(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    required = {"Pert_Type", "Pert_Post", "CP_PubChem_Name", "CP_CID", "CP_CanonicalSMILES"}

    if not required.issubset(df.columns):
        return pd.DataFrame()

    for _, row in df.iterrows():
        pert_type = _norm(row.get("Pert_Type", "")).upper()
        cp_name = _na_if_blank(row.get("CP_PubChem_Name", ""))
        cid = _na_if_blank(row.get("CP_CID", ""))
        smiles = _na_if_blank(row.get("CP_CanonicalSMILES", ""))

        if pert_type == "CP":
            if cp_name == NA_LABEL or cid == NA_LABEL or smiles == NA_LABEL:
                rows.append(
                    _make_issue_row(
                        row,
                        field="Perturbation",
                        check_type="cp_structure_mapping",
                        severity="REVIEW",
                        issue="Pert_Type is CP but CP PubChem name, CID, or CanonicalSMILES is missing.",
                        expected="CP_PubChem_Name, CP_CID, and CP_CanonicalSMILES present",
                        observed=f"CP_PubChem_Name={cp_name}; CP_CID={cid}; CP_CanonicalSMILES={smiles}",
                    )
                )

        elif pert_type and pert_type != "CP":
            non_na_cp_fields = []
            for c in ["CP_PubChem_Name", "CP_CID", "CP_CanonicalSMILES", "CP_PubChemURL"]:
                if c in df.columns and _na_if_blank(row.get(c, "")) != NA_LABEL:
                    non_na_cp_fields.append(c)

            if non_na_cp_fields:
                rows.append(
                    _make_issue_row(
                        row,
                        field="Perturbation",
                        check_type="non_cp_has_cp_mapping",
                        severity="REVIEW",
                        issue="Non-CP perturbation row has CP mapping fields populated.",
                        expected="CP fields should be NA for non-CP rows",
                        observed=", ".join(non_na_cp_fields),
                    )
                )

    return pd.DataFrame(rows)


def check_broad_category_consistency(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Check same mapped disease -> same broad category, and neoplasms -> Oncology."""
    conflict_rows = []
    neoplasm_rows = []

    if {"Disease_Mapped", "Broad_Disease_Category"}.issubset(df.columns):
        work = df.copy()
        work["_disease_key"] = work["Disease_Mapped"].map(_norm_key)
        work["_broad"] = work["Broad_Disease_Category"].map(_na_if_blank)

        valid = work[
            work["_disease_key"].ne("")
            & ~work["Disease_Mapped"].isin(ALLOWED_NON_DISEASE_LABELS)
        ].copy()

        grouped = valid.groupby("_disease_key")["_broad"].agg(lambda s: sorted(set(s))).reset_index()
        conflict_keys = grouped[grouped["_broad"].map(len) > 1]["_disease_key"]

        for _, row in valid[valid["_disease_key"].isin(conflict_keys)].iterrows():
            cats = grouped.loc[grouped["_disease_key"] == row["_disease_key"], "_broad"].iloc[0]
            conflict_rows.append(
                _make_issue_row(
                    row,
                    field="Broad_Disease_Category",
                    check_type="same_disease_same_broad_category",
                    severity="ERROR",
                    issue="The same Disease_Mapped value has multiple Broad_Disease_Category values.",
                    expected="One broad category per Disease_Mapped",
                    observed=" | ".join(cats),
                )
            )

        cancer_like = valid["Disease_Mapped"].astype(str).str.contains(
            r"\b(?:cancer|carcinoma|neoplasm|neoplasms|tumou?r)\b",
            case=False,
            regex=True,
            na=False,
        )
        not_oncology = valid["_broad"].ne("Oncology")

        for _, row in valid[cancer_like & not_oncology].iterrows():
            neoplasm_rows.append(
                _make_issue_row(
                    row,
                    field="Broad_Disease_Category",
                    check_type="neoplasm_category_rule",
                    severity="REVIEW",
                    issue="Cancer/carcinoma/neoplasm-like Disease_Mapped is not assigned to Oncology.",
                    expected="Oncology",
                    observed=row.get("Broad_Disease_Category", ""),
                )
            )

    return pd.DataFrame(conflict_rows), pd.DataFrame(neoplasm_rows)


def check_similar_disease_mapping_consistency(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    required = {"Disease_Post", "Disease_Mapped", "Broad_Disease_Category"}
    if not required.issubset(df.columns):
        return pd.DataFrame()

    work = df.copy()
    work["_family_key"] = work["Disease_Post"].map(disease_family_key)
    work["_mapped"] = work["Disease_Mapped"].map(_na_if_blank)
    work["_broad"] = work["Broad_Disease_Category"].map(_na_if_blank)

    work = work[
        work["_family_key"].ne("")
        & ~work["_mapped"].isin(ALLOWED_NON_DISEASE_LABELS)
    ]

    grouped = (
        work.groupby("_family_key")
        .agg(
            mapped_terms=("_mapped", lambda s: sorted(set(s))),
            broad_categories=("_broad", lambda s: sorted(set(s))),
        )
        .reset_index()
    )

    bad_keys = grouped[
        grouped["mapped_terms"].map(len).gt(1)
        | grouped["broad_categories"].map(len).gt(1)
    ]

    if bad_keys.empty:
        return pd.DataFrame()

    bad_lookup = bad_keys.set_index("_family_key").to_dict(orient="index")

    for _, row in work[work["_family_key"].isin(bad_lookup.keys())].iterrows():
        info = bad_lookup[row["_family_key"]]
        rows.append(
            _make_issue_row(
                row,
                field="Disease",
                check_type="similar_term_mapping_consistency",
                severity="REVIEW",
                issue="Similar disease terms have inconsistent Disease_Mapped or Broad_Disease_Category assignments.",
                expected=(
                    "Disease family should map consistently; cancer/carcinoma/neoplasm variants "
                    "should usually map to the same CTD/MEDIC term and Oncology."
                ),
                observed=(
                    f"Mapped={info['mapped_terms']}; Broad={info['broad_categories']}"
                ),
            )
        )

    return pd.DataFrame(rows)


def check_generic_mapping_consistency(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Global and within-GSE consistency for Pre/Post/Mapped field families."""
    global_rows = []
    gse_rows = []

    for field, pre_col, post_col, mapped_col in KEY_FIELD_TRIPLETS:
        if post_col not in df.columns:
            continue

        # Same Post should not map to multiple mapped values.
        if mapped_col and mapped_col in df.columns:
            work = df[["GSM_ID", "GSE_ID", pre_col, post_col, mapped_col]].copy() if pre_col in df.columns else df[["GSM_ID", "GSE_ID", post_col, mapped_col]].copy()
            work["_post_key"] = work[post_col].map(_norm_key)
            work["_mapped"] = work[mapped_col].map(_na_if_blank)
            work = work[work["_post_key"].ne("")]

            grouped = work.groupby("_post_key")["_mapped"].agg(lambda s: sorted(set(s))).reset_index()
            bad_keys = set(grouped[grouped["_mapped"].map(len) > 1]["_post_key"])

            if bad_keys:
                lookup = grouped.set_index("_post_key")["_mapped"].to_dict()
                for _, row in work[work["_post_key"].isin(bad_keys)].iterrows():
                    global_rows.append(
                        {
                            "GSM_ID": row.get("GSM_ID", ""),
                            "GSE_ID": row.get("GSE_ID", ""),
                            "Field": field,
                            "Check_Type": "global_same_post_same_mapped",
                            "Severity": "REVIEW",
                            "Issue": f"Same {post_col} value maps to multiple {mapped_col} values globally.",
                            "Expected_Value": f"One {mapped_col} per {post_col}",
                            "Observed_Value": " | ".join(lookup[row["_post_key"]]),
                            "Pre_Value": row.get(pre_col, ""),
                            "Post_Value": row.get(post_col, ""),
                            "Mapped_Value": row.get(mapped_col, ""),
                        }
                    )

            grouped_gse = work.groupby(["GSE_ID", "_post_key"])["_mapped"].agg(lambda s: sorted(set(s))).reset_index()
            bad_gse = grouped_gse[grouped_gse["_mapped"].map(len) > 1]

            if not bad_gse.empty:
                bad_pairs = set(zip(bad_gse["GSE_ID"], bad_gse["_post_key"]))
                lookup = bad_gse.set_index(["GSE_ID", "_post_key"])["_mapped"].to_dict()
                for _, row in work[work.apply(lambda r: (r["GSE_ID"], r["_post_key"]) in bad_pairs, axis=1)].iterrows():
                    gse_rows.append(
                        {
                            "GSM_ID": row.get("GSM_ID", ""),
                            "GSE_ID": row.get("GSE_ID", ""),
                            "Field": field,
                            "Check_Type": "within_gse_same_post_same_mapped",
                            "Severity": "ERROR",
                            "Issue": f"Within the same GSE, identical {post_col} values map to multiple {mapped_col} values.",
                            "Expected_Value": f"One {mapped_col} per {post_col} within GSE",
                            "Observed_Value": " | ".join(lookup[(row["GSE_ID"], row["_post_key"])]),
                            "Pre_Value": row.get(pre_col, ""),
                            "Post_Value": row.get(post_col, ""),
                            "Mapped_Value": row.get(mapped_col, ""),
                        }
                    )

        # Same Pre within the same GSE should not become multiple Post values unless study design truly supports it.
        if pre_col in df.columns:
            work2 = df[["GSM_ID", "GSE_ID", pre_col, post_col]].copy()
            work2["_pre_key"] = work2[pre_col].map(_norm_key)
            work2["_post"] = work2[post_col].map(_na_if_blank)
            work2 = work2[work2["_pre_key"].ne("")]

            grouped_pre = work2.groupby(["GSE_ID", "_pre_key"])["_post"].agg(lambda s: sorted(set(s))).reset_index()
            bad_pre = grouped_pre[grouped_pre["_post"].map(len) > 1]
            if not bad_pre.empty:
                bad_pairs = set(zip(bad_pre["GSE_ID"], bad_pre["_pre_key"]))
                lookup = bad_pre.set_index(["GSE_ID", "_pre_key"])["_post"].to_dict()
                for _, row in work2[work2.apply(lambda r: (r["GSE_ID"], r["_pre_key"]) in bad_pairs, axis=1)].iterrows():
                    gse_rows.append(
                        {
                            "GSM_ID": row.get("GSM_ID", ""),
                            "GSE_ID": row.get("GSE_ID", ""),
                            "Field": field,
                            "Check_Type": "within_gse_same_pre_same_post",
                            "Severity": "REVIEW",
                            "Issue": f"Within the same GSE, identical {pre_col} values have multiple {post_col} values.",
                            "Expected_Value": f"One {post_col} per identical {pre_col} within GSE unless justified",
                            "Observed_Value": " | ".join(lookup[(row["GSE_ID"], row["_pre_key"])]),
                            "Pre_Value": row.get(pre_col, ""),
                            "Post_Value": row.get(post_col, ""),
                            "Mapped_Value": row.get(mapped_col, "") if mapped_col and mapped_col in df.columns else "",
                        }
                    )

    return pd.DataFrame(global_rows), pd.DataFrame(gse_rows)


def _write_stage4_workbook(
    path: Path,
    summary_df: pd.DataFrame,
    sheets: Dict[str, pd.DataFrame],
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="summary", index=False)
        for name, sheet_df in sheets.items():
            safe_name = re.sub(r"[\[\]\:\*\?\/\\]", "_", name)[:31]
            if sheet_df is None or sheet_df.empty:
                pd.DataFrame().to_excel(writer, sheet_name=safe_name, index=False)
            else:
                sheet_df.to_excel(writer, sheet_name=safe_name, index=False)

    return path


def validate_stage3_release_qa(cfg, df_final: pd.DataFrame) -> Tuple[pd.DataFrame, Path]:
    """Final Stage 4 QA for mapped/release fields.

    This function is intentionally deterministic. It does not call an LLM.
    It validates closed vocabularies, mapping consistency, broad disease
    category consistency, and within-GSE consistency across key release fields.
    """
    df = normalize_final_mapped_na_values(df_final)

    # Keep release QA columns string-safe when inputs are loaded from Excel
    # with dtype=str or pandas string dtype.
    for c in ["Review_Required", "Global_QC_Status", "Review_Reason"]:
        if c in df.columns:
            df[c] = df[c].astype("object")

    ctd_csv = Path(getattr(cfg, "ctd_csv"))
    tissue_category_xlsx_value = getattr(cfg, "tissue_category_xlsx", None)
    if tissue_category_xlsx_value is None:
        tissue_category_xlsx_value = (
            Path(getattr(cfg, "workdir"))
            / "mappings"
            / "tissue"
            / "tissue_categories.xlsx"
        )
    tissue_category_xlsx = Path(tissue_category_xlsx_value)
    prior_disease_mapping_xlsx = Path(getattr(cfg, "prior_disease_mapping_xlsx"))

    valid_disease_names = load_ctd_disease_names(ctd_csv)
    valid_tissue_terms = load_tissue_category_vocabulary(tissue_category_xlsx)
    valid_broad_categories = load_broad_category_vocabulary(prior_disease_mapping_xlsx)

    disease_invalid = check_disease_mapped_vocabulary(df, valid_disease_names)
    tissue_invalid = check_tissue_mapped_vocabulary(df, valid_tissue_terms)
    broad_invalid = check_broad_category_vocabulary(df, valid_broad_categories)
    broad_conflicts, neoplasm_conflicts = check_broad_category_consistency(df)
    similar_disease_conflicts = check_similar_disease_mapping_consistency(df)
    global_consistency, within_gse_consistency = check_generic_mapping_consistency(df)
    cp_integrity = check_cp_mapping_integrity(df)

    issue_tables = [
        disease_invalid,
        tissue_invalid,
        broad_invalid,
        broad_conflicts,
        neoplasm_conflicts,
        similar_disease_conflicts,
        global_consistency,
        within_gse_consistency,
        cp_integrity,
    ]

    row_issues = pd.concat(
        [x for x in issue_tables if x is not None and not x.empty],
        ignore_index=True,
    ) if any(x is not None and not x.empty for x in issue_tables) else pd.DataFrame(
        columns=[
            "GSM_ID", "GSE_ID", "Field", "Check_Type", "Severity", "Issue",
            "Expected_Value", "Observed_Value", "Pre_Value", "Post_Value", "Mapped_Value",
        ]
    )

    df["Mapping_QA_Status"] = "PASS"
    df["Mapping_QA_Issue"] = ""
    df["Release_Ready"] = "True"

    if not row_issues.empty:
        for _, issue in row_issues.iterrows():
            gsm = str(issue.get("GSM_ID", "")).strip()
            if not gsm or "GSM_ID" not in df.columns:
                continue

            mask = df["GSM_ID"].astype(str).eq(gsm)
            short_issue = f"{issue.get('Field', '')}: {issue.get('Check_Type', '')}"
            df.loc[mask, "Mapping_QA_Status"] = "REVIEW"
            df.loc[mask, "Mapping_QA_Issue"] = df.loc[mask, "Mapping_QA_Issue"].map(
                lambda x, si=short_issue: _append_issue(x, si)
            )
            df.loc[mask, "Release_Ready"] = "False"

            if "Review_Required" in df.columns:
                df.loc[mask, "Review_Required"] = "True"
            if "Global_QC_Status" in df.columns:
                df.loc[mask, "Global_QC_Status"] = "REVIEW"
            if "Review_Reason" in df.columns:
                df.loc[mask, "Review_Reason"] = df.loc[mask, "Review_Reason"].map(
                    lambda x, si=short_issue: _append_issue(x, f"Stage4 QA: {si}")
                )

    summary_rows = [
        {"Metric": "Rows checked", "Value": len(df)},
        {"Metric": "Valid CTD/MEDIC disease names loaded", "Value": len(valid_disease_names)},
        {"Metric": "Valid tissue categories loaded", "Value": len(valid_tissue_terms)},
        {"Metric": "Valid broad disease categories loaded", "Value": len(valid_broad_categories)},
        {"Metric": "Disease mapped vocabulary issues", "Value": len(disease_invalid)},
        {"Metric": "Tissue mapped vocabulary issues", "Value": len(tissue_invalid)},
        {"Metric": "Broad category vocabulary issues", "Value": len(broad_invalid)},
        {"Metric": "Same disease -> broad category conflicts", "Value": len(broad_conflicts)},
        {"Metric": "Neoplasm not Oncology review flags", "Value": len(neoplasm_conflicts)},
        {"Metric": "Similar disease consistency flags", "Value": len(similar_disease_conflicts)},
        {"Metric": "Global mapping consistency flags", "Value": len(global_consistency)},
        {"Metric": "Within-GSE consistency flags", "Value": len(within_gse_consistency)},
        {"Metric": "CP mapping integrity flags", "Value": len(cp_integrity)},
        {"Metric": "Rows with any Stage4 QA issue", "Value": int(df["Mapping_QA_Status"].eq("REVIEW").sum())},
    ]

    summary_df = pd.DataFrame(summary_rows)

    qa_path = (
        Path(getattr(cfg, "review_dir"))
        / f"{getattr(cfg, 'run_version', 'geometa')}_stage4_release_mapping_qa.xlsx"
    )

    sheets = {
        "disease_invalid": disease_invalid,
        "tissue_invalid": tissue_invalid,
        "broad_invalid": broad_invalid,
        "broad_conflicts": broad_conflicts,
        "neoplasm_review": neoplasm_conflicts,
        "similar_disease": similar_disease_conflicts,
        "global_consistency": global_consistency,
        "within_gse": within_gse_consistency,
        "cp_integrity": cp_integrity,
        "row_issues": row_issues,
    }

    _write_stage4_workbook(qa_path, summary_df, sheets)

    error_count = 0
    if not row_issues.empty and "Severity" in row_issues.columns:
        error_count = int(
            row_issues["Severity"]
            .astype(str)
            .str.upper()
            .eq("ERROR")
            .sum()
        )

    if bool(getattr(cfg, "stage4_fail_on_mapping_qa_errors", False)) and error_count > 0:
        raise ValueError(
            f"Stage4 mapping QA found {error_count} ERROR-level issues. "
            f"QA report saved to: {qa_path}"
        )

    return df, qa_path
