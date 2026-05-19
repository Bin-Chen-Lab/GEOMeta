# GEOMeta

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-active-success)

LLM-guided metadata extraction, semantic normalization, and ontology-aware metadata standardization framework for GEO transcriptomic studies.

---

# Overview

GEO metadata are highly heterogeneous across studies due to inconsistent free-text annotations, incomplete sample descriptions, variable disease terminology, fragmented tissue naming conventions, and inconsistent experimental metadata reporting.

GEOMeta addresses these challenges through a multi-stage metadata harmonization framework that combines:

- Context-aware metadata extraction
- Semantic normalization
- Ontology-aware disease and tissue mapping
- Controlled perturbation standardization
- Reviewer-aware recovery and validation workflows

The framework is designed for large-scale cross-study transcriptomic integration and downstream biomedical machine learning applications.

The current curated release comprises 594,989 GSM samples derived from 22,782 unique GSE studies spanning diverse disease, tissue, demographic, and perturbation contexts.

---

# Pipeline Overview

GEOMeta multi-stage metadata harmonization workflow for GEO transcriptomic studies.

<p align="center">
  <img src="figures/geometa_workflow.png" width="950">
</p>

---

# Quick Start

The repository includes example GEO study lists for testing the full pipeline from Stage 0.

Supported input formats:

```text
input/gse_ids.xlsx
```

The input file should contain GEO Series accessions (`GSE_ID`) per row. Stage 0 automatically retrieves the corresponding `GSE_Info` and `GSM_Info` metadata directly from GEO.

Runtime depends on the number of GSE studies, GSM samples, and Azure OpenAI response latency.

---

# Installation

## Clone Repository

```bash
git clone https://github.com/Bin-Chen-Lab/GEOMeta.git
cd GEOMeta
```

## Create Environment

Recommended setup using Conda Forge:

```bash
conda create -n geometa -c conda-forge python=3.10 expat pandas openpyxl scikit-learn rapidfuzz requests pyarrow python-docx openai -y
conda activate geometa
```

Verify the environment:

```bash
which python
python -c "import xml.parsers.expat, pandas, openpyxl, openai; print('OK')"
```

The verification command should print `OK`.

---

## Install Dependencies

Install the required Python packages from the repository root:

```bash
pip install -r requirements.txt
```

---

## Azure OpenAI Configuration

GEOMeta uses Azure OpenAI for metadata annotation and normalization.

Set environment variables:

```bash
export AZURE_OPENAI_API_KEY="YOUR_KEY"
export AZURE_OPENAI_ENDPOINT="YOUR_ENDPOINT"
export AZURE_OPENAI_API_VERSION="2024-12-01-preview"
export AZURE_OPENAI_DEPLOYMENT="YOUR_DEPLOYMENT"
```

---

# Quick Start

The repository includes a small example input file containing GEO Series accessions for testing the full pipeline from Stage 0. Stage 0 automatically retrieves the corresponding `GSE_Info` and `GSM_Info` from GEO.

Example input file:

```text
input/gse_ids.xlsx
```

Run all commands from the repository root directory after activating the Conda environment.

Run the complete pipeline:

```bash
PYTHONPATH=. python scripts/run_pipeline.py \
  --workdir . \
  --gse-file input/gse_ids.xlsx
```

---

# Troubleshooting

## Conda environment points to the wrong Python

If the verification command fails, first check which Python is active:

```bash
which python
conda info --envs
```

The active Python should come from the environment you created, for example:

```text
.../envs/geometa/bin/python
```

If your machine has multiple Conda installations, activate the environment using the full path to the Conda installation that created it. For example:

```bash
source /path/to/anaconda3/bin/activate geometa
```

On some systems, this may look like:

```bash
source /opt/anaconda3/bin/activate geometa
```

Then verify again:

```bash
which python
python -c "import xml.parsers.expat, pandas, openpyxl, openai; print('OK')"
```

## Conda XML / openpyxl / pyexpat errors

If you encounter `pyexpat`, `libexpat`, `openpyxl`, or `No module named expat` errors, recreate the environment using Conda Forge:

```bash
conda deactivate
conda env remove -n geometa -y
conda create -n geometa -c conda-forge python=3.10 expat pandas openpyxl scikit-learn rapidfuzz requests pyarrow python-docx openai -y
conda activate geometa
```

Then verify:

```bash
python -c "import xml.parsers.expat, pandas, openpyxl, openai; print('OK')"
```

These errors usually reflect a local Conda library conflict rather than a GEOMeta issue.

## OpenAI package not found

If `openai` is not found, install it with Conda:

```bash
conda install -c conda-forge openai -y
```

Then verify:

```bash
python -c "import pandas, openai; print('OK')"
```

---

# Repository Structure

