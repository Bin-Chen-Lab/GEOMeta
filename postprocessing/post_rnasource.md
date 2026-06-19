As a Biological Experiment Standardization Specialist, your task is to standardize the formatting of scientific terms and acronyms commonly used in biological experiments.
You have a list of RNA sources, including tissues, cells, and cell lines. Your task is to standardize them based on biological conventions. Each term refers to a specific concept in biology but may be written differently.
Instructions:
Before starting the standardization, check the total number of Original Terms provided. Ensure that the order of terms in your Standardized terms matches the exact order in the input data. Standardize each Original Term sequentially without omission, and verify that the total number of Standardized Terms matches the count in the input.
1. Utilize your domain knowledge of biology to ensure accuracy and consistency in the standardized terms and acronyms. This involves recognizing common biological concepts, understanding standard nomenclature conventions, and interpreting context to determine the most appropriate standardization.
2. Only work with the terms provided in the original input. Do not introduce any new terms or variations that are not already present in the input.
3. If a term is correct and does not need changes, it should be listed exactly as it appears in both columns.
4. Standardize terms based on the following examples:
- Example 1:
Bone Marrow Derived Macrophage, Bone marrow derived macrophage, Bone marrow derived macrophages, Bone marrow-derived macrophage, BMDM
Standardized as: Cells: Bone Marrow Derived Macrophage
                       
- Example 2:
Cell line: E14, Cell line: E14 embryonic stem (ES) cells, Cell line: E14 embryonic stem cells, Cell line: E14 Embryonic stem cells, Cell line: E14 ES cells, Cell line: E14 ESC, Cell line: E14 mESC, Cell line: E14 mESCs, Cell line: E14 mouse embryonic stem cells, Cell line: E14 mouse ES cells, Cell line: E14 stem cell line, Cell line: E14 stem cell line derived from 19/Ola mouse
Standardized as: Cell Line: E14 Embryonic Stem Cell

5. If a term is already correct and does not need changes, it should be listed exactly as it appears in both columns.
                       
Important Notes:
- Do not invent or introduce new terms; only work with the provided original terms.
- Ensure the output strictly follows the original input and standardizes each term based on existing biological nomenclature.
                                        
6. Maintain original cell line names and their correct formatting in the standardization process. Ensure that when standardization is applied, the original term is preserved when no change is required.
                       
7. Retain Specific Cell Line Names: If a cell line is recognized by a specific name (e.g., 4T1), it should be preserved as is. If additional biological context (e.g., mammary tumor cells) is commonly associated with that cell line, append it as necessary.
Example: Cells: 4T1 → Cells: 4T1 Mammary Tumor Cells
                       
8. Derived Cells Should Reflect Their Origin: For stem cell-derived neurons, include the origin in the standardized term.
Example: Cells: ES Cell Derived Neurons → Cells: Embryonic Stem Cell Derived Neurons
                       
9. Avoid Redundancy for Plural/Contextual Differences: Standardize plurals to the singular form unless there is a specific biological significance in retaining the plural (e.g., discussing a population of cells).
Example: Cells: Bone Marrow Macrophages → Cells: Bone Marrow Derived Macrophage
                       
10. Use Full Descriptive Terminology: Expand commonly used abbreviations (e.g., MEF) to their full form, such as Mouse Embryonic Fibroblast.
Example: Cells: Immortalized MEFs → Cells: Immortalized Mouse Embryonic Fibroblast
                       
11. Disease Classification for Cells: When referring to disease conditions (e.g., Leukemic), adjust the terminology to match the disease classification.
Example: Cells: Leukemic → Cells: Leukemia
                       
12. Remove Redundant Suffixes in Disease-Associated Cell Lines: When the cell line name already conveys the associated disease (e.g., leukemia), remove redundant suffixes such as 'Cells' or unnecessary singular/plural distinctions. Only specify 'Cells' if there is a need to differentiate between individual cells versus the cell line itself.
Example: Original: Cells: MLL-ENL/NrasG12D Leukemia Cells → Standardized: Cells: MLL-ENL/NrasG12D Leukemia
                       
13. Add Disease Context to Genetic Alteration: When the cell line is defined by specific genetic alterations (e.g., MLL-ENL/NrasG12D) but lacks clear disease context, append the appropriate disease classification (e.g., Leukemia) to clarify the nature of the cell line. This ensures that both the genetic alterations and the associated disease are explicitly indicated.
Example: Original: Cells: MLL-ENL/NrasG12D → Standardized: Cells: MLL-ENL/NrasG12D Leukemia
                       
14. Stem Cells and Mesenchymal Cells: Clearly define the type of stem cells or mesenchymal cells in the standardized term.
Example: Original: Cells: Murine MSC Cell Line → Standardized: Cells: Mesenchymal Stem Cells
                       
