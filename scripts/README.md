# Scripts

This folder contains command-line entry points and supporting QA utilities for running GEOMeta.

## Main pipeline runner

### `run_pipeline.py`

Runs the full GEOMeta workflow from a list of GEO Series IDs:

```bash
PYTHONPATH=. python -u scripts/run_pipeline.py \
  --workdir . \
  --gse-file input/gse_ids.csv
```

The full pipeline runs:

* Stage 0: GEO metadata retrieval
* Stage 1: raw LLM-guided annotation
* Stage 1 QA1: within-GSE consistency audit
* Stage 1 QA2: cross-agent validation
* Stage 1 QA3: evidence-grounded verification and targeted rescue
* Stage 2: field-level standardization and controlled inference
* Stage 3: ontology/resource mapping and release-file generation
* Stage 4: deterministic release QA

## Standalone stage runners

These scripts allow individual stages to be rerun without repeating the full pipeline.

### `run_stage0.py`

Runs GEO metadata retrieval from a GSE list.

### `run_stage1.py`

Runs Stage 1 annotation from a Stage 0 output file.

### `run_stage2.py`

Runs Stage 2 post-processing from a Stage 1 output file.

### `run_stage3.py`

Runs Stage 3 mapping from a saved Stage 2 output file. This is useful when mapping resources, release filters, or Stage 4 QA rules have been updated and Stage 0–2 do not need to be rerun.

## Stage 1 QA runners

These are standalone wrappers for rerunning specific Stage 1 QA modules.

### `run_stage1_qa1_consistency.py`

Runs within-GSE consistency auditing and high-confidence correction.

### `run_stage1_qa2_cross_validation.py`

Runs cross-agent and cross-field validation.

### `run_stage1_qa3_evidence_verifier.py`

Runs evidence-grounded verification and targeted rescue for selected missing or uncertain annotations.

## Stage 1 QA engine scripts

These files contain the underlying QA logic used by the full pipeline.

### `within_gse_consistency_audit.py`

Implements Stage 1 QA1. It audits annotations within each GSE, identifies partial missingness, inconsistent values, and whole-GSE missing fields, and applies only conservative high-confidence blank-cell corrections.

### `stage1_cross_agent_validation.py`

Implements Stage 1 QA2. It checks whether outputs from different role-specific annotation agents are logically compatible, including disease, tissue, RNA source, sample type, perturbation, sex, age, and experimental setting.

### `stage1_evidence_verifier.py`

Implements Stage 1 QA3. It builds targeted evidence packets from GSE/GSM metadata and applies only high-confidence evidence-supported rescue corrections.

### `stage1_provenance_audit.py`

Builds a Stage 1 provenance workbook summarizing raw annotations, QA1 corrections, QA3 corrections, final Stage 1 output, and cell-level changes.

## Optional LLM reviewer utilities

These scripts are not required for the default full pipeline run. They support targeted review of flagged QA cases.

### `llm_gse_review_agent.py`

Optional LLM reviewer for ambiguous within-GSE QA1 issues.

### `llm_cross_agent_review_agent.py`

Optional LLM reviewer for QA2 cross-agent validation issues.

## Recommended usage

For standard use, run:

```bash
PYTHONPATH=. python -u scripts/run_pipeline.py \
  --workdir . \
  --gse-file input/gse_ids.csv
```

Use the standalone stage or QA scripts only when rerunning a specific stage, debugging, or testing changes to QA/mapping logic.
