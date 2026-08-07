Agent task: Model-type standardization

Standardize the `Model_Type` field according to the rules below. Preserve the input order and return one standardized value for each original term.


## General Requirements

- Preserve the original input order.
- Maintain a strict one-to-one correspondence between original and standardized terms.
- Do not skip, reorder, duplicate, split, or merge input rows.
- Apply only the field-specific rules defined below.

## Standardization Rules

1. Capitalization Consistency: The initial word of every term should be capitalized. All other words should follow title case, except for specific technical notations (e.g., Greek letters).
Examples:
'Allograft tail vein injection' → 'Allograft Tail Vein Injection'
'Chemical Induced Disease Model: Acetaminophen induced Liver Injury' → 'Chemical Induced Disease Model: Acetaminophen Induced Liver Injury'

2. Spelling Out Greek Letters: Fully spell out Greek letters or symbols in terms.
Examples:
'AdTGF-β1 induced Pulmonary Fibrosis' → 'AdTGFBeta Induced Pulmonary Fibrosis'
'Conditional Knockout: Ezh2' → 'Conditional Knockout: Ezh2'

3. Short Form to Full Form: Expand all abbreviations or acronyms into their full forms unless the short form is more commonly recognized in scientific literature.  
Examples:
'CDX' → 'Cell Line-Derived Xenograft'
'STZ' → 'Streptozotocin'

4. Uniform Terminology for Synonyms: Consolidate synonymous terms into a single standardized form.
Examples:
'Knock-In' and 'Knockin' → 'Knockin'
'Diabetes Mellitus' → 'Diabetes'

5. Format for Subcategories: Use the format 'Broad Category: Specifics' for clarity. Subcategories should be enclosed in parentheses when necessary.
Examples:
'Chemical Induced Disease Model: STZ Induced Type 1 Diabetes Mellitus' → 'Chemical Induced Disease Model: Streptozotocin Induced Diabetes (Type 1)'
'Chemical Induced Disease Model: Streptozotocin Induced Diabetic Cardiomyopathy' → 'Chemical Induced Disease Model: Streptozotocin Induced Diabetes (Cardiomyopathy)'

6. Consistency in Hyphenation and Spaces: Ensure consistent use of hyphens and spaces in compound words and phrases.
Examples:
'N-Butyl-N-(4-hydroxybutyl) nitrosamine induced Bladder Cancer' → 'N-Butyl-N-(4-hydroxybutyl)nitrosamine Induced Bladder Cancer'
'Chemical Induced Disease Model: AOM/DSS induced Colorectal Cancer' → 'Chemical Induced Disease Model: AOM-DSS Induced Colorectal Cancer'

7. Consolidation of Variants: Group variants of a term under a single standardized format where appropriate.
Examples:
'Chemical Induced Disease Model: Bleomycin induced Pulmonary Fibrosis' → 'Chemical Induced Disease Model: Bleomycin Induced Pulmonary Fibrosis'
 'Chemical Induced Disease Model: DSS induced Colitis' → 'Chemical Induced Disease Model: Dextran Sulfate Sodium Induced Colitis'

8. Clarity in Broad Categories: Preserve the broad category (e.g., 'Chemical Induced Disease Model') in all cases to ensure clarity.
Examples:
'Chemical Induced Disease Model: AOM DSS induced Colorectal Cancer' → 'Chemical Induced Disease Model: Azoxymethane-Dextran Sulfate Sodium Induced Colorectal Cancer'
'Chemical Induced Disease Model: DSS induced Ulcerative Colitis' → 'Chemical Induced Disease Model: Dextran Sulfate Sodium Induced Ulcerative Colitis'

9. Retain Meaningful Specific Details: Keep details that contribute to scientific understanding, such as chemical names, while simplifying overly complex descriptions.
Examples:
'Chemical Induced Disease Model: Alcohol Induced Liver Fibrosis' → 'Chemical Induced Disease Model: Ethanol Induced Liver Fibrosis'
'Chemical Induced Disease Model: AOM Induced Colon Cancer' → 'Chemical Induced Disease Model: Azoxymethane Induced Colon Cancer'

10. Final Format and Review: Ensure each term adheres to the standardized format 'Broad Category: Specifics' and aligns with scientific conventions.
Examples:
'Allograft orthotopic injection' → 'Allograft Orthotopic Injection'
'Chemical Induced Disease Model: LPS induced Sepsis' → 'Chemical Induced Disease Model: Lipopolysaccharide Induced Sepsis'
                       
## Output Requirements

Return exactly one standardized value for each original term.
Do not include explanations or additional commentary.

