Agent task: Experimental-setting standardization

Standardize the `Experimental_Setting` field according to the rules below. Preserve the input order and return one standardized value for each original term.

## General Requirements

- Preserve the original input order.
- Maintain a strict one-to-one correspondence between original and standardized terms.
- Do not skip, reorder, duplicate, split, or merge input rows.
- Apply only the field-specific rules defined below.

## Standardization Rules

1. Canonical Categories Only: All entries must be mapped to one of the following exact canonical terms: In Vitro, In Vivo, or Ex Vivo.

2. Fix Malformed Variants: Map any spelling mistakes, inconsistent casing, malformed phrases, or fused variants logically.
Examples:
in vivo → In Vivo
In Vit Vitro → In Vitro
In VitVitro → In Vitro

3. Title Casing: All standardized terms must follow Title Case. For example, use In Vivo instead of in vivo.

4. Fallback to NA: If a term does not confidently match one of the three valid categories, standardize it as NA.

## Output Requirements

Return exactly one standardized value for each original term.
Do not include explanations or additional commentary.


