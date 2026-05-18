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
from geo_annotation_agent.stage0_retrieve import run_stage0_retrieval
from geo_annotation_agent.stage1_annotate import run_stage1_raw_annotation_v2
from geo_annotation_agent.stage2_postprocess import (
    run_stage2_postprocessing,
    run_stage2_postprocessing_v2,
)
from geo_annotation_agent.stage3_map import run_stage3_mapping


def make_run_version(prefix: str = "geometa_full") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


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

    pd.DataFrame({"GSE_ID": clean_ids}).to_excel(out_path, index=False)
    return out_path


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

    args = parser.parse_args()
    pipeline_start = time.perf_counter()
    stage_times = {}

    workdir = Path(args.workdir).resolve()
    cfg = default_config(workdir)
    cfg.run_version = args.run_version or make_run_version()

    set_public_paths(cfg)
    cfg.ensure_dirs()

    if args.gse_file:
        gse_ids = read_gse_file(Path(args.gse_file).resolve())
    elif args.gse:
        gse_ids = clean_gse_ids(args.gse)
    else:
        raise ValueError("Provide either --gse or --gse-file.")

    cfg.gse_list_input = write_gse_input_file(
        gse_ids,
        Path(cfg.outputs_dir) / f"{cfg.run_version}_gse_input.xlsx",
    )

    print(f"[RUN] workdir={cfg.workdir}")
    print(f"[RUN] run_version={cfg.run_version}")
    print(f"[RUN] GSE count={len(gse_ids)}")
    print(f"[RUN] stage0_chunk_size={cfg.stage0_chunk_size}")
    print(f"[RUN] post_prompt_dir={cfg.post_prompt_dir}")

    print("\n========== Stage 0 ==========")
    t0 = time.perf_counter()
    df_stage0 = run_stage0_retrieval(cfg)
    stage_times["stage0_seconds"] = round(time.perf_counter() - t0, 2)

    print("\n========== Stage 1 ==========")
    t0 = time.perf_counter()
    reviewer = ReviewerV2()
    df_stage1 = run_stage1_raw_annotation_v2(
        cfg=cfg,
        df_input=df_stage0,
        reviewer=reviewer,
        save_outputs=True,
    )
    stage_times["stage1_seconds"] = round(time.perf_counter() - t0, 2)

    stage1_review_path = Path(cfg.review_dir) / f"{cfg.run_version}_stage1_review.xlsx"
    reviewer.to_dataframe().to_excel(stage1_review_path, index=False)

    print("\n========== Stage 2 ==========")
    t0 = time.perf_counter()
    df_stage2_pass1 = run_stage2_postprocessing(cfg, df_stage1)

    if args.skip_stage2_rerun:
        df_stage2_final = df_stage2_pass1.copy()
    else:
        df_stage2_final = run_stage2_postprocessing_v2(
            cfg=cfg,
            df_stage1=df_stage1,
            df_queue=pd.DataFrame(),
            run_pass1=False,
            df_stage2_pass1=df_stage2_pass1,
         )

    stage_times["stage2_seconds"] = round(time.perf_counter() - t0, 2)

    # Attach Stage0 GSE/GSM metadata before Stage3 export
    df_stage2_final = attach_stage0_info_to_sample_rows(df_stage2_final, df_stage0)
    

    print("\n========== Stage 3 ==========")
    t0 = time.perf_counter()
    df_stage3 = run_stage3_mapping(cfg, df_stage2_final)
    stage_times["stage3_seconds"] = round(time.perf_counter() - t0, 2)

    final_xlsx = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage3_mapped.xlsx"

    total_seconds = round(time.perf_counter() - pipeline_start, 2)

    summary = {
    "run_version": cfg.run_version,
    "gse_count": len(gse_ids),
    "stage0_rows": int(df_stage0.shape[0]),
    "stage1_rows": int(df_stage1.shape[0]),
    "stage2_rows": int(df_stage2_final.shape[0]),
    "stage3_rows": int(df_stage3.shape[0]),
    "runtime_seconds": total_seconds,
    "runtime_minutes": round(total_seconds / 60, 2),
    "stage_times": stage_times,
    "final_output": str(final_xlsx),
    }

    summary_path = Path(cfg.ledger_dir) / f"{cfg.run_version}_full_pipeline_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n========== DONE ==========")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()