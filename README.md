# GEOMeta

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-active-success)

LLM-guided metadata extraction, normalization, and ontology-aware standardization framework for GEO transcriptomic studies.

---

# Why GEOMeta?

GEO metadata are highly heterogeneous across studies due to inconsistent free-text annotations, incomplete sample descriptions, variable disease terminology, fragmented tissue naming conventions, and inconsistent experimental metadata reporting.

GEOMeta addresses these challenges through a multi-stage metadata harmonization framework that combines:

- Context-aware metadata extraction
- Semantic normalization
- Ontology-aware disease and tissue mapping
- Controlled perturbation standardization
- Reviewer-aware recovery and validation workflows

The framework is designed for large-scale cross-study transcriptomic integration and downstream biomedical machine learning applications.

The repository includes a small example input file containing a short list of GEO studies for testing the full pipeline from Stage 0. The file contains GSE accessions only; Stage 0 automatically retrieves the corresponding GSE_Info and GSM_Info from GEO.

The current curated release comprises 594,989 GSM samples aggregated from 22,782 unique GSE studies spanning diverse disease, tissue, demographic, and perturbation contexts.

---

# Pipeline Overview

GEOMeta multi-stage metadata harmonization workflow for GEO transcriptomic studies.

<p align="center">
  <img src="figures/geometa_workflow.png" width="900">
</p>

---

# Quick Start

The repository includes a benchmark input file containing 1,000 GEO studies:

```text
input/gse_ids.xlsx
```

Run the complete pipeline:

```bash
PYTHONPATH=. python scripts/run_pipeline.py \
  --workdir . \
  --gse-file input/gse_ids.xlsx
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
artifacts/              Outputs, caches, ledgers, and review files
```

---

# Installation

## Clone Repository

```bash
git clone https://github.com/<YOUR_USERNAME>/GEOMeta.git
cd GEOMeta
```

---

## Create Environment

Recommended Python version:

```text
Python >= 3.10
```

Example:

```bash
conda create -n geometa python=3.11
conda activate geometa
```

---

## Install Dependencies

```bash
pip install -r requirements.txt
```

Core dependencies include:

- pandas
- openpyxl
- scikit-learn
- rapidfuzz
- requests
- openai

---

# Azure OpenAI Configuration

GEOMeta uses Azure OpenAI for metadata annotation and normalization.

Set environment variables:

```bash
export AZURE_OPENAI_API_KEY="YOUR_KEY"
export AZURE_OPENAI_ENDPOINT="YOUR_ENDPOINT"
export AZURE_OPENAI_API_VERSION="YOUR_VERSION"
export AZURE_OPENAI_DEPLOYMENT="YOUR_DEPLOYMENT"
```

LLM client implementation:

```text
geo_annotation_agent/llm_client.py
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

### Extracted Metadata Fields

- Disease
- Tissue
- Experimental setting
- Perturbation, Dose, Frequency, Duration
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
- Isomeric SMILES

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

This reduces repeated API calls and improves reproducibility across reruns.

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
- Azure OpenAI
