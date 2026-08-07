# RNA-Source Mapping Resources

This folder contains reviewed RNA-source mapping resources used in the
GEOMeta Stage 3 mapping workflow.

## Files

### `rna_source_mapping_prompt.md`

Task-specific instructions used to review and map previously unseen
RNA-source terms.

### `RNA_Source_mappings.xlsx`

Reviewed reusable RNA-source mapping table. The required fields include:

- `Original_RNA_Source_Term`: RNA-source term entering the reviewed mapping
  workflow.
- `RNA_Source_Mapped`: final reviewed release-level RNA-source label.

The workflow follows a reuse-first strategy. When an incoming
`RNA_Source_Pre` value matches a reviewed `Original_RNA_Source_Term`, the
corresponding `RNA_Source_Mapped` value is reused.

### `cell_line_model_reference.csv`

Cell-line model metadata reference used for confident cell-line name
standardization. Canonical names are obtained from `CellLineName` or
`StrippedCellLineName` when available. Additional fields such as `CCLEName`,
`ModelIDAlias`, `RRID`, and `ModelID` may be used for candidate matching and
audit information.

## Mapping workflow

For terms not present in the reviewed mapping table, the pipeline applies
deterministic cleanup rules and the RNA-source mapping prompt. Ambiguous or
low-confidence terms may be exported for review rather than forced into a
release-level category.

Final RNA-source labels are restricted to:

- `Tissue: xx`
- `Cells: xx`
- `Cell Line: xx`
- `Biofluid: xx`
- `Other`
- `null`

The reviewed mapping table is the reusable source of truth. New mappings
should be incorporated only after review.