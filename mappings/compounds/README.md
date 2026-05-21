# Compound Mapping Resources

This folder contains compound and perturbation normalization resources used in the GEOMeta Stage 3 chemical compound mapping workflow.

## Files

### `cp_mapping_prompt.md`

Prompt guidance used for compound normalization and PubChem query generation.

### `compound_pubchem_mappings.xlsx`

Curated compound mapping table used by the Stage 3 workflow.

Columns:

- `Original_Raw_Compound_Term`: raw perturbation term before standardization.
- `Standardized_Compound_Term`: normalized perturbation term used for compound mapping.
- `Final_Mapped_Compound_Name`: final reviewed PubChem-matched compound name.
- `CID`: PubChem compound identifier.
- `MatchType`: type of PubChem match.
- `CanonicalSMILES`: canonical SMILES retrieved from PubChem.
- `PubChemURL`: PubChem compound page.

## Notes

Compound mappings normalize raw perturbation terms by resolving synonyms, abbreviations, naming variants, and manually reviewed compound matches.

The standardized compound term is used as the primary query term for PubChem mapping, while the final mapped compound name represents the reviewed PubChem-aligned compound annotation used by GEOMeta.

Only compound-level mappings are included here. Non-chemical perturbations, ambiguous treatment descriptions, and unmapped terms may contain empty PubChem-related fields.