from __future__ import annotations

import re
import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

import pandas as pd

from geo_annotation_agent.config import default_config
from geo_annotation_agent.reviewer import ReviewerV2
from geo_annotation_agent.reviewer_llm import ReviewerLLMV2, LLMReviewConfig
from geo_annotation_agent.stage0_retrieve import run_stage0_retrieval
from geo_annotation_agent.stage1_annotate import run_stage1_raw_annotation_v2
from geo_annotation_agent.stage2_postprocess import (
    run_stage2_postprocessing,
    run_stage2_postprocessing_v2,
)
from geo_annotation_agent.stage3_map import run_stage3_mapping
from geo_annotation_agent.excel_safe import write_excel_with_long_text_parts

from geo_annotation_agent.excel_report_utils import (
    format_excel_workbook,
    write_dataframes_to_excel,
)

from within_gse_consistency_audit import build_audit_and_corrections, AuditConfig, write_excel
from stage1_cross_agent_validation import validate_cross_agent, ValidationConfig, write_outputs
from stage1_evidence_verifier import EvidenceVerifierConfig, run_stage1_qa3_verification_pipeline
from stage1_provenance_audit import write_stage1_provenance_workbook


def make_run_version(prefix: str = "geometa_full") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

def print_stage_time(stage_name: str, seconds: float) -> None:
    minutes = seconds / 60
    print(f"[TIME] {stage_name}: {seconds:.2f} sec ({minutes:.2f} min)")


def clean_gse_ids(values: Iterable[str]) -> List[str]:
    out = []
    seen = set()

    for value in values:
        x = str(value).strip()
        if not x or x.lower() in {"nan", "none", "na", "unknown"}:
            continue
        if x not in seen:
            out.append(x)
            seen.add(x)

    return out


def read_gse_file(path: Path) -> List[str]:
    if not path.exists():
        raise FileNotFoundError(f"GSE input file not found: {path}")

    suffix = path.suffix.lower()

    if suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(path, engine="openpyxl")
    elif suffix == ".csv":
        df = pd.read_csv(path)
    elif suffix == ".tsv":
        df = pd.read_csv(path, sep="\t")
    elif suffix == ".txt":
        return clean_gse_ids(path.read_text(encoding="utf-8").splitlines())
    else:
        raise ValueError(f"Unsupported GSE input file type: {path}")

    values = df["GSE_ID"].tolist() if "GSE_ID" in df.columns else df.iloc[:, 0].tolist()
    return clean_gse_ids(values)


