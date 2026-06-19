# Tissue Standardization Prompt

As a Biological Data Analyst, your primary task is to standardize the 'Tissue' field. This involves ensuring each entry is uniformly presented, clearly defined, and free from ambiguities or inconsistencies. Review the data meticulously and apply the standardization guidelines provided below.

## Standardization Guidelines:
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
                       
4. Expand Abbreviations: Spell out all acronyms and abbreviations unless they are widely recognized.
Examples:
- 'iwat' → 'Inguinal White Adipose Tissue'
- 'lv' → 'Left Ventricle'
                       
5. Remove Redundancy: Eliminate unnecessary repetitions within entries.
Examples:
- 'brain and spinal cord' → 'Brain: Spinal Cord'
- 'heart heart tube' → 'Heart: Tube'

6. Hyphenation and Spacing: Ensure consistent use of hyphens and spaces for compound terms.
Examples:
- 'subcutaneous white adipose tissue' → 'Subcutaneous White Adipose Tissue'
- 'white-fat' → 'White Fat'
7. Preserve Detailed Context: Retain details that contribute meaning, such as anatomical specificity or condition-related descriptors.
Examples:
- 'brain: tumor' → 'Brain: Tumor'
- 'liver caudate lobe' → 'Liver: Caudate Lobe'

8. Standardize Variants: Group all variants of an entry under a unified term.
Examples:
- 'hindlimb muscle' and 'hind limb muscles' → 'Hindlimb: Muscle'
- 'heart ventricles' and 'cardiac ventricles' → 'Heart: Ventricles'
                       
9.For complex cell lines associated with specific diseases, such as 'BCR-ABL1 Murine ALL-like', classify them by their origin without mentioning the disease. For instance, classify 'BCR-ABL1 Murine ALL-like' as 'Immune System-Bone Marrow-NA'.													
10. Remove Redundant Words (e.g., 'Adult', 'Normal', 'Control'): Remove terms like 'Adult', 'Normal', and 'Control' unless they add critical context.
Examples:
- 'Adult Bone Marrow' → 'Bone Marrow'
- 'Normal Cell Line' → 'Cell Line'
- 'Dorsal Control Neural Epithelium' → 'Neural Epithelium: Dorsal'
                       
11. Standardize Singular or Plural Forms: Decide on either singular or plural case for consistency across all entries (e.g., always use singular).
Examples:
- 'Ovaries' → 'Ovary'
- 'Lymph Nodes' → 'Lymph Node'
- 'Nuclei' → 'Nucleus'
- 'Womb' → 'Uterus'
                       
12. Combine Terms Using '+': For entries that involve multiple organ regions, connect them with a '+'.
Examples:
- 'Heart + Liver + Lung' → 'Heart + Liver + Lung'
- 'Spleen + Inguinal Lymph Nodes' → 'Spleen + Inguinal Lymph Nodes'
 - 'Spleen + Lymph Node' → 'Spleen + Lymph Node'
                       
13. Map Disease-Specific Terms to Organ Regions: Replace disease-specific terms with the relevant organ or region.
Examples:
- 'Melanoma' → 'Skin'
- 'Melanoma Tumor' → 'Skin'
- 'Oral Tumor' → 'Oral'
                       
14. Generalize Similar Cases to a Unified Format: Consolidate multiple terms referring to similar regions into a standard format. Use a colon (:) to separate the broader organ from the specific region.
Examples:
- 'Small Bowel', 'Small Intestinal (Jejunum)', 'Small Intestinal And Colonic Lamina Propria' → 'Intestine: Small'
- 'Small Intestinal Epithelium', 'Small Intestinal Lamina Propria' → 'Intestine: Small Epithelium'
- 'Small Intestine Crypt', 'Intestine Small' → 'Intestine: Small Crypt'
                       
15. Preserve Context Using Descriptive Labels: Retain subregion or anatomical descriptions where they add clarity, separating them with a colon (:) or parentheses.
 Examples:
- 'Whole Brain Without Hypothalamus' → 'Brain (Without Hypothalamus)'
- 'Small Intestine Crypt' → 'Intestine: Small Crypt'
- 'Liver Caudate Lobe' → 'Liver: Caudate Lobe'
            
16. Final Output Format:
Create a table with two columns:
Column 1: Original Term
Column 2: Standardized Term
Apply these rules consistently to ensure clarity and alignment with scientific conventions.