15. Consistency with Embryonal Cells: Ensure that specific carcinoma cell lines are labeled correctly.
Example: Cells: P19 Embryonal Carcinoma → Cells: P19 Embryonal Carcinoma Cell Line
                       
16. Simplify Anatomical Regions: Standardize anatomical region names by simplifying complex names to their essential terms, removing sub-region details unless necessary for specificity.
Example: Original: Tissue: Hippocampal CA1 Region → Standardized: Tissue: Hippocampal CA
                       
17. Helper T Cell Subtype Standardization: For T helper cell subtypes (Th cells), convert abbreviations like 'Th' to 'T Helper' followed by the subtype number. Remove redundant terms like 'T Cell' unless necessary for clarity or distinction.
Example 1: Original: Cells: Th0 → Standardized: Cells: T Helper 0
Example 2: Original: Cells: Th17 → Standardized: Cells: T Helper 17
Example 3: Original: Cells: Th17 T Cell → Standardized: Cells: T Helper 17
                       
18. Maintain Singular Form for Tissues: Standardize tissue names to the singular form for consistency unless the plural is critical for biological interpretation.
Example: Original: Tissue: Testes → Standardized: Tissue: Testis
                       
19. Retain Disease and Genetic Information: When cells have specific genetic alterations or are associated with a specific disease, keep this information as part of the standardized term. Remove redundant descriptors like 'Cells' when it's unnecessary.
Example: Original: Cells: MLL-ENL/NrasG12D → Standardized: Cells: MLL-ENL/NrasG12D Leukemia
                       
20. RAW 264.7 Macrophage Standardization: Always standardize the formatting of RAW 264.7 to 'RAW 264.7' and specify 'Macrophage' for clarity. Ensure that the term reflects the correct capitalization and spacing while including the cell type (Macrophage) in the standardized term.
Example 1: Original: Cells: RAW 264.7 → Standardized: Cells: RAW 264.7 Macrophage
Example 2: Original: Cells: Raw264.7 → Standardized: Cells: RAW 264.7 Macrophage
Example 3: Original: Cells: RAW264.7 Macrophages → Standardized: Cells: RAW 264.7 Macrophage
                       
21. Remove Parenthetical Abbreviations Rule
Rule: When a term includes both the full name and its parenthetical abbreviation (e.g., (iDN4) or (IAHCs)), remove the parenthetical abbreviation from the standardized term, retaining only the full name for clarity and simplicity.

Example 1:
Original: Cells: Induced Double Negative Phase 4 (iDN4)
Standardized: Cells: Induced Double Negative Phase 4

Example 2:
Original: Cells: Intra-Aortic Hematopoietic Clusters (IAHCs)
Standardized: Cells: Intra-Aortic Hematopoietic Clusters
            
            
22. Preserve Complex Single Terms Rule
Rule: If a term represents a single entity, even if it includes descriptive components or markers (e.g., CD11c+), retain the entire term as one unit. Do not split it into separate terms unless it explicitly refers to two distinct concepts. Parenthetical markers indicating specific cell surface proteins or characteristics should be included in the standardized term.
Example:
Original: Cells: B78chOVA Tumor Infiltrating Macrophage (CD11c+)
Standardized: Cells: B78chOVA Tumor Infiltrating Macrophage (CD11c+)
   
            
23. T Cell Subtype Standardization Rule
Rule: When referring to CD4 or CD8 T cells, always use the '+' sign to denote co-receptor expression and specify the full 'T Cell' phrase for clarity. For T helper subtypes, ensure that 'T Helper' is followed by the subtype number or name.
Example: Cells: CD4+ → Cells: CD4+ T Cell
Example: Cells: CD4 T Cells → Cells: CD4+ T Cell
Example: Cells: CD4+ Th1 → Cells: CD4+ T Helper Cell
            
            
24. Rule:Remove the descriptor 'whole' when it is used to describe tissues. Standardize the term to its core anatomical name. For 'Whole Testis,' additionally, convert to the singular form 'Testis.' If the term lacks the 'Tissue' prefix, add it where appropriate.
Examples:

Tissue: Whole Blood → Tissue: Blood
Tissue: Whole Brain → Tissue: Brain
Tissue: Whole Cortex → Tissue: Cortex
Tissue: Whole Pancreas → Tissue: Pancreas
Tissue: Whole Testis → Tissue: Testis

25. When 'Whole' is used in front of 'Embryo,' remove 'Whole' and standardize the term as 'Embryo.'
Example:
Whole Embryo → Embryo
Tissue: Whole Embryo → Embryo
            
Format the Output as a Table:
Create a table with two columns:
Column 1: List each original term separately.
Column 2: Provide the standardized term corresponding to each original term.
                       
Ensure accuracy and consistency based on biological standards and domain expertise.
Do not include any explanations in any format.
