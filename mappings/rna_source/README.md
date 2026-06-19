# RNA Source Mapping

This folder contains the reviewed RNA-source mapping resources used by the GEOMeta pipeline.

The main mapping file is RNA_Source_mappings.xlsx. This file must contain two required columns: Original_RNA_Source_Term and RNA_Source_Mapped.

The pipeline maps new RNA-source annotations from RNA_Source_Pre to RNA_Source_Mapped.

The mapping workflow follows a reuse-first strategy. If RNA_Source_Pre matches a reviewed term in Original_RNA_Source_Term, the corresponding RNA_Source_Mapped value is used directly. Blank values in RNA_Source_Mapped are intentional when the source term should not receive a final RNA-source label.

For new terms not found in the reviewed mapping file, the pipeline applies deterministic RNA-source cleanup rules. Unresolved terms are exported to a review queue for manual or LLM-assisted curation.

The optional cell-line reference file is cell_line_model_reference.csv. This file is used only for confident cell-line name standardization and should contain CellLineName and StrippedCellLineName.

The LLM/manual review prompt is rna_source_mapping_prompt.md. This prompt is used for reviewing new RNA-source terms before adding them permanently to RNA_Source_mappings.xlsx.

Final RNA-source labels should use one of the following formats: Tissue: xx, Cells: xx, Cell Line: xx, Biofluid: xx, Other, or blank/NA.

The reviewed mapping file is the source of truth. New mappings should only be added after review.
