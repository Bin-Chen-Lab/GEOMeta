# Stage 3 Mapping Prompts and Resources

This directory contains the prompts, controlled vocabularies, external
reference files, and reviewed reusable mapping resources used during Stage 3
of the GEOMeta pipeline.

Stage 3 mapping agents link standardized metadata values to controlled
vocabularies or external reference resources. The mapping prompt files provide
task-specific instructions and are used together with candidate terms,
reference records, structured-output requirements, and review procedures;
they are not standalone autonomous agents.

## Subdirectories

### `disease/`

Disease mapping prompts and reviewed resources based primarily on CTD MEDIC
disease concepts, ontology identifiers, and curated broad disease categories.

### `tissue/`

Tissue mapping prompts, controlled tissue categories, and reviewed mappings
derived primarily from Human Protein Atlas tissue categories, supported brain
subregions, and additional curated anatomical categories.

### `compounds/`

Chemical-perturbation mapping prompts and reviewed compound mappings used for
PubChem name, CID, and structural-descriptor assignment.

### `rna_source/`

RNA-source mapping prompts, reviewed RNA-source mappings, and cell-line
reference records used to assign standardized tissue, cell, cell-line,
biofluid, or other source labels.

## Notes

Reviewed mappings are reused before new mapping attempts are performed.
Previously unseen, ambiguous, or low-confidence terms may be retained in
field-specific review queues rather than being forced into unsupported
controlled-vocabulary assignments.

These resources are provided to support reproducibility, ontology
harmonization, auditability, and reuse across GEOMeta annotation runs.