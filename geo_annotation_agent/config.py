from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    # -------------------------
    # Core project paths
    # -------------------------
    workdir: Path

    # Input modes
    input_xlsx: Path
    gse_list_input: Path

    # Prompt folders / files
    post_prompt_dir: Path

    # Core KB / mapping resources
    ctd_csv: Path
    prior_disease_mapping_xlsx: Path
    prior_tissue_mapping_xlsx: Path
    prior_cp_mapping_xlsx: Path
    disease_group_mapping_xlsx: Path

    tissue_mapping_prompt_docx: Path
    disease_mapping_prompt_docx: Path
    cp_mapping_prompt_docx: Path

    # Artifact / output directories
    artifacts_dir: Path
    outputs_dir: Path
    debug_dir: Path
    mapping_cache_dir: Path
    review_dir: Path
    memory_dir: Path
    ledger_dir: Path

    # GEO retrieval/cache
    geo_cache_dir: Path
    geo_gse_cache_dir: Path
    geo_gsm_cache_dir: Path

    # Manual review exports
    manual_review_dir: Path
    novel_term_dir: Path

    # -------------------------
    # Generic LLM backend
    # -------------------------
    # Default target is the direct OpenAI API, but the same interface can point
    # to OpenAI-compatible gateways/servers such as LiteLLM, OpenRouter, vLLM,
    # Ollama/LM Studio, Together/Fireworks-style APIs, etc.
    llm_api_type: str = "openai_compatible"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-5"

    # -------------------------
    # Runtime knobs
    # -------------------------
    max_retries: int = 3
    retry_sleep_seconds: int = 10
    top_p: float = 0.95
    sleep_between_calls: float = 0.2
    term_batch_size: int = 30
    run_version: str = "gaa"

    # GEO retrieval
    stage0_chunk_size: int = 30
    geo_fetch_retry: int = 6
    geo_timeout_sec: int = 30

    # PubChem / HTTP
    pubchem_timeout_sec: int = 15

    # Reviewer limits
    max_row_reviews_per_run: int = 150
    max_gse_reviews_per_run: int = 50

    def __post_init__(self):
        self.workdir = Path(self.workdir).resolve()

        self.input_xlsx = Path(self.input_xlsx)
        self.gse_list_input = Path(self.gse_list_input)
        self.post_prompt_dir = Path(self.post_prompt_dir)

        self.ctd_csv = Path(self.ctd_csv)
        self.prior_disease_mapping_xlsx = Path(self.prior_disease_mapping_xlsx)
        self.prior_tissue_mapping_xlsx = Path(self.prior_tissue_mapping_xlsx)
        self.prior_cp_mapping_xlsx = Path(self.prior_cp_mapping_xlsx)
        self.disease_group_mapping_xlsx = Path(self.disease_group_mapping_xlsx)

        self.tissue_mapping_prompt_docx = Path(self.tissue_mapping_prompt_docx)
        self.disease_mapping_prompt_docx = Path(self.disease_mapping_prompt_docx)
        self.cp_mapping_prompt_docx = Path(self.cp_mapping_prompt_docx)

        self.artifacts_dir = Path(self.artifacts_dir)
        self.outputs_dir = Path(self.outputs_dir)
        self.debug_dir = Path(self.debug_dir)
        self.mapping_cache_dir = Path(self.mapping_cache_dir)
        self.review_dir = Path(self.review_dir)
        self.memory_dir = Path(self.memory_dir)
        self.ledger_dir = Path(self.ledger_dir)

        self.geo_cache_dir = Path(self.geo_cache_dir)
        self.geo_gse_cache_dir = Path(self.geo_gse_cache_dir)
        self.geo_gsm_cache_dir = Path(self.geo_gsm_cache_dir)

        self.manual_review_dir = Path(self.manual_review_dir)
        self.novel_term_dir = Path(self.novel_term_dir)

        # Generic LLM environment overrides.
        #
        # Preferred names:
        #   LLM_API_TYPE
        #   LLM_API_KEY
        #   LLM_BASE_URL
        #   LLM_MODEL
        #
        # Backward/convenience aliases for direct OpenAI:
        #   OPENAI_API_KEY
        #   OPENAI_MODEL
        self.llm_api_type = os.getenv("LLM_API_TYPE", self.llm_api_type).lower().strip()

        self.llm_api_key = os.getenv(
            "LLM_API_KEY",
            os.getenv("OPENAI_API_KEY", self.llm_api_key),
        ).strip()

        self.llm_base_url = os.getenv(
            "LLM_BASE_URL",
            self.llm_base_url,
        ).rstrip("/").strip()

        self.llm_model = os.getenv(
            "LLM_MODEL",
            os.getenv("OPENAI_MODEL", self.llm_model),
        ).strip()

    def validate_env(self):
        """
        Validate the LLM runtime environment.

        GEOMeta now uses a provider-agnostic OpenAI-compatible interface.
        The core pipeline no longer requires Azure-specific variables.
        """
        missing = []

        if not self.llm_api_type:
            missing.append("LLM_API_TYPE")

        if self.llm_api_type not in {"openai_compatible", "openai"}:
            raise EnvironmentError(
                f"Unsupported LLM_API_TYPE={self.llm_api_type}. "
                "Currently supported: openai_compatible."
            )

        if not self.llm_api_key:
            missing.append("LLM_API_KEY or OPENAI_API_KEY")

        if not self.llm_base_url:
            missing.append("LLM_BASE_URL")

        if not self.llm_model:
            missing.append("LLM_MODEL or OPENAI_MODEL")

        if missing:
            raise EnvironmentError("Missing LLM env vars: " + ", ".join(missing))

    def ensure_dirs(self):
        dirs = [
            self.artifacts_dir,
            self.outputs_dir,
            self.debug_dir,
            self.mapping_cache_dir,
            self.review_dir,
            self.memory_dir,
            self.ledger_dir,
            self.geo_cache_dir,
            self.geo_gse_cache_dir,
            self.geo_gsm_cache_dir,
            self.manual_review_dir,
            self.novel_term_dir,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def validate_paths(
        self,
        require_input_xlsx: bool = False,
        require_gse_list: bool = False,
        require_stage3_resources: bool = True,
        require_prompts: bool = True,
    ):
        required_paths = {}

        # Stage 1 / Stage 2 prompt dir
        if require_prompts:
            required_paths["post_prompt_dir"] = self.post_prompt_dir

        # Optional entry inputs
        if require_input_xlsx:
            required_paths["input_xlsx"] = self.input_xlsx

        if require_gse_list:
            required_paths["gse_list_input"] = self.gse_list_input

        # Stage 3 only
        if require_stage3_resources:
            required_paths["ctd_csv"] = self.ctd_csv
            required_paths["prior_disease_mapping_xlsx"] = self.prior_disease_mapping_xlsx
            required_paths["prior_tissue_mapping_xlsx"] = self.prior_tissue_mapping_xlsx
            required_paths["prior_cp_mapping_xlsx"] = self.prior_cp_mapping_xlsx
            required_paths["tissue_mapping_prompt_docx"] = self.tissue_mapping_prompt_docx
            required_paths["disease_mapping_prompt_docx"] = self.disease_mapping_prompt_docx
            required_paths["cp_mapping_prompt_docx"] = self.cp_mapping_prompt_docx

        missing = {
            name: str(path)
            for name, path in required_paths.items()
            if not path.exists()
        }

        if missing:
            pretty = "\n".join(f"{k}: {v}" for k, v in missing.items())
            raise FileNotFoundError(f"Missing required config paths:\n{pretty}")

    def preflight_summary(self) -> dict:
        return {
            "workdir": str(self.workdir),
            "input_xlsx": str(self.input_xlsx),
            "gse_list_input": str(self.gse_list_input),
            "post_prompt_dir": str(self.post_prompt_dir),
            "ctd_csv": str(self.ctd_csv),
            "prior_disease_mapping_xlsx": str(self.prior_disease_mapping_xlsx),
            "prior_tissue_mapping_xlsx": str(self.prior_tissue_mapping_xlsx),
            "prior_cp_mapping_xlsx": str(self.prior_cp_mapping_xlsx),
            "disease_group_mapping_xlsx": str(self.disease_group_mapping_xlsx),
            "artifacts_dir": str(self.artifacts_dir),
            "outputs_dir": str(self.outputs_dir),
            "mapping_cache_dir": str(self.mapping_cache_dir),
            "review_dir": str(self.review_dir),
            "manual_review_dir": str(self.manual_review_dir),
            "novel_term_dir": str(self.novel_term_dir),
            "run_version": self.run_version,
            "stage0_chunk_size": self.stage0_chunk_size,
            "llm_api_type": self.llm_api_type,
            "llm_base_url": self.llm_base_url,
            "llm_model": self.llm_model,
        }


def default_config(workdir: Path) -> Config:
    workdir = Path(workdir).resolve()

    artifacts = workdir / "artifacts"
    outputs = artifacts / "outputs"
    debug = artifacts / "debug_llm_raw"
    cache = artifacts / "mapping_cache"
    review = artifacts / "review_queue"
    memory = artifacts / "memory"
    ledger = artifacts / "ledgers"

    geo_cache = artifacts / "geo_cache"
    geo_gse_cache = geo_cache / "gse"
    geo_gsm_cache = geo_cache / "gsm"

    manual_review = artifacts / "manual_review"
    novel_terms = manual_review / "novel_terms"

    return Config(
        workdir=workdir,

        # Existing Stage1-style input, kept for backward compatibility
        input_xlsx=workdir / "input" / "stage1_input.xlsx",

        # Stage0 input: GSE accession list
        gse_list_input=workdir / "input" / "gse_ids.xlsx",

        # Stage2 postprocessing and inference prompts
        # Current public repo stores postprocessing/ and inference/ at repo root.
        post_prompt_dir=workdir,

        # Stage3 KB / curated mapping files
        ctd_csv=workdir / "mappings" / "disease" / "ctd_medic_disease_reference.csv",
        prior_disease_mapping_xlsx=workdir / "mappings" / "disease" / "disease_mappings.xlsx",
        prior_tissue_mapping_xlsx=workdir / "mappings" / "tissue" / "tissue_mappings.xlsx",
        prior_cp_mapping_xlsx=workdir / "mappings" / "compounds" / "compound_pubchem_mappings.xlsx",

        # Optional legacy field; keep only if other scripts still reference it
        disease_group_mapping_xlsx=workdir / "mappings" / "disease" / "disease_group_mappings.xlsx",

        # Stage3 mapping prompt files
        tissue_mapping_prompt_docx=workdir / "mappings" / "tissue" / "tissue_mapping_prompt.md",
        disease_mapping_prompt_docx=workdir / "mappings" / "disease" / "disease_mapping_prompt.md",
        cp_mapping_prompt_docx=workdir / "mappings" / "compounds" / "cp_mapping_prompt.md",

        # Artifact / output directories
        artifacts_dir=artifacts,
        outputs_dir=outputs,
        debug_dir=debug,
        mapping_cache_dir=cache,
        review_dir=review,
        memory_dir=memory,
        ledger_dir=ledger,

        # GEO retrieval/cache
        geo_cache_dir=geo_cache,
        geo_gse_cache_dir=geo_gse_cache,
        geo_gsm_cache_dir=geo_gsm_cache,

        # Manual review dirs
        manual_review_dir=manual_review,
        novel_term_dir=novel_terms,

        # Generic LLM defaults
        llm_api_type="openai_compatible",
        llm_api_key="",
        llm_base_url="https://api.openai.com/v1",
        llm_model="gpt-5",

        # Runtime defaults
        run_version="gaa",
        stage0_chunk_size=30,
        term_batch_size=30,
        pubchem_timeout_sec=15,
        geo_fetch_retry=6,
        geo_timeout_sec=30,
        max_row_reviews_per_run=150,
        max_gse_reviews_per_run=50,
    )