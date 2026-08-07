Agent task: Tissue standardization

Standardize the `Tissue` field according to the rules below. Preserve the input order and return one standardized value for each original term.

## General Requirements

- Preserve the original input order.
- Maintain a strict one-to-one correspondence between original and standardized terms.
- Do not skip, reorder, duplicate, split, or merge input rows.
- Apply only the field-specific rules defined below.

## Standardization Rules

1. Consistent Capitalization: Capitalize the first letter of every word. Maintain title case for organ and region names.
Examples:
- 'adrenal gland' → 'Adrenal Gland'
- 'hippocampus: dentate gyrus' → 'Hippocampus: Dentate Gyrus'
                       
2. Avoid Synonyms: Use a single standard term for synonyms.
Examples:
- 'ear pinnae' and 'auricle' → 'Ear'
- 'brown adipose tissue' and 'brown fat' → 'Brown Adipose Tissue'
                       
3. Subcategory Consistency: Use the format 'Organ: Subregion' to specify subcategories clearly.
Examples:
- 'brain: hippocampus: dentate gyrus' → 'Brain: Hippocampus: Dentate Gyrus'
- 'heart left ventricle' → 'Heart: Left Ventricle'
- 'brain and spinal cord' → 'Brain: Spinal Cord'
                       
4. Expand Abbreviations: Spell out all acronyms and abbreviations unless they are widely recognized.
Examples:
- 'iwat' → 'Inguinal White Adipose Tissue'
- 'lv' → `Heart: Left Ventricle` only when the anatomical context clearly indicates the cardiac left ventricle.
                       
5. Remove Redundancy: Eliminate unnecessary repetitions within entries.
Examples:
- 'heart heart tube' → 'Heart: Tube'

6. Hyphenation and Spacing: Ensure consistent use of hyphens and spaces for compound terms.
Examples:
- 'subcutaneous white adipose tissue' → 'Subcutaneous White Adipose Tissue'
- 'white-fat' → 'White Fat'

7. Preserve Detailed Context: Retain details that contribute meaning, such as anatomical specificity or condition-related descriptors.
Examples:
- 'brain: tumor' → 'Brain'
- 'liver caudate lobe' → 'Liver: Caudate Lobe'

8. Standardize Variants: Group all variants of an entry under a unified term.
Examples:
- 'hindlimb muscle' and 'hind limb muscles' → 'Muscle: Hindlimb'
- 'heart ventricles' and 'cardiac ventricles' → 'Heart: Ventricles'
                       							
9. Remove Redundant Words (e.g., 'Adult', 'Normal', 'Control'): Remove terms like 'Adult', 'Normal', and 'Control' unless they add critical context.
Examples:
- 'Adult Bone Marrow' → 'Bone Marrow'
- 'Normal Cell Line' → 'NA'
- 'Dorsal Control Neural Epithelium' → 'Neural Epithelium: Dorsal'
                       
10. Standardize Singular or Plural Forms: Decide on either singular or plural case for consistency across all entries (e.g., always use singular).
Examples:
- 'Ovaries' → 'Ovary'
- 'Lymph Nodes' → 'Lymph Node'
- 'Nuclei' → 'Nucleus'
- 'Womb' → 'Uterus'
                       
11. Combine Terms Using '+': For entries that involve multiple organ regions, connect them with a '+'.
Examples:
- 'Heart + Liver + Lung' → 'Heart + Liver + Lung'
- 'Spleen + Inguinal Lymph Nodes' → 'Spleen + Inguinal Lymph Nodes'
- 'Spleen + Lymph Node' → 'Spleen + Lymph Node'
                       
12. Disease-Associated Terms
Do not infer Tissue solely from a disease name unless the anatomical origin is explicitly stated or unambiguous in the original term. Remove disease-state descriptors when a clear anatomical tissue is already present.
Examples:
- Liver Tumor → Liver
- Brain Tumor → Brain
- Breast Carcinoma Tissue → Breast
If the term contains only a disease label without a supported anatomical origin, do not guess the Tissue.
                       
13. Standardize Anatomical Hierarchy
Use a colon (`:`) to represent progressively more specific anatomical subregions. Preserve all explicitly stated anatomical information and do not introduce a subregion that is not present in the original term.

Examples:
- `Small Bowel` → `Intestine: Small`
- `Small Intestinal` → `Intestine: Small`
- `Small Intestinal Jejunum` → `Intestine: Small: Jejunum`
- `Small Intestinal Epithelium` → `Intestine: Small: Epithelium`
- `Small Intestinal Lamina Propria` → `Intestine: Small: Lamina Propria`
- `Small Intestine Crypt` → `Intestine: Small: Crypt`
- `Small Intestinal and Colonic Lamina Propria` → `Intestine: Small: Lamina Propria + Colon: Lamina Propria`
                       
14. Preserve Context Using Descriptive Labels: Retain subregion or anatomical descriptions where they add clarity, separating them with a colon (:) or parentheses.
 Examples:
- 'Whole Brain Without Hypothalamus' → 'Brain (Without Hypothalamus)'
- 'Small Intestine Crypt' → 'Intestine: Small Crypt'
- 'Liver Caudate Lobe' → 'Liver: Caudate Lobe'
            
## Output Requirements

Return exactly one standardized value for each original term.
Do not include explanations or additional commentary.