def write_gse_input_file(gse_ids: List[str], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    clean_ids = clean_gse_ids(gse_ids)

    if not clean_ids:
        raise ValueError("No valid GSE IDs were provided.")

    df = pd.DataFrame({"GSE_ID": clean_ids})
    suffix = out_path.suffix.lower()

    if suffix == ".csv":
        df.to_csv(out_path, index=False)
    elif suffix == ".tsv":
        df.to_csv(out_path, sep="\t", index=False)
    elif suffix in {".xlsx", ".xls"}:
        df.to_excel(out_path, index=False)
    else:
        raise ValueError(f"Unsupported GSE output file type: {out_path}")

    return out_path



def read_gse_input_table(path: Path) -> pd.DataFrame:
    """
    Read the original GSE input table while preserving non-GSE columns such as Counts.
    This is used for integrity auditing; read_gse_file() is still used to build the
    deduplicated GSE list used by the pipeline.
    """
    if not path.exists():
        raise FileNotFoundError(f"GSE input file not found: {path}")

    suffix = path.suffix.lower()

    if suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(path, engine="openpyxl")
    elif suffix == ".csv":
        df = pd.read_csv(path)
    elif suffix == ".tsv":
        df = pd.read_csv(path, sep="\t")
    elif suffix == ".txt":
        df = pd.DataFrame({"GSE_ID": path.read_text(encoding="utf-8").splitlines()})
    else:
        raise ValueError(f"Unsupported GSE input file type: {path}")

    if "GSE_ID" not in df.columns:
        df = df.rename(columns={df.columns[0]: "GSE_ID"})

    df["GSE_ID"] = df["GSE_ID"].astype(str).str.strip()
    df = df[
        ~df["GSE_ID"].str.lower().isin({"", "nan", "none", "na", "unknown"})
    ].copy()

    return df


def write_duplicated_input_gse_report(original_gse_file: Path, out_path: Path) -> Path | None:
    """
    Save duplicated input GSE_ID rows, if any. Returns the output path when duplicates
    are present; otherwise returns None.
    """
    df_input = read_gse_input_table(original_gse_file)

    duplicated = df_input[df_input["GSE_ID"].duplicated(keep=False)].copy()
    if duplicated.empty:
        return None

    duplicated = duplicated.sort_values("GSE_ID")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    duplicated.to_excel(out_path, index=False)

    return out_path


def write_input_count_audit(
    original_gse_file: Path,
    df_stage1: pd.DataFrame,
    out_path: Path,
) -> Path:
    """
    Compare the original input Counts column against actual annotated GSM rows.

    This audit is intentionally separate from Stage0 failed-GSE/GSM reports:
    - Stage0 failed reports track GEO retrieval failures.
    - This audit tracks expected-vs-actual sample count mismatches and duplicate
      GSE_ID rows in the submitted input file.

    If the input does not contain a Counts column, the audit still reports input
    duplicate GSE_IDs and annotated GSM counts.
    """
    df_input = read_gse_input_table(original_gse_file)

    if "Counts" not in df_input.columns:
        df_input["Counts"] = pd.NA

    df_input["Counts_numeric"] = pd.to_numeric(df_input["Counts"], errors="coerce")

    input_audit = (
        df_input
        .groupby("GSE_ID", dropna=False)
        .agg(
            Input_Rows=("GSE_ID", "size"),
            Input_Count_First=("Counts_numeric", "first"),
            Input_Count_Total=("Counts_numeric", "sum"),
        )
        .reset_index()
    )

    # A missing Counts column produces zero after sum(); keep the distinction explicit.
    has_counts_column = "Counts" in read_gse_input_table(original_gse_file).columns
    if not has_counts_column:
        input_audit["Input_Count_First"] = pd.NA
        input_audit["Input_Count_Total"] = pd.NA

    if "GSE_ID" not in df_stage1.columns or "GSM_ID" not in df_stage1.columns:
        raise ValueError("Stage1 dataframe must contain GSE_ID and GSM_ID for count audit.")

    annotated_counts = (
        df_stage1
        .assign(
            GSE_ID=df_stage1["GSE_ID"].astype(str).str.strip(),
            GSM_ID=df_stage1["GSM_ID"].astype(str).str.strip(),
        )
        .loc[lambda d: (d["GSM_ID"] != "") & (d["GSM_ID"].str.lower() != "nan")]
        .groupby("GSE_ID", dropna=False)["GSM_ID"]
        .nunique()
        .reset_index(name="Annotated_GSM_Count")
    )

    audit = input_audit.merge(annotated_counts, on="GSE_ID", how="left")
    audit["Annotated_GSM_Count"] = audit["Annotated_GSM_Count"].fillna(0).astype(int)
    audit["Has_Duplicate_Input_GSE"] = audit["Input_Rows"] > 1

    if has_counts_column:
        audit["Count_Difference_vs_First_Count"] = (
            audit["Annotated_GSM_Count"] - audit["Input_Count_First"]
        )
        audit["Count_Difference_vs_Total_Count"] = (
            audit["Annotated_GSM_Count"] - audit["Input_Count_Total"]
        )
    else:
        audit["Count_Difference_vs_First_Count"] = pd.NA
        audit["Count_Difference_vs_Total_Count"] = pd.NA

    def _status(row):
        if not has_counts_column:
            return "No input Counts column; annotated GSM count reported only"
        if row["Has_Duplicate_Input_GSE"]:
            return "Duplicate GSE_ID in input; Counts total may be inflated"
        if pd.isna(row["Input_Count_First"]):
            return "Missing input Counts value"
        if row["Count_Difference_vs_First_Count"] == 0:
            return "Matched"
        if row["Count_Difference_vs_First_Count"] < 0:
            return "Fewer annotated GSMs than input Counts"
        return "More annotated GSMs than input Counts"

    audit["Status"] = audit.apply(_status, axis=1)

    preferred_cols = [
        "GSE_ID",
        "Input_Rows",
        "Input_Count_First",
        "Input_Count_Total",
        "Annotated_GSM_Count",
        "Count_Difference_vs_First_Count",
        "Count_Difference_vs_Total_Count",
        "Has_Duplicate_Input_GSE",
        "Status",
    ]
    audit = audit[preferred_cols].sort_values(
        ["Status", "GSE_ID"], kind="stable"
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    audit.to_excel(out_path, index=False)

    return out_path



def _clean_gsm_id_series(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip()


def _valid_gsm_mask(s: pd.Series) -> pd.Series:
    vals = _clean_gsm_id_series(s)
    return (vals != "") & (~vals.str.lower().isin({"nan", "none", "na", "unknown"}))


def stage0_expected_gsm_table(df_stage0: pd.DataFrame) -> pd.DataFrame:
    """
    Expand Stage0 chunk-level GSM_ID_List into one row per expected/retrieved GSM.
    This is the retrieval-derived sample universe used for downstream integrity checks.
    """
    rows = []
    if df_stage0 is None or df_stage0.empty or "GSM_ID_List" not in df_stage0.columns:
        return pd.DataFrame(columns=["GSE_ID", "GSM_ID", "Chunk_ID", "Chunk_Index"])

    for _, r in df_stage0.iterrows():
        gse_id = str(r.get("GSE_ID", "")).strip()
        chunk_id = str(r.get("Chunk_ID", "")).strip()
        chunk_index = r.get("Chunk_Index", "")
        gsm_list = str(r.get("GSM_ID_List", "")).strip()
        if not gsm_list or gsm_list.lower() in {"nan", "none", "na", "unknown"}:
            continue
        for gsm_id in [x.strip() for x in gsm_list.split("|") if x.strip()]:
            rows.append({
                "GSE_ID": gse_id,
                "GSM_ID": gsm_id,
                "Chunk_ID": chunk_id,
                "Chunk_Index": chunk_index,
            })
    return pd.DataFrame(rows)


def sample_identity_table(df: pd.DataFrame, stage_name: str) -> pd.DataFrame:
    if df is None or df.empty or "GSM_ID" not in df.columns:
        return pd.DataFrame(columns=["stage", "GSE_ID", "GSM_ID"])
    out = df.copy()
    if "GSE_ID" not in out.columns:
        out["GSE_ID"] = ""
    out["GSE_ID"] = out["GSE_ID"].astype(str).str.strip()
    out["GSM_ID"] = out["GSM_ID"].astype(str).str.strip()
    out = out.loc[_valid_gsm_mask(out["GSM_ID"]), ["GSE_ID", "GSM_ID"]].drop_duplicates()
    out.insert(0, "stage", stage_name)
    return out


def write_stage_transition_audit(
    cfg,
    df_stage0: pd.DataFrame,
    df_stage1: pd.DataFrame,
    df_stage2_pass1: pd.DataFrame,
    df_stage2_final: pd.DataFrame,
    df_stage3: pd.DataFrame,
) -> tuple[Path, Path]:
    """
    Save GSM identity preservation checks across Stage0->Stage1->Stage2->Stage3.
    The Excel file lists missing/extra GSMs for each transition; the JSON file summarizes counts.
    """
    review_dir = Path(cfg.review_dir)
    ledger_dir = Path(cfg.ledger_dir)
    review_dir.mkdir(parents=True, exist_ok=True)
    ledger_dir.mkdir(parents=True, exist_ok=True)

    stage_tables = {
        "stage0_expected": stage0_expected_gsm_table(df_stage0).assign(stage="stage0_expected"),
        "stage1": sample_identity_table(df_stage1, "stage1"),
        "stage2_pass1": sample_identity_table(df_stage2_pass1, "stage2_pass1"),
        "stage2_final": sample_identity_table(df_stage2_final, "stage2_final"),
        "stage3": sample_identity_table(df_stage3, "stage3"),
    }

    def keyset(name: str) -> set[tuple[str, str]]:
        d = stage_tables[name]
        if d.empty:
            return set()
        return set(zip(d["GSE_ID"].astype(str), d["GSM_ID"].astype(str)))

    transitions = [
        ("stage0_expected", "stage1"),
        ("stage1", "stage2_pass1"),
        ("stage2_pass1", "stage2_final"),
        ("stage2_final", "stage3"),
    ]

    diff_rows = []
    summary = {
        "run_version": cfg.run_version,
        "stage_counts": {},
        "transition_counts": {},
        "status": "pass",
    }

    for name, tab in stage_tables.items():
        if tab.empty:
            summary["stage_counts"][name] = {"unique_gsm": 0, "rows": 0, "duplicate_gsm_rows": 0}
            continue
        duplicate_rows = int(tab["GSM_ID"].astype(str).duplicated().sum())
        summary["stage_counts"][name] = {
            "unique_gsm": int(tab["GSM_ID"].astype(str).nunique()),
            "rows": int(tab.shape[0]),
            "duplicate_gsm_rows": duplicate_rows,
        }

    for left, right in transitions:
        left_set = keyset(left)
        right_set = keyset(right)
        missing = sorted(left_set - right_set)
        extra = sorted(right_set - left_set)
        transition_status = "pass" if not missing and not extra else "review"
        if transition_status != "pass":
            summary["status"] = "review"
        summary["transition_counts"][f"{left}_to_{right}"] = {
            "missing_in_right": len(missing),
            "extra_in_right": len(extra),
            "status": transition_status,
        }
        for gse_id, gsm_id in missing:
            diff_rows.append({
                "transition": f"{left}_to_{right}",
                "issue": "missing_in_right",
                "GSE_ID": gse_id,
                "GSM_ID": gsm_id,
            })
        for gse_id, gsm_id in extra:
            diff_rows.append({
                "transition": f"{left}_to_{right}",
                "issue": "extra_in_right",
                "GSE_ID": gse_id,
                "GSM_ID": gsm_id,
            })

    diff_df = pd.DataFrame(diff_rows, columns=["transition", "issue", "GSE_ID", "GSM_ID"])

    xlsx_path = review_dir / f"{cfg.run_version}_stage_transition_gsm_audit.xlsx"
    json_path = ledger_dir / f"{cfg.run_version}_stage_transition_gsm_audit_summary.json"

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        pd.DataFrame([summary]).to_excel(writer, sheet_name="summary_json", index=False)
        pd.DataFrame(summary["stage_counts"]).T.reset_index(names="stage").to_excel(
            writer, sheet_name="stage_counts", index=False
        )
        pd.DataFrame(summary["transition_counts"]).T.reset_index(names="transition").to_excel(
            writer, sheet_name="transition_counts", index=False
        )
        diff_df.to_excel(writer, sheet_name="gsm_differences", index=False)
        for name, tab in stage_tables.items():
            tab.to_excel(writer, sheet_name=name[:31], index=False)

    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return xlsx_path, json_path


def write_stage0_chunk_to_stage1_audit(cfg, df_stage0: pd.DataFrame, df_stage1: pd.DataFrame) -> Path:
    """Compare each Stage0 chunk GSM_ID_List against Stage1 emitted GSMs."""
    rows = []
    stage1_ids = set()
    if df_stage1 is not None and not df_stage1.empty and {"GSE_ID", "GSM_ID"}.issubset(df_stage1.columns):
        tmp = df_stage1.copy()
        tmp["GSE_ID"] = tmp["GSE_ID"].astype(str).str.strip()
        tmp["GSM_ID"] = tmp["GSM_ID"].astype(str).str.strip()
        tmp = tmp.loc[_valid_gsm_mask(tmp["GSM_ID"]), ["GSE_ID", "GSM_ID"]]
        stage1_ids = set(zip(tmp["GSE_ID"], tmp["GSM_ID"]))

    for _, r in df_stage0.iterrows():
        gse_id = str(r.get("GSE_ID", "")).strip()
        chunk_id = str(r.get("Chunk_ID", "")).strip()
        expected = [x.strip() for x in str(r.get("GSM_ID_List", "")).split("|") if x.strip()]
        present = [gsm for gsm in expected if (gse_id, gsm) in stage1_ids]
        missing = [gsm for gsm in expected if (gse_id, gsm) not in stage1_ids]
        rows.append({
            "GSE_ID": gse_id,
            "Chunk_ID": chunk_id,
            "Chunk_Index": r.get("Chunk_Index", ""),
            "Stage0_GSM_Counts": r.get("GSM_Counts", ""),
            "Expected_GSM_Count": len(expected),
            "Stage1_Present_Count": len(present),
            "Stage1_Missing_Count": len(missing),
            "Missing_GSM_IDs": " | ".join(missing),
            "Status": "Matched" if not missing else "Review: missing Stage1 rows",
        })

    out = Path(cfg.review_dir) / f"{cfg.run_version}_stage0_chunk_to_stage1_audit.xlsx"
    pd.DataFrame(rows).to_excel(out, index=False)
    return out


def write_stage_completeness_audit(cfg, stage_name: str, df: pd.DataFrame) -> Path:
    """Save per-column missing/NA/Unknown counts for a stage output."""
    rows = []
    n = int(df.shape[0]) if df is not None else 0
    for c in (df.columns if df is not None else []):
        vals = df[c].astype(str).str.strip()
        missing = vals.str.lower().isin({"", "nan", "none", "na", "unknown"}).sum()
        rows.append({
            "stage": stage_name,
            "column": c,
            "row_count": n,
            "missing_na_unknown_count": int(missing),
            "missing_na_unknown_pct": round((int(missing) / n * 100), 3) if n else 0,
            "unique_nonmissing_values": int(vals.loc[~vals.str.lower().isin({"", "nan", "none", "na", "unknown"})].nunique()),
        })
    out = Path(cfg.ledger_dir) / f"{cfg.run_version}_{stage_name}_completeness_audit.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    return out


def write_stage2_change_audit(cfg, df_pass1: pd.DataFrame, df_final: pd.DataFrame) -> Path:
    """Document cells changed between Stage2 pass1 and Stage2 final rerun."""
    out = Path(cfg.review_dir) / f"{cfg.run_version}_stage2_pass1_to_final_change_audit.xlsx"
    if df_pass1 is None or df_final is None or df_pass1.empty or df_final.empty:
        pd.DataFrame(columns=["GSM_ID", "GSE_ID", "field", "pass1_value", "final_value"]).to_excel(out, index=False)
        return out

    if "GSM_ID" not in df_pass1.columns or "GSM_ID" not in df_final.columns:
        pd.DataFrame(columns=["GSM_ID", "GSE_ID", "field", "pass1_value", "final_value"]).to_excel(out, index=False)
        return out

    left = df_pass1.copy()
    right = df_final.copy()
    left["GSM_ID"] = left["GSM_ID"].astype(str).str.strip()
    right["GSM_ID"] = right["GSM_ID"].astype(str).str.strip()
    common_cols = [c for c in left.columns if c in right.columns and c not in {"GSM_ID", "GSE_ID", "GSE_Info", "GSM_Info"}]
    merged = left[["GSM_ID", "GSE_ID"] + common_cols].merge(
        right[["GSM_ID"] + common_cols], on="GSM_ID", how="inner", suffixes=("_pass1", "_final")
    )
    rows = []
    for _, r in merged.iterrows():
        for c in common_cols:
            a = str(r.get(f"{c}_pass1", "")).strip()
            b = str(r.get(f"{c}_final", "")).strip()
            if a != b:
                rows.append({
                    "GSM_ID": r.get("GSM_ID", ""),
                    "GSE_ID": r.get("GSE_ID", ""),
                    "field": c,
                    "pass1_value": a,
                    "final_value": b,
                })
    pd.DataFrame(rows, columns=["GSM_ID", "GSE_ID", "field", "pass1_value", "final_value"]).to_excel(out, index=False)
    return out


def write_run_manifest(cfg) -> Path:
    """Save a manifest of all run-versioned artifacts created so far."""
    artifacts_dir = Path(cfg.artifacts_dir)
    rows = []
    for fp in sorted(artifacts_dir.rglob(f"{cfg.run_version}*")):
        if fp.is_file():
            rows.append({
                "file_name": fp.name,
                "path": str(fp),
                "relative_path": str(fp.relative_to(artifacts_dir)),
                "size_bytes": fp.stat().st_size,
            })
    out = Path(cfg.ledger_dir) / f"{cfg.run_version}_artifact_manifest.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    return out

def _artifact_category_for_path(artifacts_dir: Path, fp: Path) -> str:
    try:
        rel = fp.relative_to(artifacts_dir)
        first = rel.parts[0] if rel.parts else "misc"
    except Exception:
        first = "misc"

    if first in {"outputs", "review_queue", "ledgers", "logs", "manual_review", "debug"}:
        return first
    return "misc"


def _link_or_copy_artifact(src: Path, dst: Path) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)

    if dst.exists() or dst.is_symlink():
        dst.unlink()

    try:
        dst.symlink_to(src)
        return "symlink"
    except Exception:
        import shutil

        shutil.copy2(src, dst)
        return "copy"


def write_run_folder_index(cfg) -> Path:
    """
    Create a user-facing run folder:

    artifacts/runs/<run_version>/
        outputs/
        review_queue/
        ledgers/
        logs/
        manual_review/
        debug/
        run_output_index.xlsx
        run_manifest.json
        README_outputs.txt

    Existing pipeline paths remain unchanged for backward compatibility.
    """
    artifacts_dir = Path(cfg.artifacts_dir)
    run_dir = artifacts_dir / "runs" / cfg.run_version
    run_dir.mkdir(parents=True, exist_ok=True)

    rows = []

    for fp in sorted(artifacts_dir.rglob(f"{cfg.run_version}*")):
        if not fp.is_file():
            continue

        # Avoid recursively indexing the run folder itself.
        if "runs" in fp.relative_to(artifacts_dir).parts:
            continue

        category = _artifact_category_for_path(artifacts_dir, fp)
        dest = run_dir / category / fp.name
        link_type = _link_or_copy_artifact(fp.resolve(), dest)

        rows.append(
            {
                "Run_Version": cfg.run_version,
                "Category": category,
                "File_Name": fp.name,
                "Original_Path": str(fp),
                "Run_Folder_Path": str(dest),
                "Link_Type": link_type,
                "Size_Bytes": int(fp.stat().st_size),
                "Created_Time": datetime.fromtimestamp(fp.stat().st_mtime).isoformat(timespec="seconds"),
            }
        )

    index_df = pd.DataFrame(rows).sort_values(["Category", "File_Name"], kind="stable") if rows else pd.DataFrame(
        columns=[
            "Run_Version",
            "Category",
            "File_Name",
            "Original_Path",
            "Run_Folder_Path",
            "Link_Type",
            "Size_Bytes",
            "Created_Time",
        ]
    )

    index_xlsx = run_dir / "run_output_index.xlsx"
    index_json = run_dir / "run_manifest.json"
    readme_txt = run_dir / "README_outputs.txt"

    index_df.to_excel(index_xlsx, index=False)
    format_excel_workbook(index_xlsx)
    index_json.write_text(
        json.dumps(
            {
                "run_version": cfg.run_version,
                "run_folder": str(run_dir),
                "n_artifacts": int(index_df.shape[0]),
                "artifacts": index_df.to_dict(orient="records"),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    readme_txt.write_text(
        "\n".join(
            [
                f"GEOMeta run folder: {cfg.run_version}",
                "",
                "This folder collects the run-versioned outputs generated by the pipeline.",
                "The original pipeline artifact paths are preserved; files here are symlinks or copies.",
                "",
                "Most users should inspect:",
                "1. outputs/*_stage1_final_for_stage2.xlsx",
                "2. outputs/*_stage2_post_final.xlsx",
                "3. outputs/*_stage3_final_release.xlsx",
                "4. outputs/*_stage3_cp_perturbation_release.xlsx",
                "5. review_queue/*_stage3_5_final_qc_report.xlsx",
                "6. review_queue/*_stage1_provenance_audit.xlsx",
                "",
                "See run_output_index.xlsx for a complete file index.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return run_dir

def _read_xlsx_sheet_if_exists(path: Path, sheet_name: str) -> pd.DataFrame:
    if path is None or not Path(path).exists():
        return pd.DataFrame(
            [{"Status": "Not generated", "Path": str(path) if path else ""}]
        )

    try:
        return pd.read_excel(path, sheet_name=sheet_name, dtype=str, keep_default_na=False)
    except Exception as e:
        return pd.DataFrame(
            [{"Status": "Could not read sheet", "Path": str(path), "Error": repr(e)}]
        )


def _artifact_user_description(file_name: str) -> tuple[str, str]:
    """
    Return user-facing description and recommended action for common GEOMeta artifacts.
    """
    name = str(file_name)

    rules = [
        (
            "_final_pipeline_report.xlsx",
            "Top-level run report",
            "Open first. Summarizes run status, row counts, QC status, and key output files.",
        ),
        (
            "_stage3_final_release.xlsx",
            "Primary final sample-level release file",
            "Use for most downstream analyses.",
        ),
        (
            "_stage3_cp_perturbation_release.xlsx",
            "Structure-ready CP perturbation release file",
            "Use for compound-perturbation downstream analyses.",
        ),
        (
            "_stage3_5_final_qc_report.xlsx",
            "Stage 3.5 final QC workbook",
            "Review QC summary, review queue, dose/duration summaries, and PubChem query status.",
        ),
        (
            "_stage4_release_mapping_qa.xlsx",
            "Stage 4 deterministic release QA workbook",
            "Check release mapping validation and row-level QA issues.",
        ),
        (
            "_stage1_provenance_audit.xlsx",
            "Stage 1 provenance audit workbook",
            "Inspect Stage 1 QA changes and provenance layers.",
        ),
        (
            "_stage1_final_for_stage2.xlsx",
            "Final Stage 1 input used for Stage 2",
            "Use to resume Stage 2 without rerunning Stage 1.",
        ),
        (
            "_stage2_post_final.xlsx",
            "Final Stage 2 postprocessed file",
            "Use to resume Stage 3 without rerunning Stage 1/2.",
        ),
        (
            "_stage3_mapped.xlsx",
            "Full Stage 3 mapped output",
            "Use for internal audit and complete mapped annotations.",
        ),
        (
            "_full_pipeline_summary.json",
            "Machine-readable full pipeline summary",
            "Use for automated checks or logging.",
        ),
    ]

    for suffix, description, action in rules:
        if name.endswith(suffix):
            return description, action

    return "Run artifact", "Inspect if relevant to the stage being reviewed."


def build_run_artifact_index_for_report(cfg) -> pd.DataFrame:
    artifacts_dir = Path(cfg.artifacts_dir)
    rows = []

    for fp in sorted(artifacts_dir.rglob(f"{cfg.run_version}*")):
        if not fp.is_file():
            continue

        try:
            rel = fp.relative_to(artifacts_dir)
            if "runs" in rel.parts:
                continue
        except Exception:
            rel = Path(fp.name)

        description, action = _artifact_user_description(fp.name)
        category = _artifact_category_for_path(artifacts_dir, fp)

        rows.append(
            {
                "Category": category,
                "File_Name": fp.name,
                "Description": description,
                "Recommended_User_Action": action,
                "Path": str(fp),
                "Size_Bytes": int(fp.stat().st_size) if fp.exists() else "",
                "Modified_Time": datetime.fromtimestamp(fp.stat().st_mtime).isoformat(timespec="seconds")
                if fp.exists()
                else "",
            }
        )

    out = pd.DataFrame(rows)

    if out.empty:
        return pd.DataFrame(
            columns=[
                "Category",
                "File_Name",
                "Description",
                "Recommended_User_Action",
                "Path",
                "Size_Bytes",
                "Modified_Time",
            ]
        )

    priority = {
        "Top-level run report": 0,
        "Primary final sample-level release file": 1,
        "Structure-ready CP perturbation release file": 2,
        "Stage 3.5 final QC workbook": 3,
        "Stage 4 deterministic release QA workbook": 4,
        "Stage 1 provenance audit workbook": 5,
        "Final Stage 1 input used for Stage 2": 6,
        "Final Stage 2 postprocessed file": 7,
        "Full Stage 3 mapped output": 8,
    }

    out["_priority"] = out["Description"].map(priority).fillna(99)
    out = out.sort_values(["_priority", "Category", "File_Name"], kind="stable")
    out = out.drop(columns=["_priority"])

    return out


def _summary_dict_to_df(summary: dict) -> pd.DataFrame:
    preferred_order = [
        "run_version",
        "gse_count",
        "stage0_rows",
        "stage1_rows",
        "stage2_pass1_rows",
        "stage2_rows",
        "stage3_rows",
        "stage1_unique_gsm",
        "stage2_pass1_unique_gsm",
        "stage2_unique_gsm",
        "stage3_unique_gsm",
        "stage1_dup_gsm",
        "stage2_dup_gsm",
        "stage3_dup_gsm",
        "stage_transition_audit_status",
        "stage1_qa3_mode",
        "stage1_qa3_max_tasks",
        "stage1_qa1_review_queue_rows",
        "stage1_qa2_issue_rows",
        "stage2_rule_review_rows",
        "stage2_llm_row_review_rows",
        "stage2_llm_gse_review_rows",
        "stage2_reannotation_queue_rows",
        "runtime_seconds",
        "runtime_minutes",
    ]

    rows = []

    for key in preferred_order:
        if key in summary:
            status = ""
            if key == "stage_transition_audit_status":
                status = "PASS" if str(summary.get(key)).lower() == "pass" else "REVIEW"
            elif key.endswith("_dup_gsm"):
                status = "PASS" if int(summary.get(key, 0)) == 0 else "REVIEW"
            rows.append(
                {
                    "Metric": key,
                    "Value": summary.get(key, ""),
                    "Status": status,
                }
            )

    for key, value in summary.items():
        if key.startswith("warning_"):
            rows.append(
                {
                    "Metric": key,
                    "Value": value,
                    "Status": "REVIEW" if value else "PASS",
                }
            )

    return pd.DataFrame(rows)


def _stage_timing_df(summary: dict) -> pd.DataFrame:
    stage_times = summary.get("stage_times_seconds", {}) or {}
    total = float(summary.get("runtime_seconds", 0) or 0)

    rows = []
    for stage, seconds in stage_times.items():
        sec = float(seconds)
        rows.append(
            {
                "Stage": stage.replace("_seconds", ""),
                "Seconds": round(sec, 2),
                "Minutes": round(sec / 60, 2),
                "Percent_Total_Runtime": round((sec / total * 100), 2) if total else "",
            }
        )

    return pd.DataFrame(rows)

def _stage1_qa_summary_df(summary: dict) -> pd.DataFrame:
    qa3_outputs = summary.get("stage1_qa3_outputs", {}) or {}

    return pd.DataFrame(
        [
            {
                "QA_Step": "QA1 within-GSE consistency audit",
                "Mode": "deterministic",
                "Rows_or_Issues": summary.get("stage1_qa1_review_queue_rows", ""),
                "Output": summary.get("stage1_qa1_report_xlsx", ""),
                "Recommended_User_Action": "Review QA1 queue if rows_or_issues > 0.",
            },
            {
                "QA_Step": "QA2 cross-agent validation",
                "Mode": "deterministic",
                "Rows_or_Issues": summary.get("stage1_qa2_issue_rows", ""),
                "Output": summary.get("stage1_qa2_report_xlsx", ""),
                "Recommended_User_Action": "Review QA2 issues; high-value unresolved issues feed QA3 smart mode.",
            },
            {
                "QA_Step": "QA3 evidence-grounded verifier",
                "Mode": summary.get("stage1_qa3_mode", ""),
                "Rows_or_Issues": summary.get("stage1_qa3_max_tasks", ""),
                "Output": json.dumps(qa3_outputs, ensure_ascii=False),
                "Recommended_User_Action": (
                    "QA3 was skipped." if summary.get("stage1_qa3_mode") == "off"
                    else "Review QA3 recommendations and human-review queue."
                ),
            },
        ]
    )


def _recommended_user_actions_df(cfg, summary: dict) -> pd.DataFrame:
    run_version = cfg.run_version
    outputs_dir = Path(cfg.outputs_dir)
    review_dir = Path(cfg.review_dir)
    runs_dir = Path(cfg.artifacts_dir) / "runs" / run_version

    rows = [
        {
            "Priority": 1,
            "Action": "Open the final pipeline report first.",
            "File": str(outputs_dir / f"{run_version}_final_pipeline_report.xlsx"),
        },
        {
            "Priority": 2,
            "Action": "Use the primary final release file for most downstream analyses.",
            "File": str(outputs_dir / f"{run_version}_stage3_final_release.xlsx"),
        },
        {
            "Priority": 3,
            "Action": "Use the CP perturbation release only for structure-ready compound perturbation analyses.",
            "File": str(outputs_dir / f"{run_version}_stage3_cp_perturbation_release.xlsx"),
        },
        {
            "Priority": 4,
            "Action": "Review Stage 3.5 QC before public release or sharing.",
            "File": str(review_dir / f"{run_version}_stage3_5_final_qc_report.xlsx"),
        },
        {
            "Priority": 5,
            "Action": "Review Stage 4 deterministic mapping QA.",
            "File": str(review_dir / f"{run_version}_stage4_release_mapping_qa.xlsx"),
        },
        {
            "Priority": 6,
            "Action": "Use the run folder to find all run-versioned artifacts.",
            "File": str(runs_dir),
        },
    ]

    if summary.get("stage1_qa3_mode") == "off":
        rows.append(
            {
                "Priority": 7,
                "Action": "QA3 was off. For production release, rerun with --stage1-qa3-mode smart.",
                "File": "",
            }
        )

    return pd.DataFrame(rows)


def write_final_pipeline_report(cfg, summary: dict) -> Path:
    """
    Write the user-facing final report for one full pipeline run.

    Saved to:
      artifacts/outputs/<run_version>_final_pipeline_report.xlsx

    This report is intentionally high-level. Detailed QC remains in the
    Stage 3.5 and Stage 4 workbooks.
    """
    run_version = cfg.run_version
    outputs_dir = Path(cfg.outputs_dir)
    review_dir = Path(cfg.review_dir)

    report_path = outputs_dir / f"{run_version}_final_pipeline_report.xlsx"

    stage3_5_qc_path = review_dir / f"{run_version}_stage3_5_final_qc_report.xlsx"
    stage4_qa_path = review_dir / f"{run_version}_stage4_release_mapping_qa.xlsx"

    final_qc_summary = _read_xlsx_sheet_if_exists(stage3_5_qc_path, "Final_QC_Summary")
    stage4_summary = _read_xlsx_sheet_if_exists(stage4_qa_path, "summary")

    sheets = {
        "Run_Summary": _summary_dict_to_df(summary),
        "Stage_Timing": _stage_timing_df(summary),
        "Output_Files": build_run_artifact_index_for_report(cfg),
        "Stage1_QA_Summary": _stage1_qa_summary_df(summary),
        "Stage3_5_Final_QC": final_qc_summary,
        "Stage4_QA_Summary": stage4_summary,
        "Recommended_User_Actions": _recommended_user_actions_df(cfg, summary),
    }

    write_dataframes_to_excel(report_path, sheets, format_workbook=True)

    return report_path

def attach_stage0_info_to_sample_rows(df_sample: pd.DataFrame, df_stage0: pd.DataFrame) -> pd.DataFrame:
    """
    Attach GSE_Info and GSM_Info from Stage0 metadata back to sample-level rows.
    Each GSM_ID receives only its own GSM_Info block.
    """
    df_sample = df_sample.copy()

    # GSE_Info: same for all samples in the same GSE
    gse_info_map = (
        df_stage0[["GSE_ID", "GSE_Info"]]
        .drop_duplicates("GSE_ID")
        .set_index("GSE_ID")["GSE_Info"]
        .to_dict()
    )

    # GSM_Info: extract the matching GSM block from each Stage0 chunk
    gsm_info_map = {}

    for _, row in df_stage0.iterrows():
        gsm_info_block = str(row.get("GSM_Info", ""))

        # Split at each GSM block while keeping the GSM ID line
        parts = re.split(r"(?=GSM ID:\s*GSM\d+)", gsm_info_block)

        for part in parts:
            part = part.strip()
            if not part:
                continue

            m = re.search(r"GSM ID:\s*(GSM\d+)", part)
            if not m:
                continue

            gsm_id = m.group(1).strip()
            gsm_info_map[gsm_id] = part

    df_sample["GSE_Info"] = df_sample["GSE_ID"].map(gse_info_map).fillna("")
    df_sample["GSM_Info"] = df_sample["GSM_ID"].map(gsm_info_map).fillna("")

    return df_sample


def set_public_paths(cfg) -> None:
    workdir = Path(cfg.workdir)

    # Stage 2 prompt search directory.
    # Your current repo uses root-level postprocessing/ and inference/.
    if (workdir / "prompts" / "postprocessing").exists():
        cfg.post_prompt_dir = workdir / "prompts" / "postprocessing"
    elif (workdir / "postprocessing").exists() or (workdir / "inference").exists():
        cfg.post_prompt_dir = workdir
    elif (workdir / "Postprocessing_Prompts").exists():
        cfg.post_prompt_dir = workdir / "Postprocessing_Prompts"

    # Stage 3 mapping resources.
    paths = {
        "ctd_csv": workdir / "mappings" / "disease" / "ctd_medic_disease_reference.csv",
        "prior_disease_mapping_xlsx": workdir / "mappings" / "disease" / "disease_mappings.xlsx",
        "prior_tissue_mapping_xlsx": workdir / "mappings" / "tissue" / "tissue_mappings.xlsx",
        "prior_cp_mapping_xlsx": workdir / "mappings" / "compounds" / "compound_pubchem_mappings.xlsx",
        "disease_mapping_prompt_docx": workdir / "prompts" / "mapping" / "disease" / "disease_mapping_prompt.md",
        "tissue_mapping_prompt_docx": workdir / "prompts" / "mapping" / "tissue" / "tissue_mapping_prompt.md",
        "cp_mapping_prompt_docx": workdir / "prompts" / "mapping" / "compounds" / "cp_mapping_prompt.md",
    }

    for attr, path in paths.items():
        if path.exists():
            setattr(cfg, attr, path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run GEOMeta Stage 0 -> Stage 3 from GSE IDs."
    )

    parser.add_argument("--workdir", default=".", help="Project working directory.")
    parser.add_argument("--gse", nargs="*", default=None, help="One or more GSE IDs.")
    parser.add_argument("--gse-file", default=None, help="File containing GSE IDs.")
    parser.add_argument("--run-version", default=None, help="Optional run version.")
    parser.add_argument(
        "--skip-stage2-rerun",
        action="store_true",
        help="Run Stage2 pass1 only and skip selective rerun.",
    )
    parser.add_argument(
        "--skip-stage2-review",
        action="store_true",
        help="Skip Stage2 rule/LLM review and use an empty rerun queue.",
    )
    parser.add_argument(
        "--strict-integrity",
        action="store_true",
        help="Raise an error if GSM identity changes across stages.",
    )
    
    parser.add_argument(
    "--stage1-qa3-mode",
    choices=["off", "smart", "full"],
    default="off",
    help=(
        "Stage1 QA3 mode. "
        "off: skip LLM QA3 evidence verification; recommended default for scalable full runs. "
        "smart: prioritized targeted QA3 audit; recommended for small final audits or targeted QC. "
        "full: broad QA3 audit; use only for small datasets or benchmarking."
        ),
    )

    parser.add_argument(
        "--disable-run-folder",
        action="store_true",
        help="Do not create artifacts/runs/<run_version>/ user-facing output folder.",
    )

    parser.add_argument(
        "--stage1-qa3-build-tasks-only",
        action="store_true",
        help="Build Stage1 QA3 evidence-verification tasks but do not call the LLM reviewer.",
    )
    parser.add_argument(
        "--stage1-qa3-no-apply",
        action="store_true",
        help="Do not apply Stage1 QA3 accepted corrections; save recommendations/review queues only.",
    )
    parser.add_argument(
        "--stage1-qa3-max-tasks",
        type=int,
        default=None,
        help="Maximum Stage1 QA3 tasks for automated Mode A.",
    )

    args = parser.parse_args()
    pipeline_start = time.perf_counter()
    stage_times = {}

    workdir = Path(args.workdir).resolve()
    cfg = default_config(workdir)
    cfg.run_version = args.run_version or make_run_version()

    set_public_paths(cfg)
    cfg.ensure_dirs()

    # Preflight: fail early if LLM credentials/resources are missing.
    cfg.validate_env()
    preflight_path = Path(cfg.ledger_dir) / f"{cfg.run_version}_preflight_summary.json"
    preflight_path.write_text(json.dumps(cfg.preflight_summary(), indent=2), encoding="utf-8")
    print("[SAVED] Preflight summary:", preflight_path)

    duplicated_input_gse_path = None
    input_count_audit_path = None

    if args.gse_file:
        original_gse_file = Path(args.gse_file).resolve()
        gse_ids = read_gse_file(original_gse_file)

        duplicated_input_gse_path = write_duplicated_input_gse_report(
            original_gse_file=original_gse_file,
            out_path=Path(cfg.review_dir) / f"{cfg.run_version}_duplicated_input_gse_ids.xlsx",
        )
        if duplicated_input_gse_path is not None:
            print("[WARNING] Duplicated GSE_ID rows found in input:", duplicated_input_gse_path)

    elif args.gse:
        original_gse_file = None
        gse_ids = clean_gse_ids(args.gse)
    else:
        raise ValueError("Provide either --gse or --gse-file.")

    cfg.gse_list_input = write_gse_input_file(
        gse_ids,
        Path(cfg.outputs_dir) / f"{cfg.run_version}_gse_input.csv",
    )

    print(f"[RUN] workdir={cfg.workdir}")
    print(f"[RUN] run_version={cfg.run_version}")
    print(f"[RUN] GSE count={len(gse_ids)}")
    print("[RUN] stage0_chunking_policy=metadata-token-aware; small GSEs kept together, large GSEs split only as needed")
    print(f"[RUN] stage0_metadata_safe_input_token_limit={getattr(cfg, 'stage0_metadata_safe_input_token_limit', 180000)}")
    print(f"[RUN] stage0_max_gsms_per_chunk={getattr(cfg, 'stage0_max_gsms_per_chunk', 0)} (0 means no fixed GSM-count cap)")
    print("[RUN] stage0_restart_artifact=stage0_input.parquet; Excel is review copy only")
    print(f"[RUN] post_prompt_dir={cfg.post_prompt_dir}")
    print(f"[RUN] llm_api_type={cfg.llm_api_type}")
    print(f"[RUN] llm_model={cfg.llm_model}")
    print(f"[RUN] llm_base_url={cfg.llm_base_url}")
    print(f"[RUN] automated_release_mode={getattr(cfg, 'automated_release_mode', True)}")

    print("\n========== Stage 0 ==========")
    t0 = time.perf_counter()
    df_stage0 = run_stage0_retrieval(cfg)
    stage_times["stage0_seconds"] = round(time.perf_counter() - t0, 2)
    print_stage_time("Stage 0", stage_times["stage0_seconds"])

    print("\n========== Stage 1 ==========")
    print("[Stage1] Starting LLM-guided GEO metadata annotation.")
    print(
        "[Stage1] Behind the scenes: each metadata chunk is sent to four role-specific "
        "annotators: experimental context, biological context, perturbation, and sample metadata."
    )
    print(
        "[Stage1] The role outputs are merged into the canonical 27-field GEOMeta sample-level schema."
    )
    print(
        "[Stage1] Progress is reported by completed metadata chunks, elapsed time, average time/chunk, and ETA."
    )
    print("[Stage1] Main outputs will be saved to artifacts/outputs/ and artifacts/ledgers/.")
    t0 = time.perf_counter()
    reviewer = ReviewerV2()
    df_stage1 = run_stage1_raw_annotation_v2(
        cfg=cfg,
        df_input=df_stage0,
        reviewer=reviewer,
        save_outputs=True,
    )
    # Preserve the original raw Stage 1 annotations before any QA/audit layer.
    # This dataframe is never overwritten and is used in the Stage 1 provenance workbook.
    df_stage1_raw = df_stage1.copy()
    stage1_raw_xlsx = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage1_raw.xlsx"
    stage_times["stage1_seconds"] = round(time.perf_counter() - t0, 2)
    print_stage_time("Stage 1", stage_times["stage1_seconds"])

    stage1_review_path = Path(cfg.review_dir) / f"{cfg.run_version}_stage1_review.xlsx"
    reviewer.to_dataframe().to_excel(stage1_review_path, index=False)

    if original_gse_file is not None:
        input_count_audit_path = (
            Path(cfg.review_dir)
            / f"{cfg.run_version}_input_count_vs_annotated_gsm_audit.xlsx"
        )
        write_input_count_audit(
            original_gse_file=original_gse_file,
            df_stage1=df_stage1,
            out_path=input_count_audit_path,
        )
        print("[SAVED] Input count vs annotated GSM audit:", input_count_audit_path)

    # ------------------------------------------------------------------
    # Mode A Stage 1 QA stack: non-blocking automated release.
    # QA1 high-confidence corrections and QA3 high-confidence missing-cell
    # rescue are applied; ambiguous cases are flagged and carried forward.
    # ------------------------------------------------------------------
    print("\n========== Stage 1 QA1: within-GSE consistency audit ==========")
    print("[Stage1 QA1] Running deterministic within-GSE consistency checks.")
    print("[Stage1 QA1] Safe high-confidence corrections may be applied automatically.")
    print("[Stage1 QA1] Ambiguous inconsistencies are reported but not force-corrected.")
    t0 = time.perf_counter()
    df_stage1_raw_with_info = attach_stage0_info_to_sample_rows(df_stage1_raw, df_stage0)
    # From this point forward, Stage 1 QA operates on the raw annotations plus
    # GSE_Info/GSM_Info context. The raw annotation layer is kept separately.
    df_stage1 = df_stage1_raw_with_info.copy()
    stage1_with_info_xlsx = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage1_raw_with_info.xlsx"
    stage1_with_info_parq = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage1_raw_with_info.parquet"
    write_excel_with_long_text_parts(
        df_stage1_raw_with_info,
        stage1_with_info_xlsx,
        part_limit=int(getattr(cfg, "stage0_excel_text_part_char_limit", 32000)),
    )
    df_stage1_raw_with_info.to_parquet(stage1_with_info_parq, index=False)
    print("[SAVED] Stage1 raw with GSE/GSM info:", stage1_with_info_xlsx)
    print("[SAVED] Stage1 raw with GSE/GSM info Parquet:", stage1_with_info_parq)

    qa1_report = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage1_qa1_consistency_report.xlsx"
    qa1_corrected = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage1_qa1_corrected_high_confidence.xlsx"
    qa1_candidates = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage1_qa1_correction_candidates.xlsx"
    qa1_cfg = AuditConfig(gse_col="GSE_ID", gsm_col="GSM_ID", treat_na_as_missing=True)
    df_stage1_qa1, qa1_summary_df, qa1_candidates_df, qa1_review_df = build_audit_and_corrections(df_stage1, qa1_cfg)
    write_excel(
        corrected_df=df_stage1_qa1,
        summary_df=qa1_summary_df,
        candidates_df=qa1_candidates_df,
        review_queue_df=qa1_review_df,
        output_report=qa1_report,
        output_corrected=qa1_corrected,
        output_candidates=qa1_candidates,
    )
    stage_times["stage1_qa1_seconds"] = round(time.perf_counter() - t0, 2)
    print_stage_time("Stage 1 QA1", stage_times["stage1_qa1_seconds"])
    print("[SAVED] Stage1 QA1 report:", qa1_report)
    print("[SAVED] Stage1 QA1 corrected:", qa1_corrected)

    print("\n========== Stage 1 QA2: cross-agent validation ==========")
    print("[Stage1 QA2] Running cross-agent and cross-field validation.")
    print("[Stage1 QA2] This step identifies suspicious annotations and prepares candidates for targeted QA3.")
    print("[Stage1 QA2] This step is deterministic and does not overwrite Stage 1 values.")
    t0 = time.perf_counter()
    qa2_report = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage1_qa2_cross_agent_validation_report.xlsx"
    qa2_cfg = ValidationConfig(gse_col="GSE_ID", gsm_col="GSM_ID")
    qa2_issues_df = validate_cross_agent(df_stage1_qa1, qa2_cfg)
    write_outputs(df_stage1_qa1, qa2_issues_df, qa2_report)
    stage_times["stage1_qa2_seconds"] = round(time.perf_counter() - t0, 2)
    print_stage_time("Stage 1 QA2", stage_times["stage1_qa2_seconds"])
    print("[SAVED] Stage1 QA2 report:", qa2_report)

    print("\n========== Stage 1 QA3: evidence-grounded verifier / targeted rescue ==========")
    t0 = time.perf_counter()

    qa3_mode = str(args.stage1_qa3_mode).strip().lower()

    if args.stage1_qa3_max_tasks is not None:
        qa3_max_tasks = int(args.stage1_qa3_max_tasks)
    elif qa3_mode == "full":
        qa3_max_tasks = 150
    elif qa3_mode == "off":
        qa3_max_tasks = 0
    else:
        qa3_max_tasks = 50

    print(
        "[Stage1 QA3] Mode="
        f"{qa3_mode}; max_tasks={qa3_max_tasks}; "
        f"min_confidence_to_apply={float(getattr(cfg, 'qa3_min_confidence_to_apply', 0.90)):.2f}; "
        f"apply_accepted={bool(getattr(cfg, 'qa3_auto_apply_high_confidence', True)) and not args.stage1_qa3_no_apply}; "
        f"allow_nonempty_overwrite={bool(getattr(cfg, 'qa3_allow_nonempty_overwrite', False))}."
    )

    if qa3_mode == "off":
        print("[Stage1 QA3] Skipped because --stage1-qa3-mode off was selected.")
        print("[Stage1 QA3] Using Stage1 QA1 corrected output as Stage1 final input for Stage2.")
        df_stage1_qa3 = df_stage1_qa1.copy()
        qa3_outputs = {}
    else:
        print("[Stage1 QA3] Candidate issues from QA1/QA2 are checked against GSE/GSM evidence.")
        print("[Stage1 QA3] Only high-confidence evidence-backed recommendations are applied automatically.")
        print("[Stage1 QA3] Ambiguous or unsupported recommendations are routed to the human review queue.")
        
        qa3_cfg = EvidenceVerifierConfig(
            gse_col="GSE_ID",
            gsm_col="GSM_ID",
            qa3_mode=qa3_mode,
            max_tasks=qa3_max_tasks,
            min_confidence_to_apply=float(getattr(cfg, "qa3_min_confidence_to_apply", 0.90)),
            build_tasks_only=bool(args.stage1_qa3_build_tasks_only or getattr(cfg, "qa3_build_tasks_only", False)),
            apply_accepted=bool(getattr(cfg, "qa3_auto_apply_high_confidence", True)) and not args.stage1_qa3_no_apply,
            allow_nonempty_overwrite=bool(getattr(cfg, "qa3_allow_nonempty_overwrite", False)),
            include_sampling_qc=True if qa3_mode == "full" else False,
        )

        df_stage1_qa3, qa3_outputs = run_stage1_qa3_verification_pipeline(
            df_stage1=df_stage1_qa1,
            stage1_qa1_report=qa1_report,
            stage1_qa2_report=qa2_report,
            output_dir=Path(cfg.outputs_dir),
            run_version=cfg.run_version,
            verifier_config=qa3_cfg,
            cfg_pipeline=cfg,
        )

    # Explicit final Stage 1 layer used by Stage 2. Do not overwrite raw/QA files.
    df_stage1_final_for_stage2 = df_stage1_qa3.copy()
    df_stage1 = df_stage1_final_for_stage2
    stage1_final_for_stage2_xlsx = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage1_final_for_stage2.xlsx"
    stage1_final_for_stage2_parq = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage1_final_for_stage2.parquet"
    write_excel_with_long_text_parts(
        df_stage1_final_for_stage2,
        stage1_final_for_stage2_xlsx,
        part_limit=int(getattr(cfg, "stage0_excel_text_part_char_limit", 32000)),
    )
    df_stage1_final_for_stage2.to_parquet(stage1_final_for_stage2_parq, index=False)

    stage1_provenance_path = Path(cfg.review_dir) / f"{cfg.run_version}_stage1_provenance_audit.xlsx"
    stage1_provenance_path = write_stage1_provenance_workbook(
        output_path=stage1_provenance_path,
        run_version=cfg.run_version,
        stage1_raw=df_stage1_raw,
        stage1_raw_with_info=df_stage1_raw_with_info,
        stage1_qa1_corrected=df_stage1_qa1,
        stage1_qa3_corrected=df_stage1_qa3,
        stage1_final_for_stage2=df_stage1_final_for_stage2,
        qa1_summary_df=qa1_summary_df,
        qa1_candidates_df=qa1_candidates_df,
        qa1_review_df=qa1_review_df,
        qa2_issues_df=qa2_issues_df,
        qa3_outputs=qa3_outputs,
        file_manifest={
            "stage1_raw": stage1_raw_xlsx,
            "stage1_raw_with_info": stage1_with_info_xlsx,
            "stage1_raw_with_info_parquet": stage1_with_info_parq,
            "stage1_qa1_report": qa1_report,
            "stage1_qa1_corrected": qa1_corrected,
            "stage1_qa1_candidates": qa1_candidates,
            "stage1_qa2_report": qa2_report,
            "stage1_qa3_corrected": qa3_outputs.get("corrected", ""),
            "stage1_final_for_stage2": stage1_final_for_stage2_xlsx,
            "stage1_final_for_stage2_parquet": stage1_final_for_stage2_parq,
        },
        gse_col="GSE_ID",
        gsm_col="GSM_ID",
        part_limit=int(getattr(cfg, "stage0_excel_text_part_char_limit", 32000)),
        max_rows_per_sheet=int(getattr(cfg, "stage1_provenance_max_rows_per_sheet", 1_048_575)),
    )

    stage_times["stage1_qa3_seconds"] = round(time.perf_counter() - t0, 2)
    print_stage_time("Stage 1 QA3", stage_times["stage1_qa3_seconds"])
    if qa3_mode != "off":
        print("[SAVED] Stage1 QA3 corrected:", qa3_outputs.get("corrected"))
        print("[SAVED] Stage1 QA3 human/review queue:", qa3_outputs.get("human_review"))
    else:
        print("[Stage1 QA3] No QA3 correction/review files generated because QA3 is off.")

    print("[SAVED] Stage1 final for Stage2:", stage1_final_for_stage2_xlsx)
    print("[SAVED] Stage1 provenance audit workbook:", stage1_provenance_path)

    print("\n========== Stage 2 ==========")
    t0 = time.perf_counter()
    df_stage2_pass1 = run_stage2_postprocessing(cfg, df_stage1)

    # Keep these path variables for summary/reporting, but do not write duplicate aliases.
    stage2_pass1_xlsx = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage2_post.xlsx"
    stage2_pass1_parq = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage2_post.parquet"

    print("[INFO] Stage2 pass1 Excel:", stage2_pass1_xlsx)
    print("[INFO] Stage2 pass1 Parquet:", stage2_pass1_parq)

    if args.skip_stage2_review:
        rule_review_df = pd.DataFrame()
        llm_row_review_df = pd.DataFrame()
        llm_gse_review_df = pd.DataFrame()
        rerun_queue_df = pd.DataFrame()
        print("[Stage2 REVIEW] Skipped; using empty reannotation queue.")
    else:
        reviewer2 = ReviewerV2()
        reviewer2.review_stage2_rules(df_stage2_pass1)
        reviewer2.review_within_gse(df_stage2_pass1)
        rule_review_df = reviewer2.to_dataframe()

        stage2_rule_review_path = Path(cfg.review_dir) / f"{cfg.run_version}_stage2_rule_review.xlsx"
        rule_review_df.to_excel(stage2_rule_review_path, index=False)
        print("[SAVED] Stage2 rule review:", stage2_rule_review_path)

        llm_reviewer = ReviewerLLMV2(
            cfg=cfg,
            debug_dir=Path(cfg.debug_dir) / "reviewer",
            llm_review_cfg=LLMReviewConfig(
                max_row_reviews_per_run=int(cfg.max_row_reviews_per_run),
                max_gse_reviews_per_run=int(cfg.max_gse_reviews_per_run),
                row_fields_focus=[
                    "Disease", "Tissue", "Pert", "Pert_Type",
                    "Sex", "Age", "Model_Type", "SampleType", "Specimen_Type",
                ],
            ),
        )

        flagged_rows_df = reviewer2.get_flagged_rows_for_llm()

        llm_row_review_df = llm_reviewer.review_rows(
            df_stage2=df_stage2_pass1,
            df_input_stage1_source=df_stage1,
            flagged_rows_df=flagged_rows_df,
        )
        stage2_llm_row_review_path = Path(cfg.review_dir) / f"{cfg.run_version}_stage2_llm_row_review.xlsx"
        llm_row_review_df.to_excel(stage2_llm_row_review_path, index=False)
        print("[SAVED] Stage2 LLM row review:", stage2_llm_row_review_path)

        llm_gse_review_df = llm_reviewer.review_gses(
            df_stage2=df_stage2_pass1,
            df_input_stage1_source=df_stage1,
            flagged_rows_df=flagged_rows_df,
        )
        stage2_llm_gse_review_path = Path(cfg.review_dir) / f"{cfg.run_version}_stage2_llm_gse_review.xlsx"
        llm_gse_review_df.to_excel(stage2_llm_gse_review_path, index=False)
        print("[SAVED] Stage2 LLM GSE review:", stage2_llm_gse_review_path)

        rerun_queue_df = reviewer2.build_reannotation_queue(
            rule_review_df=rule_review_df,
            llm_row_review_df=llm_row_review_df,
            llm_gse_review_df=llm_gse_review_df,
        )
        stage2_reannotation_queue_path = Path(cfg.review_dir) / f"{cfg.run_version}_stage2_reannotation_queue.xlsx"
        rerun_queue_df.to_excel(stage2_reannotation_queue_path, index=False)
        print("[SAVED] Stage2 reannotation queue:", stage2_reannotation_queue_path)

    if args.skip_stage2_rerun:
        df_stage2_final = df_stage2_pass1.copy()
        print("[Stage2 RERUN] Skipped; using Stage2 pass1 as final.")
    else:
        df_stage2_final = run_stage2_postprocessing_v2(
            cfg=cfg,
            df_stage1=df_stage1,
            df_queue=rerun_queue_df,
            run_pass1=False,
            df_stage2_pass1=df_stage2_pass1,
         )

    stage_times["stage2_seconds"] = round(time.perf_counter() - t0, 2)
    print_stage_time("Stage 2", stage_times["stage2_seconds"])

    # Save explicit Stage2 final aliases before Stage3.
    stage2_final_xlsx = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage2_post_final.xlsx"
    stage2_final_parq = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage2_post_final.parquet"
    df_stage2_final.to_excel(stage2_final_xlsx, index=False)
    df_stage2_final.to_parquet(stage2_final_parq, index=False)
    print("[SAVED] Stage2 final Excel:", stage2_final_xlsx)
    print("[SAVED] Stage2 final Parquet:", stage2_final_parq)

    stage2_change_audit_path = write_stage2_change_audit(cfg, df_stage2_pass1, df_stage2_final)
    print("[SAVED] Stage2 pass1-to-final change audit:", stage2_change_audit_path)

    # Attach Stage0 GSE/GSM metadata before Stage3 export.
    df_stage2_final = attach_stage0_info_to_sample_rows(df_stage2_final, df_stage0)

    print("\n========== Stage 3 ==========")
    t0 = time.perf_counter()
    df_stage3 = run_stage3_mapping(cfg, df_stage2_final)
    stage_times["stage3_seconds"] = round(time.perf_counter() - t0, 2)
    print_stage_time("Stage 3", stage_times["stage3_seconds"])

    # Additional audit files after all stages are available.
    stage0_to_stage1_audit_path = write_stage0_chunk_to_stage1_audit(cfg, df_stage0, df_stage1)
    transition_audit_xlsx, transition_audit_json = write_stage_transition_audit(
        cfg, df_stage0, df_stage1, df_stage2_pass1, df_stage2_final, df_stage3
    )
    completeness_stage1_path = write_stage_completeness_audit(cfg, "stage1", df_stage1)
    completeness_stage2_path = write_stage_completeness_audit(cfg, "stage2_final", df_stage2_final)
    completeness_stage3_path = write_stage_completeness_audit(cfg, "stage3", df_stage3)

    transition_summary = json.loads(transition_audit_json.read_text(encoding="utf-8"))
    if args.strict_integrity and transition_summary.get("status") != "pass":
        raise AssertionError(
            f"GSM identity audit failed. See: {transition_audit_xlsx}"
        )

    final_xlsx = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage3_mapped.xlsx"
    artifact_manifest_path = write_run_manifest(cfg)

    total_seconds = round(time.perf_counter() - pipeline_start, 2)
    
    def format_stage_times(stage_times: dict) -> dict:
        out = {}
        for k, v in stage_times.items():
            stage = k.replace("_seconds", "")
            seconds = float(v)
            minutes = seconds / 60
            out[stage] = f"{seconds:.2f} sec ({minutes:.2f} min)"
        return out

    stage_times_display = format_stage_times(stage_times)

    summary = {
        "run_version": cfg.run_version,
        "gse_count": len(gse_ids),
        "stage0_rows": int(df_stage0.shape[0]),
        "stage1_rows": int(df_stage1.shape[0]),
        "stage2_pass1_rows": int(df_stage2_pass1.shape[0]),
        "stage2_rows": int(df_stage2_final.shape[0]),
        "stage3_rows": int(df_stage3.shape[0]),
        "stage1_unique_gsm": int(df_stage1["GSM_ID"].astype(str).nunique()) if "GSM_ID" in df_stage1.columns else 0,
        "stage2_pass1_unique_gsm": int(df_stage2_pass1["GSM_ID"].astype(str).nunique()) if "GSM_ID" in df_stage2_pass1.columns else 0,
        "stage2_unique_gsm": int(df_stage2_final["GSM_ID"].astype(str).nunique()) if "GSM_ID" in df_stage2_final.columns else 0,
        "stage3_unique_gsm": int(df_stage3["GSM_ID"].astype(str).nunique()) if "GSM_ID" in df_stage3.columns else 0,
        "stage1_dup_gsm": int(df_stage1["GSM_ID"].astype(str).duplicated().sum()) if "GSM_ID" in df_stage1.columns else 0,
        "stage2_dup_gsm": int(df_stage2_final["GSM_ID"].astype(str).duplicated().sum()) if "GSM_ID" in df_stage2_final.columns else 0,
        "stage3_dup_gsm": int(df_stage3["GSM_ID"].astype(str).duplicated().sum()) if "GSM_ID" in df_stage3.columns else 0,
        "stage2_rule_review_rows": int(rule_review_df.shape[0]),
        "stage2_llm_row_review_rows": int(llm_row_review_df.shape[0]),
        "stage2_llm_gse_review_rows": int(llm_gse_review_df.shape[0]),
        "stage2_reannotation_queue_rows": int(rerun_queue_df.shape[0]),
        "stage1_qa1_report_xlsx": str(qa1_report),
        "stage1_qa1_corrected_xlsx": str(qa1_corrected),
        "stage1_qa2_report_xlsx": str(qa2_report),
        "stage1_qa3_mode": qa3_mode,
        "stage1_qa3_max_tasks": qa3_max_tasks,
        "stage1_qa3_outputs": {k: str(v) for k, v in qa3_outputs.items()},
        "stage1_raw_xlsx": str(stage1_raw_xlsx),
        "stage1_raw_with_info_xlsx": str(stage1_with_info_xlsx),
        "stage1_raw_with_info_parquet": str(stage1_with_info_parq),
        "stage1_final_for_stage2_xlsx": str(stage1_final_for_stage2_xlsx),
        "stage1_final_for_stage2_parquet": str(stage1_final_for_stage2_parq),
        "stage1_provenance_audit_xlsx": str(stage1_provenance_path),
        "stage1_qa1_review_queue_rows": int(qa1_review_df.shape[0]),
        "stage1_qa2_issue_rows": int(qa2_issues_df.shape[0]),
        "stage_transition_audit_status": transition_summary.get("status"),
        "runtime_seconds": total_seconds,
        "runtime_minutes": round(total_seconds / 60, 2),
        "stage_times": stage_times_display,
        "stage_times_seconds": stage_times,
        "final_output": str(final_xlsx),
        "preflight_summary": str(preflight_path),
        "stage2_pass1_xlsx": str(stage2_pass1_xlsx),
        "stage2_final_xlsx": str(stage2_final_xlsx),
        "stage2_change_audit": str(stage2_change_audit_path),
        "stage0_chunk_to_stage1_audit": str(stage0_to_stage1_audit_path),
        "stage_transition_gsm_audit_xlsx": str(transition_audit_xlsx),
        "stage_transition_gsm_audit_json": str(transition_audit_json),
        "stage1_completeness_audit": str(completeness_stage1_path),
        "stage2_completeness_audit": str(completeness_stage2_path),
        "stage3_completeness_audit": str(completeness_stage3_path),
        "artifact_manifest": str(artifact_manifest_path),
    }

    if duplicated_input_gse_path is not None:
        summary["duplicated_input_gse_report"] = str(duplicated_input_gse_path)
    if input_count_audit_path is not None:
        summary["input_count_vs_annotated_gsm_audit"] = str(input_count_audit_path)
    if not args.skip_stage2_review:
        summary["stage2_rule_review_xlsx"] = str(stage2_rule_review_path)
        summary["stage2_llm_row_review_xlsx"] = str(stage2_llm_row_review_path)
        summary["stage2_llm_gse_review_xlsx"] = str(stage2_llm_gse_review_path)
        summary["stage2_reannotation_queue_xlsx"] = str(stage2_reannotation_queue_path)

    # Explicit warning flags, so downstream scripts can check without parsing text logs.
    if summary["stage2_pass1_rows"] != summary["stage1_rows"]:
        summary["warning_stage2_pass1_row_mismatch"] = True
    if summary["stage2_rows"] != summary["stage1_rows"]:
        summary["warning_stage2_final_row_mismatch"] = True
    if summary["stage3_rows"] != summary["stage2_rows"]:
        summary["warning_stage3_row_mismatch"] = True
    if transition_summary.get("status") != "pass":
        summary["warning_stage_transition_gsm_identity_mismatch"] = True

    summary_path = Path(cfg.ledger_dir) / f"{cfg.run_version}_full_pipeline_summary.json"
    
    final_pipeline_report_path = Path(cfg.outputs_dir) / f"{cfg.run_version}_final_pipeline_report.xlsx"

    summary["full_pipeline_summary_json"] = str(summary_path)
    summary["final_pipeline_report_xlsx"] = str(final_pipeline_report_path)

    # Save once before building the final report so the summary JSON exists
    # and can be indexed as a run artifact.
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    final_pipeline_report_path = write_final_pipeline_report(cfg, summary)
    summary["final_pipeline_report_xlsx"] = str(final_pipeline_report_path)
    print("[SAVED] Final pipeline report:", final_pipeline_report_path)

    # Save again after final report generation.
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if not args.disable_run_folder:
        run_folder = write_run_folder_index(cfg)
        summary["run_folder"] = str(run_folder)
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print("[SAVED] User-facing run folder:", run_folder)
        print("[SAVED] Run output index:", run_folder / "run_output_index.xlsx")

    print("\n========== DONE ==========")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()