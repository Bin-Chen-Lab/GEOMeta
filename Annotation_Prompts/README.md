# Stage 1 Annotation-Agent Prompts

This directory contains the prompt templates and shared system instructions
used to configure the four task-specific Stage 1 annotation agents in the
GEOMeta pipeline.

In GEOMeta, an agent refers to an LLM invocation configured with task-specific
instructions, a defined GEO metadata context, restricted target fields, and a
structured output contract. The Markdown files in this directory provide the
reusable instructions for these agent calls; they are not standalone
autonomous agents.

## Included Prompt Templates

- `biological_context_prompt.md`  
  Extracts disease-related biological context.

- `experimental_context_prompt.md`  
  Extracts sequencing, RNA-library, RNA-source, tissue, experimental-setting,
  model-type, and related technical or experimental attributes.

- `perturbation_prompt.md`  
  Extracts study- and sample-level perturbation status, perturbation identity,
  dose, duration, frequency, and route of administration.

- `sample_metadata_prompt.md`  
  Extracts age, sex, race, ethnicity, sample type, specimen type, timepoint,
  outcome, and related sample-level attributes.

- `stage1_common_system_prompt.md`  
  Provides shared system-level instructions, formatting requirements, and
  structured-output constraints used across the four Stage 1 annotation agents.

## Notes

For each GEO metadata batch, the four annotation agents receive the same
GSE-level and GSM-level context but operate on different restricted sets of
target fields. Their structured outputs are subsequently validated and merged
into one annotation record per GSM–GSE pair.