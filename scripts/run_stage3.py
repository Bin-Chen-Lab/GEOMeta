from __future__ import annotations

import argparse
import json
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

    required_cols = {"GSM_ID", "GSE_ID", "Disease_Post", "Tissue_Post", "Pert_Type", "Pert_Post"}
    missing = required_cols - set(df_stage2.columns)
    if missing:
        raise ValueError(
            f"Stage2 input file is missing required columns: {sorted(missing)}\n"
            f"Input file: {stage2_path}"
        )

    df_stage3 = run_stage3_mapping(cfg, df_stage2)

    out_xlsx = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage3_mapped.xlsx"
    df_stage3.to_excel(out_xlsx, index=False)

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