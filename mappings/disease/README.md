# Disease Mapping Resources

This folder contains curated disease normalization and ontology mapping resources used in the GEOMeta Stage 3 disease mapping workflow.

## Files

### `disease_mapping_prompt.md`

Prompt guidance used for LLM-assisted disease normalization and CTD/MEDIC ontology mapping.

### `disease_mappings.xlsx`

Curated disease mapping table used by the Stage 3 workflow.

Columns:

- `Original_Raw_Disease_Term`: raw disease term extracted from GEO metadata.
- `Standardized_Disease_Term`: normalized disease term after post-processing and synonym standardization.
- `Final_Mapped_Disease_Term`: final reviewed disease concept used for ontology alignment.
- `DiseaseName`: canonical CTD/MEDIC disease name.
- `DiseaseID`: CTD/MEDIC disease identifier.
- `AltDiseaseIDs`: alternative ontology identifiers.
- `Definition`: disease definition from CTD/MEDIC when available.
- `ParentIDs`: parent ontology identifiers.
- `TreeNumbers`: ontology tree identifiers.
- `ParentTreeNumbers`: parent ontology tree identifiers.
- `Synonyms`: ontology synonyms.
- `SlimMappings`: higher-level ontology slim mappings.
- `Broad_Disease_Category`: curated higher-level disease category used for downstream analysis.

## Notes

Mappings were generated through iterative normalization, ontology matching, structured review, and manual refinement. The final mapped disease term and associated ontology fields should be treated as the authoritative disease annotation for downstream analyses.