from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, Optional

import pandas as pd

from .ledger import LedgerV2
from .memory import MemoryV2
from .reviewer import ReviewerV2
from .reviewer_llm import ReviewerLLMV2, LLMReviewConfig
from .stage0_retrieve import run_stage0_retrieval
from .stage1_annotate import run_stage1_raw_annotation_v2
from .stage2_postprocess import run_stage2_postprocessing, run_stage2_postprocessing_v2
from .stage3_map import run_stage3_mapping


class Orchestrator:
    """
    Full workflow orchestrator.

    Supported entry modes:
      1) GSE-list driven:
           GSE list -> Stage0 retrieval -> Stage1 -> Stage2 pass1 -> review -> Stage2 rerun -> Stage3
      2) Existing Stage1-style input:
           input_xlsx -> Stage1 -> Stage2 pass1 -> review -> Stage2 rerun -> Stage3
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.cfg.ensure_dirs()

        self.ledger = LedgerV2(Path(cfg.ledger_dir), cfg.run_version)
        self.memory = MemoryV2(Path(cfg.memory_dir))
        self.reviewer = ReviewerV2()

        self.llm_reviewer = ReviewerLLMV2(
            cfg=cfg,
            debug_dir=Path(cfg.debug_dir) / "reviewer",
            llm_review_cfg=LLMReviewConfig(
                max_row_reviews_per_run=int(cfg.max_row_reviews_per_run),
                max_gse_reviews_per_run=int(cfg.max_gse_reviews_per_run),
                row_fields_focus=[
                    "Disease", "Organ_Region", "Pert", "Pert_Type",
                    "Sex", "Age", "Model_Type", "SampleType", "Specimen_Type",
                ],
            ),
        )

        self.output_dir = Path(cfg.outputs_dir)
        self.review_dir = Path(cfg.review_dir)
        self.ledger_dir = Path(cfg.ledger_dir)

    # -------------------------
    # Preflight
    # -------------------------
    def preflight(self, entry_mode: str = "input_xlsx") -> Dict[str, Any]:
        self.cfg.validate_env()

        if entry_mode == "gse_list":
            self.cfg.validate_paths(require_gse_list=True)
        elif entry_mode == "input_xlsx":
            self.cfg.validate_paths(require_input_xlsx=True)
        else:
            raise ValueError(f"Unsupported entry_mode: {entry_mode}")

        report = {
            "run_version": self.cfg.run_version,
            "entry_mode": entry_mode,
            "status": "ok",
            **self.cfg.preflight_summary(),
        }

        out = self.ledger_dir / f"{self.cfg.run_version}_preflight.json"
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("[SAVED] Preflight:", out)

        return report

    # -------------------------
    # Stage 0
    # -------------------------
    def run_stage0(self) -> pd.DataFrame:
        df_stage0 = run_stage0_retrieval(self.cfg)
        return df_stage0

    # -------------------------
    # Load Stage1 input
    # -------------------------
    def load_stage1_input_from_file(self) -> pd.DataFrame:
        df_input = pd.read_excel(self.cfg.input_xlsx, engine="openpyxl")
        return df_input

    # -------------------------
    # Stage 1
    # -------------------------
    def run_stage1(self, df_stage1_input: pd.DataFrame) -> pd.DataFrame:
        """
        Stage1 expects a chunked input table with at least:
          - GSE_ID
          - GSE_Info
          - GSM_Info
          - GSM_Counts
        """
        # reset reviewer state for stage1
        self.reviewer = ReviewerV2()

        df_stage1 = run_stage1_raw_annotation_v2(
            cfg=self.cfg,
            df_input=df_stage1_input,
            reviewer=self.reviewer,
            save_outputs=True,
        )

        stage1_review_df = self.reviewer.to_dataframe()
        stage1_review_path = self.review_dir / f"{self.cfg.run_version}_stage1_review.xlsx"
        stage1_review_df.to_excel(stage1_review_path, index=False)

        print("[SAVED] Stage1 review:", stage1_review_path)
        return df_stage1

    # -------------------------
    # Stage 2 pass 1
    # -------------------------
    def run_stage2_pass1(self, df_stage1: pd.DataFrame) -> pd.DataFrame:
        df_stage2_pass1 = run_stage2_postprocessing(self.cfg, df_stage1)

        out_xlsx = self.output_dir / f"{self.cfg.run_version}_stage2_pass1.xlsx"
        out_parq = self.output_dir / f"{self.cfg.run_version}_stage2_pass1.parquet"
        df_stage2_pass1.to_excel(out_xlsx, index=False)
        df_stage2_pass1.to_parquet(out_parq, index=False)

        print("[SAVED] Stage2 pass1 Excel:", out_xlsx)
        print("[SAVED] Stage2 pass1 Parquet:", out_parq)

        return df_stage2_pass1

    # -------------------------
    # Stage 2 review
    # -------------------------
    def review_stage2(self, df_stage1: pd.DataFrame, df_stage2_pass1: pd.DataFrame) -> pd.DataFrame:
        """
        Hybrid review:
          - deterministic rules on all rows
          - LLM row review only on flagged rows
          - LLM GSE review only on suspicious GSEs
          - build reannotation queue
        """
        # reset reviewer state for stage2
        self.reviewer = ReviewerV2()

        # 1) deterministic review
        self.reviewer.review_stage2_rules(df_stage2_pass1)
        self.reviewer.review_within_gse(df_stage2_pass1)
        rule_review_df = self.reviewer.to_dataframe()

        rule_review_path = self.review_dir / f"{self.cfg.run_version}_stage2_rule_review.xlsx"
        rule_review_df.to_excel(rule_review_path, index=False)
        print("[SAVED] Stage2 rule review:", rule_review_path)

        # 2) selective LLM row review
        flagged_rows_df = self.reviewer.get_flagged_rows_for_llm()

        llm_row_review_df = self.llm_reviewer.review_rows(
            df_stage2=df_stage2_pass1,
            df_input_stage1_source=df_stage1,
            flagged_rows_df=flagged_rows_df,
        )
        llm_row_review_path = self.review_dir / f"{self.cfg.run_version}_stage2_llm_row_review.xlsx"
        llm_row_review_df.to_excel(llm_row_review_path, index=False)
        print("[SAVED] Stage2 LLM row review:", llm_row_review_path)

        # 3) selective LLM GSE review
        llm_gse_review_df = self.llm_reviewer.review_gses(
            df_stage2=df_stage2_pass1,
            df_input_stage1_source=df_stage1,
            flagged_rows_df=flagged_rows_df,
        )
        llm_gse_review_path = self.review_dir / f"{self.cfg.run_version}_stage2_llm_gse_review.xlsx"
        llm_gse_review_df.to_excel(llm_gse_review_path, index=False)
        print("[SAVED] Stage2 LLM GSE review:", llm_gse_review_path)

        # 4) build rerun queue
        rerun_queue_df = self.reviewer.build_reannotation_queue(
            rule_review_df=rule_review_df,
            llm_row_review_df=llm_row_review_df,
            llm_gse_review_df=llm_gse_review_df,
        )
        rerun_queue_path = self.review_dir / f"{self.cfg.run_version}_stage2_reannotation_queue.xlsx"
        rerun_queue_df.to_excel(rerun_queue_path, index=False)
        print("[SAVED] Stage2 reannotation queue:", rerun_queue_path)

        return rerun_queue_df

    # -------------------------
    # Stage 2 rerun executor
    # -------------------------
    def run_stage2_rerun(
        self,
        df_stage1: pd.DataFrame,
        df_stage2_pass1: pd.DataFrame,
        rerun_queue_df: pd.DataFrame,
    ) -> pd.DataFrame:
        df_stage2_final = run_stage2_postprocessing_v2(
            cfg=self.cfg,
            df_stage1=df_stage1,
            df_queue=rerun_queue_df,
            run_pass1=False,
            df_stage2_pass1=df_stage2_pass1,
        )

        final_xlsx = self.output_dir / f"{self.cfg.run_version}_stage2_post_final.xlsx"
        final_parq = self.output_dir / f"{self.cfg.run_version}_stage2_post_final.parquet"

        df_stage2_final.to_excel(final_xlsx, index=False)
        df_stage2_final.to_parquet(final_parq, index=False)

        print("[SAVED] Stage2 final Excel:", final_xlsx)
        print("[SAVED] Stage2 final Parquet:", final_parq)

        return df_stage2_final

    # -------------------------
    # Stage 3
    # -------------------------
    def run_stage3(self, df_stage2_final: pd.DataFrame) -> pd.DataFrame:
        df_stage3 = run_stage3_mapping(self.cfg, df_stage2_final)

        out_xlsx = self.output_dir / f"{self.cfg.run_version}_stage3_mapped.xlsx"
        df_stage3.to_excel(out_xlsx, index=False)

        print("[SAVED] Stage3 mapped Excel:", out_xlsx)
        return df_stage3

    # -------------------------
    # Integrity checks
    # -------------------------
    def validate_row_integrity(
        self,
        df_stage1: pd.DataFrame,
        df_stage2: pd.DataFrame,
        df_stage3: pd.DataFrame,
    ) -> Dict[str, Any]:
        checks = {
            "stage1_rows": int(df_stage1.shape[0]),
            "stage2_rows": int(df_stage2.shape[0]),
            "stage3_rows": int(df_stage3.shape[0]),
            "stage1_unique_gsm": int(df_stage1["GSM_ID"].astype(str).nunique()) if "GSM_ID" in df_stage1.columns else 0,
            "stage2_unique_gsm": int(df_stage2["GSM_ID"].astype(str).nunique()) if "GSM_ID" in df_stage2.columns else 0,
            "stage3_unique_gsm": int(df_stage3["GSM_ID"].astype(str).nunique()) if "GSM_ID" in df_stage3.columns else 0,
            "stage1_dup_gsm": int(df_stage1["GSM_ID"].astype(str).duplicated().sum()) if "GSM_ID" in df_stage1.columns else 0,
            "stage2_dup_gsm": int(df_stage2["GSM_ID"].astype(str).duplicated().sum()) if "GSM_ID" in df_stage2.columns else 0,
            "stage3_dup_gsm": int(df_stage3["GSM_ID"].astype(str).duplicated().sum()) if "GSM_ID" in df_stage3.columns else 0,
        }

        if checks["stage2_rows"] != checks["stage1_rows"]:
            raise AssertionError(f"Row loss detected: Stage2 rows ({checks['stage2_rows']}) != Stage1 rows ({checks['stage1_rows']})")

        if checks["stage3_rows"] != checks["stage2_rows"]:
            raise AssertionError(f"Row loss detected: Stage3 rows ({checks['stage3_rows']}) != Stage2 rows ({checks['stage2_rows']})")

        if checks["stage2_unique_gsm"] != checks["stage1_unique_gsm"]:
            raise AssertionError("Unique GSM count mismatch between Stage1 and Stage2.")

        if checks["stage3_unique_gsm"] != checks["stage2_unique_gsm"]:
            raise AssertionError("Unique GSM count mismatch between Stage2 and Stage3.")

        out = self.ledger_dir / f"{self.cfg.run_version}_row_integrity.json"
        out.write_text(json.dumps(checks, indent=2), encoding="utf-8")
        print("[SAVED] Row integrity:", out)

        return checks

    # -------------------------
    # Novel-term / manual-review exports
    # -------------------------
    def export_novel_term_review_files(self) -> Dict[str, str]:
        """
        Collect known novel-term outputs if present and summarize for manual review.
        This does not create mappings; it only centralizes review artifacts.
        """
        outputs = {}

        candidate_files = [
            Path(self.output_dir) / f"{self.cfg.run_version}_DiseasePost_mappings.xlsx",
            Path(self.output_dir) / f"{self.cfg.run_version}_OrganRegionPost_mappings.xlsx",
            Path(self.output_dir) / f"{self.cfg.run_version}_CP_PertPost_mappings.xlsx",
            Path(self.review_dir) / f"{self.cfg.run_version}_stage2_reannotation_queue.xlsx",
        ]

        manifest = []
        for fp in candidate_files:
            if fp.exists():
                manifest.append({"file": str(fp), "name": fp.name})

        manifest_fp = Path(self.novel_term_dir) / f"{self.cfg.run_version}_manual_review_manifest.json"
        manifest_fp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        outputs["manifest"] = str(manifest_fp)

        print("[SAVED] Manual review manifest:", manifest_fp)
        return outputs

    # -------------------------
    # Full run: start from Stage0
    # -------------------------
    def run_all_from_gse_list(self) -> Dict[str, Any]:
        self.preflight(entry_mode="gse_list")

        df_stage0 = self.run_stage0()
        df_stage1 = self.run_stage1(df_stage0)
        df_stage2_pass1 = self.run_stage2_pass1(df_stage1)
        rerun_queue_df = self.review_stage2(df_stage1, df_stage2_pass1)
        df_stage2_final = self.run_stage2_rerun(df_stage1, df_stage2_pass1, rerun_queue_df)
        df_stage3 = self.run_stage3(df_stage2_final)

        integrity = self.validate_row_integrity(df_stage1, df_stage2_final, df_stage3)
        review_exports = self.export_novel_term_review_files()

        self.memory.save()

        summary = {
            "run_version": self.cfg.run_version,
            "entry_mode": "gse_list",
            "stage0_rows": int(df_stage0.shape[0]),
            "stage1_rows": int(df_stage1.shape[0]),
            "stage2_pass1_rows": int(df_stage2_pass1.shape[0]),
            "stage2_final_rows": int(df_stage2_final.shape[0]),
            "stage3_rows": int(df_stage3.shape[0]),
            "reannotation_queue_rows": int(rerun_queue_df.shape[0]),
            "integrity": integrity,
            "review_exports": review_exports,
        }

        summary_path = self.ledger_dir / f"{self.cfg.run_version}_pipeline_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print("[SAVED] Pipeline summary:", summary_path)

        return summary

    # -------------------------
    # Full run: start from existing Stage1-style input
    # -------------------------
    def run_all_from_input_table(self) -> Dict[str, Any]:
        self.preflight(entry_mode="input_xlsx")

        df_input = self.load_stage1_input_from_file()
        df_stage1 = self.run_stage1(df_input)
        df_stage2_pass1 = self.run_stage2_pass1(df_stage1)
        rerun_queue_df = self.review_stage2(df_stage1, df_stage2_pass1)
        df_stage2_final = self.run_stage2_rerun(df_stage1, df_stage2_pass1, rerun_queue_df)
        df_stage3 = self.run_stage3(df_stage2_final)

        integrity = self.validate_row_integrity(df_stage1, df_stage2_final, df_stage3)
        review_exports = self.export_novel_term_review_files()

        self.memory.save()

        summary = {
            "run_version": self.cfg.run_version,
            "entry_mode": "input_xlsx",
            "stage1_input_rows": int(df_input.shape[0]),
            "stage1_rows": int(df_stage1.shape[0]),
            "stage2_pass1_rows": int(df_stage2_pass1.shape[0]),
            "stage2_final_rows": int(df_stage2_final.shape[0]),
            "stage3_rows": int(df_stage3.shape[0]),
            "reannotation_queue_rows": int(rerun_queue_df.shape[0]),
            "integrity": integrity,
            "review_exports": review_exports,
        }

        summary_path = self.ledger_dir / f"{self.cfg.run_version}_pipeline_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print("[SAVED] Pipeline summary:", summary_path)

        return summary

    # -------------------------
    # Generic dispatcher
    # -------------------------
    def run_all(self, entry_mode: str = "input_xlsx") -> Dict[str, Any]:
        if entry_mode == "gse_list":
            return self.run_all_from_gse_list()
        elif entry_mode == "input_xlsx":
            return self.run_all_from_input_table()
        else:
            raise ValueError(f"Unsupported entry_mode: {entry_mode}")