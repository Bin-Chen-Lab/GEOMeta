# GEOMeta Pipeline Scripts

This directory contains the command-line runners and optional quality-control
utilities for the GEOMeta pipeline.

## Main pipeline runners

- `run_pipeline.py`: runs the complete GEOMeta workflow.
- `run_stage0.py`: retrieves and prepares GEO metadata.
- `run_stage1.py`: runs Stage 1 annotation.
- `run_stage2.py`: runs field standardization and controlled inference.
- `run_stage3.py`: runs controlled-vocabulary and external-resource mapping.

## Optional Stage 1 quality-control modules

- `run_stage1_qa1_consistency.py`: performs within-GSE consistency checks and
  restricted high-confidence blank-cell recovery.
- `run_stage1_qa2_cross_validation.py`: performs cross-field consistency
  validation across Stage 1 outputs.
- `run_stage1_qa3_evidence_verifier.py`: performs evidence-grounded review and
  targeted recovery for unresolved annotations.

The QA modules are quality-control procedures within the fixed GEOMeta
workflow. They are not additional autonomous agents or independent annotation
stages.

## Additional utilities

The remaining scripts support provenance auditing, evidence verification,
within-GSE consistency assessment, and merging of Stage 3 batch outputs.

Run commands should be executed from the repository root. See the main
[`README.md`](../README.md) for installation and usage instructions.