from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from geo_annotation_agent.config import default_config
from geo_annotation_agent.stage3_map import run_stage3_mapping


def make_run_version(prefix: str = "gaa_stage3") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def infer_run_version_from_stage2(stage2_path: Path) -> str:
    stem = stage2_path.stem

    suffixes = [
        "_stage2_post_final",
        "_stage2_post",
        "_stage2_pass1",
    ]
    for suf in suffixes:
        if stem.endswith(suf):
            return stem[: -len(suf)]

    return make_run_version("gaa_stage3")


def attach_stage0_info_to_sample_rows(df_sample: pd.DataFrame, df_stage0: pd.DataFrame) -> pd.DataFrame:
    """Attach full GSE_Info and GSM-specific GSM_Info from Stage0 metadata.

    This mirrors the full-pipeline behavior so standalone Stage 3 reruns do not
    lose GSE_Info/GSM_Info columns when starting from stage2_post_final.xlsx.
    """
    df_sample = df_sample.copy()

    if df_stage0 is None or df_stage0.empty:
        return df_sample

    if {"GSE_ID", "GSE_Info"}.issubset(df_stage0.columns):
        gse_info_map = (
            df_stage0[["GSE_ID", "GSE_Info"]]
            .drop_duplicates("GSE_ID")
            .set_index("GSE_ID")["GSE_Info"]
            .to_dict()
        )
        new_gse_info = df_sample["GSE_ID"].map(gse_info_map).fillna("")
        if "GSE_Info" not in df_sample.columns:
            df_sample["GSE_Info"] = new_gse_info
        else:
            current = df_sample["GSE_Info"].fillna("").astype(str).str.strip()
            df_sample.loc[current.eq("") | current.str.lower().isin({"nan", "none", "na", "unknown"}), "GSE_Info"] = new_gse_info

    if "GSM_Info" in df_stage0.columns:
        gsm_info_map = {}
        for _, row in df_stage0.iterrows():
            gsm_info_block = str(row.get("GSM_Info", ""))
            parts = re.split(r"(?=GSM ID:\s*GSM\d+)", gsm_info_block)
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                m = re.search(r"GSM ID:\s*(GSM\d+)", part)
                if m:
                    gsm_info_map[m.group(1).strip()] = part

        new_gsm_info = df_sample["GSM_ID"].map(gsm_info_map).fillna("")
        if "GSM_Info" not in df_sample.columns:
            df_sample["GSM_Info"] = new_gsm_info
        else:
            current = df_sample["GSM_Info"].fillna("").astype(str).str.strip()
            df_sample.loc[current.eq("") | current.str.lower().isin({"nan", "none", "na", "unknown"}), "GSM_Info"] = new_gsm_info

    return df_sample


def _missing_like_series(s: pd.Series) -> pd.Series:
    vals = s.fillna("").astype(str).str.strip().str.lower()
    return vals.eq("") | vals.isin({"nan", "none", "na", "unknown"})


def _read_table_auto(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, engine="openpyxl")
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="	")
    raise ValueError(f"Unsupported metadata fallback file type: {path}")


