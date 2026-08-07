Agent task: Sequence-type standardization

Standardize the `Seq_Type` field according to the rules below. Preserve the input order and return one standardized value for each original term.

## General Requirements

- Preserve the original input order.
- Maintain a strict one-to-one correspondence between original and standardized terms.
- Do not skip, reorder, duplicate, split, or merge input rows.
- Apply only the field-specific rules defined below.

## Standardization Rules

1. Unify All Variants to 'BULK-RNA':
- Regardless of spelling variation, typographical errors, or casing (e.g., 'BULRNA', 'BULULK-RNA', 'BULulk-RNA', 'BULNA', etc.), all terms representing bulk RNA sequencing must be standardized as 'BULK-RNA'.
- This includes abbreviations, partial terms, or common misspellings.

2. Remove Redundancies and Non-standard Variants:
- Any variant or alternate presentation of bulk RNA sequencing not matching 'BULK-RNA' exactly should be converted to 'BULK-RNA'.
- Disregard extraneous whitespace, dashes, or capitalization differences.

3. Retain Only 'BULK-RNA':
- In the standardized output, only the exact form 'BULK-RNA' should be present for all matching or similar terms.
- Any input term not related to bulk RNA sequencing should be flagged as 'NA'.

## Output Requirements

Return exactly one standardized value for each original term.
Do not include explanations or additional commentary.

## Output Examples:
Original Term  | Standardized Term 
BULRNA         | BULK-RNA          
BULULK-RNA     | BULK-RNA          
BULulk-RNA     | BULK-RNA          
BULNA          | BULK-RNA          
BULK-RNA       | BULK-RNA          
