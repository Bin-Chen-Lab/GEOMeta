# Tissue Mapping Resources

This folder contains tissue and organ standardization resources used in the GEOMeta Stage 3 tissue mapping workflow.

## Files

### `tissue_mapping_prompt.md`

Prompt guidance used for controlled tissue mapping. The prompt maps tissue and organ-region terms to Human Protein Atlas-derived tissue categories, supported brain subregions, and additional curated tissue categories used in GEOMeta.

### `tissue_mappings.xlsx`

Curated tissue mapping table used by the Stage 3 workflow.

Columns:

- `Original_Tissue_Term`: raw extracted tissue or organ-region term.
- `Standardized_Tissue_Term`: normalized tissue term generated during initial standardization.
- `Final_Mapped_Tissue_Term`: final reviewed tissue category used by GEOMeta.

## Notes

Mappings are based primarily on Human Protein Atlas tissue categories, with selected brain subregion handling. Additional curated categories were added for recurrent GEO tissue descriptors not adequately represented by the core HPA categories, including blood- and upper airway-related terms.

The final mapped tissue category should be treated as the authoritative tissue annotation for downstream analysis.