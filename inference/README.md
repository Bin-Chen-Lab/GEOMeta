# Stage 2 Controlled-Inference Prompts

This directory contains the prompt templates used by the three controlled-inference agent tasks in Stage 2 of the GEOMeta pipeline.

These tasks derive secondary annotations from standardized metadata using predefined rules and constrained output categories. The Markdown files contain reusable task instructions and are not standalone autonomous agents.

## Included Tasks

- `derive_agegroup_from_age.md`  
  Derives standardized age-group labels from standardized biological or developmental age annotations.

- `infer_perturbation_type.md`  
  Classifies standardized perturbation terms into predefined perturbation categories.

- `infer_sex_from_tissue.md`  
  Performs restricted sex inference from clearly sex-specific anatomical context when directly reported sex information is unavailable.

## Notes

Controlled inference is limited to fields for which explicit derivation rules and constrained output categories are defined. These tasks do not replace directly reported metadata with unsupported inferred values.