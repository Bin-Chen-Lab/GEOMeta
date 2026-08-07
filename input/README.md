# GEOMeta Input Files

This directory contains example GSE accession files for running the GEOMeta pipeline.

## Supported input formats

GEOMeta accepts GSE accession lists in the following formats:

- CSV: `.csv`
- Excel: `.xlsx`
- Tab-separated text: `.tsv`
- Plain text: `.txt`

CSV is used in the primary examples, but all supported formats can be supplied through the same `--gse-file` argument.

## Tabular input files

CSV, Excel, and TSV files should preferably contain a column named `GSE_ID`.

Example:

```text
GSE_ID
GSE130063
GSE53779
```

If a `GSE_ID` column is not present, GEOMeta reads the first column as the GSE accession list.

## Plain-text input files

For `.txt` files, provide one GSE accession per line:

```text
GSE147493
GSE116860
```

Blank entries and duplicate GSE accessions are removed during input
processing.

## Example commands

### CSV input

```bash
PYTHONPATH=. python scripts/run_pipeline.py \
  --workdir . \
  --gse-file input/gse_ids.csv
```

### Excel input

```bash
PYTHONPATH=. python scripts/run_pipeline.py \
  --workdir . \
  --gse-file input/gse_ids.xlsx
```

### TSV input

```bash
PYTHONPATH=. python scripts/run_pipeline.py \
  --workdir . \
  --gse-file input/gse_ids.tsv
```

### Plain-text input

```bash
PYTHONPATH=. python scripts/run_pipeline.py \
  --workdir . \
  --gse-file input/gse_ids.txt
```

## SuperSeries records

Parent SuperSeries records may contain insufficient experimental-design information for sample-level annotation. When applicable, users should provide the corresponding component SubSeries accessions.