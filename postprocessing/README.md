# Stage 2 Postprocessing Prompts

This directory contains prompt templates used during the GEOMeta Stage 2 postprocessing workflow.

## Purpose

Stage 2 performs field-level normalization and metadata standardization after initial extraction. These prompts are used to improve formatting consistency, reduce redundancy, normalize terminology, and prepare metadata fields for downstream ontology mapping and validation.

## Included Fields

- post_age.md
- post_disease.md
- post_ethnicity.md
- post_experimentsetting.md
- post_genotype.md
- post_modeltype.md
- post_organism.md
- post_outcome.md
- post_pert.md
- post_pertdose.md
- post_pertduration.md
- post_pertfreq.md
- post_race.md
- post_rnasource.md
- post_routeadmin.md
- post_sequencetype.md
- post_sex.md
- post_specimentype.md
- post_strain.md
- post_timepoint.md
- post_tissue.md

## Notes

Stage 2 prompts are designed for metadata normalization rather than ontology mapping. Controlled vocabulary mapping and ontology alignment are performed separately during Stage 3 processing.

These prompts support consistent annotation across heterogeneous GEO metadata submissions while preserving biologically relevant context when possible.