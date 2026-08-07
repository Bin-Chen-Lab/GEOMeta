# Stage 2 Field-Standardization Prompts

This directory contains the prompt templates used by the 21 field-specific standardization agent tasks in Stage 2 of the GEOMeta pipeline. 

The Markdown files contain reusable task instructions and are not standalone autonomous agents. At runtime, each template is combined with the relevant field values, structured-output requirements, validation procedures, and the configured LLM backend. Each prompt template configures one field-specific standardization agent task. At runtime, the task combines the reusable prompt, candidate terms from one metadata field, field-restricted instructions, and a structured output contract.

## Purpose

Stage 2 performs field-level normalization and standardization after initial metadata extraction. The standardization tasks harmonize terminology, abbreviations, units, capitalization, formatting, and naming variants while preserving biologically relevant information supported by the source metadata.

## Included Fields

- `post_age.md`
- `post_disease.md`
- `post_ethnicity.md`
- `post_experimentsetting.md`
- `post_genotype.md`
- `post_modeltype.md`
- `post_organism.md`
- `post_outcome.md`
- `post_pert.md`
- `post_pertdose.md`
- `post_pertduration.md`
- `post_pertfreq.md`
- `post_race.md`
- `post_rnasource.md`
- `post_routeadmin.md`
- `post_sequencetype.md`
- `post_sex.md`
- `post_specimentype.md`
- `post_strain.md`
- `post_timepoint.md`
- `post_tissue.md`

## Notes

Stage 2 standardization reduces variation in extracted metadata values before controlled-vocabulary and external-resource mapping. Ontology alignment and reference-resource mapping are performed separately during Stage 3.

For selected fields, raw extracted values and standardized values are retained separately to support traceability and stage-specific review.