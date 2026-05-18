from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from geo_annotation_agent.config import default_config
from geo_annotation_agent.reviewer import ReviewerV2
from geo_annotation_agent.stage1_annotate import run_stage1_raw_annotation_v2


def make_run_version(prefix: str = "gaa_stage1") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def main():
    ap = argparse.ArgumentParser(
        description="Run Stage 1 independently on a Stage1-style input table (including Stage0 output tables)."
    )
    ap.add_argument(
        "--workdir",
        default=".",
        help="Project working directory. Defaults to current directory.",
    )
    ap.add_argument(
        "--input",
        default=None,
        help=(
            "Optional input Excel override. "
            "If omitted, config.input_xlsx is used. "
            "This can be either a manually prepared Stage1-style input table "
            "or a Stage0 output file."
        ),
    )
    ap.add_argument(
        "--run-version",
        default=None,
        help="Optional run version override.",
    )
    args = ap.parse_args()

    workdir = Path(args.workdir).resolve()
    cfg = default_config(workdir)

    if args.run_version:
        cfg.run_version = args.run_version
    else:
        cfg.run_version = make_run_version("gaa_stage1")

    if args.input:
        cfg.input_xlsx = Path(args.input).resolve()

    cfg.ensure_dirs()
    cfg.validate_paths(
    require_input_xlsx=True,
    require_stage3_resources=False,
    require_prompts=False,
)

    print(f"[RUN] workdir={cfg.workdir}")
    print(f"[RUN] run_version={cfg.run_version}")
    print(f"[RUN] input_xlsx={cfg.input_xlsx}")

    df_input = pd.read_excel(cfg.input_xlsx, engine="openpyxl")

    required_cols = {"GSE_ID", "GSE_Info", "GSM_Info", "GSM_Counts"}
    missing = required_cols - set(df_input.columns)
    if missing:
        raise ValueError(
            f"Stage1 input file is missing required columns: {sorted(missing)}\n"
            f"Input file: {cfg.input_xlsx}"
        )

    reviewer = ReviewerV2()

    df_stage1 = run_stage1_raw_annotation_v2(
        cfg=cfg,
        df_input=df_input,
        reviewer=reviewer,
        save_outputs=True,
    )

    review_df = reviewer.to_dataframe()
    review_path = Path(cfg.review_dir) / f"{cfg.run_version}_stage1_review.xlsx"
    review_df.to_excel(review_path, index=False)

    result = {
        "run_version": cfg.run_version,
        "input_file": str(cfg.input_xlsx),
        "input_rows": int(df_input.shape[0]),
        "stage1_rows": int(df_stage1.shape[0]),
        "stage1_unique_gsm": int(df_stage1["GSM_ID"].astype(str).nunique()) if "GSM_ID" in df_stage1.columns else 0,
        "stage1_dup_gsm": int(df_stage1["GSM_ID"].astype(str).duplicated().sum()) if "GSM_ID" in df_stage1.columns else 0,
        "review_rows": int(review_df.shape[0]),
        "stage1_output_file": str(Path(cfg.outputs_dir) / f"{cfg.run_version}_stage1_raw.xlsx"),
        "stage1_jsonl_file": str(Path(cfg.outputs_dir) / f"{cfg.run_version}_stage1_rows.jsonl"),
        "stage1_review_file": str(review_path),
    }

    summary_path = Path(cfg.ledger_dir) / f"{cfg.run_version}_run_stage1_result.json"
    summary_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("[SAVED] Stage1 review:", review_path)
    print("[SAVED] Stage1 summary:", summary_path)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()