def _find_run_artifact(outputs_dir: Path, run_version: str, suffix: str) -> Path | None:
    """Find a run artifact in outputs_dir or nested subfolders.

    This helps when test outputs were moved into subfolders such as
    artifacts/outputs/0614 test runs/.
    """
    direct = outputs_dir / f"{run_version}_{suffix}"
    if direct.exists():
        return direct

    hits = sorted(
        outputs_dir.rglob(f"{run_version}_{suffix}"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )
    return hits[0] if hits else None


def _attach_sample_metadata_by_gsm(df_stage2: pd.DataFrame, df_meta: pd.DataFrame, source_path: Path) -> pd.DataFrame:
    """Attach GSE_Info/GSM_Info from a sample-level Stage1 metadata table."""
    needed = {"GSM_ID", "GSE_Info", "GSM_Info"}
    if not needed.issubset(df_meta.columns):
        return df_stage2

    out = df_stage2.copy()
    meta = df_meta[["GSM_ID", "GSE_Info", "GSM_Info"]].copy()
    meta["GSM_ID"] = meta["GSM_ID"].astype(str).str.strip()
    meta = meta.drop_duplicates("GSM_ID")

    out["GSM_ID"] = out["GSM_ID"].astype(str).str.strip()

    # Preserve existing non-empty metadata if already present.
    for c in ["GSE_Info", "GSM_Info"]:
        if c not in out.columns:
            out[c] = ""
        else:
            out[c] = out[c].fillna("").astype(str)

    merged = out.merge(meta, on="GSM_ID", how="left", suffixes=("", "_from_meta"))

    for c in ["GSE_Info", "GSM_Info"]:
        current_missing = _missing_like_series(merged[c])
        merged.loc[current_missing, c] = merged.loc[current_missing, f"{c}_from_meta"].fillna("")
        merged = merged.drop(columns=[f"{c}_from_meta"])

    print("[INFO] Attached GSE_Info/GSM_Info from fallback metadata:", source_path)
    return merged


def maybe_attach_stage0_metadata(cfg, df_stage2: pd.DataFrame) -> pd.DataFrame:
    """Attach GSE_Info/GSM_Info for standalone Stage 3 reruns.

    Preferred:
      1. Stage0 parquet, because it is the full-fidelity metadata artifact.

    Fallback:
      2. Recursively search artifacts/outputs for the Stage0 parquet.
      3. Stage1 raw-with-info parquet/xlsx.
      4. Stage1 final-for-Stage2 parquet/xlsx, if it contains metadata.

    Stage 3 can run without metadata, but final files will have blank GSE_Info/GSM_Info.
    """
    outputs_dir = Path(cfg.outputs_dir)

    # If Stage2 already has non-empty metadata, do nothing.
    has_gse_info = "GSE_Info" in df_stage2.columns and (~_missing_like_series(df_stage2["GSE_Info"])).any()
    has_gsm_info = "GSM_Info" in df_stage2.columns and (~_missing_like_series(df_stage2["GSM_Info"])).any()
    if has_gse_info and has_gsm_info:
        print("[INFO] Stage2 input already contains non-empty GSE_Info/GSM_Info.")
        return df_stage2

    stage0_fp = _find_run_artifact(outputs_dir, cfg.run_version, "stage0_input.parquet")
    if stage0_fp is not None and stage0_fp.exists():
        df_stage0 = pd.read_parquet(stage0_fp)
        df_stage2 = attach_stage0_info_to_sample_rows(df_stage2, df_stage0)
        print("[INFO] Attached Stage0 GSE_Info/GSM_Info from:", stage0_fp)
        return df_stage2

    fallback_suffixes = [
        "stage1_raw_with_info.parquet",
        "stage1_raw_with_info.xlsx",
        "stage1_final_for_stage2.parquet",
        "stage1_final_for_stage2.xlsx",
    ]

    for suffix in fallback_suffixes:
        fp = _find_run_artifact(outputs_dir, cfg.run_version, suffix)
        if fp is None or not fp.exists():
            continue
        try:
            df_meta = _read_table_auto(fp)
        except Exception as e:
            print(f"[WARN] Could not read fallback metadata file {fp}: {e}")
            continue

        if {"GSM_ID", "GSE_Info", "GSM_Info"}.issubset(df_meta.columns):
            return _attach_sample_metadata_by_gsm(df_stage2, df_meta, fp)

    print("[WARN] No Stage0/Stage1 metadata artifact found; GSE_Info/GSM_Info will be blank in standalone Stage3 outputs.")
    print("[WARN] Expected primary artifact:", outputs_dir / f"{cfg.run_version}_stage0_input.parquet")
    return df_stage2


def main():
    ap = argparse.ArgumentParser(
        description="Run Stage 3 independently on a Stage2 final Excel file."
    )
    ap.add_argument(
        "--workdir",
        default=".",
        help="Project working directory. Defaults to current directory.",
    )
    ap.add_argument(
        "--stage2",
        required=True,
        help="Path to Stage2 final Excel file.",
    )
    ap.add_argument(
        "--run-version",
        default=None,
        help="Optional run version override.",
    )
    args = ap.parse_args()

    workdir = Path(args.workdir).resolve()
    cfg = default_config(workdir)

    stage2_path = Path(args.stage2).resolve()
    if not stage2_path.exists():
        raise FileNotFoundError(f"Stage2 input file not found: {stage2_path}")

    if args.run_version:
        cfg.run_version = args.run_version
    else:
        cfg.run_version = infer_run_version_from_stage2(stage2_path)

    cfg.ensure_dirs()
    cfg.validate_paths()

    print(f"[RUN] workdir={cfg.workdir}")
    print(f"[RUN] run_version={cfg.run_version}")
    print(f"[RUN] stage2={stage2_path}")
    print(f"[RUN] llm_api_type={cfg.llm_api_type}")
    print(f"[RUN] llm_model={cfg.llm_model}")
    print(f"[RUN] llm_base_url={cfg.llm_base_url}")

    df_stage2 = pd.read_excel(stage2_path, engine="openpyxl")
    df_stage2 = maybe_attach_stage0_metadata(cfg, df_stage2)

    required_cols = {"GSM_ID", "GSE_ID", "Disease_Post", "Tissue_Post", "Pert_Type", "Pert_Post"}
    missing = required_cols - set(df_stage2.columns)
    if missing:
        raise ValueError(
            f"Stage2 input file is missing required columns: {sorted(missing)}\n"
            f"Input file: {stage2_path}"
        )

    t0 = time.perf_counter()
    df_stage3 = run_stage3_mapping(cfg, df_stage2)
    stage3_seconds = round(time.perf_counter() - t0, 2)
    print(f"[TIME] Stage 3: {stage3_seconds:.2f} sec ({stage3_seconds / 60:.2f} min)")

    out_xlsx = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage3_mapped.xlsx"

    result = {
        "run_version": cfg.run_version,
        "stage2_input_file": str(stage2_path),
        "stage2_input_rows": int(df_stage2.shape[0]),
        "stage2_unique_gsm": int(df_stage2["GSM_ID"].astype(str).nunique()),
        "stage2_dup_gsm": int(df_stage2["GSM_ID"].astype(str).duplicated().sum()),
        "stage3_rows": int(df_stage3.shape[0]),
        "stage3_unique_gsm": int(df_stage3["GSM_ID"].astype(str).nunique()) if "GSM_ID" in df_stage3.columns else 0,
        "stage3_dup_gsm": int(df_stage3["GSM_ID"].astype(str).duplicated().sum()) if "GSM_ID" in df_stage3.columns else 0,
        "stage3_output_file": str(out_xlsx),
        "stage3_seconds": stage3_seconds,
        "stage3_minutes": round(stage3_seconds / 60, 2),
    }

    if result["stage3_rows"] != result["stage2_input_rows"]:
        result["warning_stage3_row_mismatch"] = True

    if result["stage3_unique_gsm"] != result["stage2_unique_gsm"]:
        result["warning_stage3_unique_gsm_mismatch"] = True

    summary_path = Path(cfg.ledger_dir) / f"{cfg.run_version}_run_stage3_result.json"
    summary_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("[SAVED] Stage3 mapped Excel:", out_xlsx)
    print("[SAVED] Stage3 summary:", summary_path)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()