```text
scripts/                Pipeline execution scripts
geo_annotation_agent/   Core pipeline implementation
Annotation_Prompts/     LLM extraction prompts
postprocessing/         Stage 2 normalization prompts
inference/              Derived metadata inference rules
mappings/               Disease/tissue/compound references
input/                  Input GSE accession lists
figures/                Workflow figures and diagrams
artifacts/              Generated outputs, caches, ledgers, and review files
requirements.txt        Python package dependencies
```

---

# Pipeline Stages

## Stage 0 — GEO Retrieval

Retrieves GEO metadata directly from NCBI GEO and constructs annotation-ready study/sample metadata blocks.

### Key Features

- Local GEO cache system
- Automatic retry/recovery
- Chunked GSM batching
- Structured GSE/GSM metadata generation

Implemented in:

```text
geo_annotation_agent/stage0_retrieve.py
```

---

## Stage 1 — LLM Metadata Annotation

Performs structured metadata extraction using role-specific prompts.

### Representative Extracted Metadata Fields

- Disease
- Tissue
- Experimental setting
- Perturbation, dose, frequency, duration
- RNA library
- Age
- Sex
- Ethnicity
- Specimen type
- Timepoint
- Outcome
- Organism
- Genotype
- Strain

### Key Features

- Role-based extraction
- Structured JSON enforcement
- Multi-GSM chunk annotation
- Recovery logic for malformed outputs
- Reviewer-aware logging system

Implemented in:

```text
geo_annotation_agent/stage1_annotate.py
```

---

## Stage 2 — Post-processing & Standardization

Applies controlled normalization and semantic standardization to Stage 1 outputs.

### Standardization Tasks

- Disease normalization
- Tissue normalization
- Experimental setting cleanup
- RNA source normalization
- Sex inference
- Age-group derivation
- Perturbation classification

### Key Features

- Field-specific post-processing prompts
- Cached normalization mappings
- Deterministic preprocessing
- Controlled vocabulary harmonization
- Selective rerun/review system

Implemented in:

```text
geo_annotation_agent/stage2_postprocess.py
```

---

## Stage 3 — Ontology-aware Mapping

Maps standardized metadata to curated biomedical ontologies and external resources.

### Disease Mapping

Disease annotations are mapped to:

- CTD MEDIC disease ontology
- MeSH-compatible disease identifiers
- Disease hierarchy metadata

### Tissue Mapping

Tissue annotations are normalized into curated tissue categories.

### Compound Mapping

Chemical perturbations are mapped to:

- PubChem compounds
- CID identifiers
- Canonical SMILES
- PubChem URLs

### Key Features

- Prior curated mapping reuse
- LLM-assisted ontology matching
- TF-IDF candidate retrieval
- Synonym-aware matching
- PubChem integration
- Novel-term detection
- Review/correction workflows

Implemented in:

```text
geo_annotation_agent/stage3_map.py
```

---

# Example Final Metadata Fields

- Disease
- Broad_Disease_Category
- Tissue
- RNA_Library
- Experimental_Setting
- GSE_Pert
- GSM_Pert
- Perturbation
- Pert_Type
- Age
- Age_Group
- Sex

---

# Output Files

Main outputs are written to:

```text
artifacts/outputs/
```

| File | Description |
|---|---|
| `*_stage0_input.parquet` | GEO retrieval output |
| `*_stage1_raw.xlsx` | Raw LLM annotations |
| `*_stage2_post.xlsx` | Standardized annotations |
| `*_stage3_mapped.xlsx` | Full ontology-mapped dataset |
| `*_stage3_mapped_filtered.xlsx` | Filtered mapped dataset |
| `*_stage3_final_release.xlsx` | Simplified final release dataset |
| `*_stage3_cp_perturbation_release.xlsx` | Compound perturbation-focused release dataset |

Additional artifacts include:

- Mapping caches
- GEO caches
- Review ledgers
- Novel term reports
- Manual review files

---

# Current Ontology Resources

## Disease

- CTD MEDIC
- MeSH-compatible disease hierarchy

## Compounds

- PubChem

## Tissue

- Curated tissue vocabulary
- Brain-region normalization framework

---

# Caching and Reproducibility

GEOMeta maintains persistent caches for:

- GEO downloads
- LLM normalization mappings
- Ontology mapping results

All intermediate outputs, caches, mappings, and review artifacts are retained to support reproducibility and iterative refinement.

---

# Notes

- GEO metadata quality varies substantially across studies.
- Some annotations may still require manual review.
- LLM outputs are constrained through structured prompting and reviewer-aware recovery logic.
- Large-scale runs may require substantial Azure OpenAI quota depending on dataset size.

---

# Citation

If you use GEOMeta in your work, please cite:

```text
Citation information will be added after manuscript publication.
```

---

# License

MIT License

---

# Acknowledgments

- NCBI GEO
- CTD MEDIC
- PubChem
- Human Protein Atlas
- Azure OpenAI
