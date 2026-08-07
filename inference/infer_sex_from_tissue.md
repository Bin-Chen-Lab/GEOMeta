Agent task: Sex-from-tissue inference

Determine whether each standardized anatomical `Tissue` term provides sufficiently specific anatomical evidence to infer Sex. Preserve the input order and classify each term according to the rules below.

## General Requirements

- Preserve the original input order.
- Maintain a strict one-to-one correspondence between original and inferred
  categories.
- Infer Sex only from clearly sex-specific anatomical structures.
- Do not infer Sex from disease, diagnosis, cell-line identity, developmental
  stage, or general tissue type.
- When anatomical evidence is not sufficiently sex-specific, return `Neutral`.

## Inference Rules

### Male

Use `Male` only for clearly male-specific anatomical structures.

Examples:
- Testis → Male
- Prostate → Male
- Epididymis → Male
- Seminal Vesicle → Male
- Vas Deferens → Male
- Penis → Male

### Female
Use `Female` only for clearly female-specific anatomical structures.

Examples:
- Ovary → Female
- Uterus → Female
- Cervix → Female
- Vagina → Female
- Fallopian Tube → Female

### Neutral

`Neutral` indicates that no Sex inference should be made from the Tissue term. Use `Neutral` for anatomical structures that occur in both sexes or do not provide sufficient evidence for Sex inference.

Examples:
- Placenta → Neutral
- Embryo → Neutral
- Fetus → Neutral
- Heart → Neutral
- Liver → Neutral
- Brain → Neutral

## Output Requirements

Return exactly one category for each original Tissue term.
Use only `Male`, `Female`, or `Neutral`.
Do not include explanations or additional commentary.