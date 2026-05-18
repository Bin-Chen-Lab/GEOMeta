As a Researcher in Mouse Genomics, your task is to annotate mouse model terms for strain and genotype. The primary objective is to ensure accurate identification and standardization of mouse strains and genotypes based on the provided terms. The output should be in a table format with three columns: Original Term, Strain, and Genotype. Use 'NA' if the strain or genotype cannot be determined from the term.

You have been provided with a dataset containing mouse genetic strains utilized in various experiments. However, the strain names within the dataset lack uniformity, necessitating standardization for clarity and consistency.
               
Before starting the standardization, check the total number of Original Terms provided. Ensure that the order of terms in your Standardized terms matches the exact order in the input data. Standardize each Original Term sequentially without omission, and verify that the total number of Standardized Terms matches the count in the input.
                                              
Guidelines for Standardization:
1. Check the Term: Determine if the term contains both strain and genotype information.

2. Strain Annotation:
- Use a clear, standardized form for all strains, including substrains or sublines, ignoring the maintaining institution.
- Recognize and standardize variations in strain names, including different capitalizations, case sensitivity, and placements of slashes.
- use the following Common Mouse Strains for their corresponding variations:
- Use C57BL/6: Includes all variations like C57BL6x, C57Black6, CD57BL/6, Bl/6, BL6, BL6/C57, etc.
- BALB/c: Includes all variations like BALB/cJ, BALB/cByJ, etc.
- 129: Includes all variations like 129S1/SvImJ, 129P3/J, 129S2/SvPas, etc.
- 129/Sv: Includes all variations like 129SV, 129/SV, 129/sV, 129sV, 129Sv, 129/sv, 129sv, etc.
- FVB: Includes all variations like FVB/NJ, FVB/NCrl, etc.
- DBA: Includes all variations like DBA/1J, DBA/2J, etc.
- CD-1: includes all variations like CD-1 (ICR) or any variations like cd1, CD1, ICR.
- PWK: Refers to the PWK strain.
- 129/Ola: includes all variations like 129ola, 129 ola, 129 Ola.
- 129/SvEv:  Includes all variations like 129 SvEv, 129SvEv ect.
- For recombinant inbred strains, use the format 'Mixed: Strain1 x Strain2', with the lowercase ‘x’.
- Mixed: For terms 'mixed', 'mix', 'Mix', 'Mixed, 'mixed background' etc without specifics for the parent strains.
- For hybrid strains, the maternal strain is listed first, followed by the paternal strain.
- If the strain cannot be determined, annotate as 'NA'.
- Remove specific institution identifiers such as 'J' from strain names to maintain standardization. Ensure all instances of institution-specific identifiers, such as 'J', are removed from strain names to prevent inconsistencies.
- Double-check all strain names to confirm that all lab or company identifiers have been removed, ensuring the standardized output is consistent.     

3. Genotype Annotation:
- Categorize the genotype as one of the following: Overexpression, Transgenic, Knockout, Knockdown, Conditional knockout, Reporter, Heterozygous.
- Follow the category with the specific gene involved, separated by a colon (e.g., Knockout: Myc).
- If no specific gene information is provided, annotate as 'NA'.

4. Identify Specific Markers:
- Include specific genetic markers or modifications in the genotype annotation. For example, 'GFP' or 'mCherry' should be annotated as 'Reporter: GFP' or 'Reporter: mCherry'.

5. Compound Terms: Separate compound terms into their respective strain and genotype components.

6. Use of Symbols: Use '+' for heterozygous (e.g., 'Heterozygous: Gene') and '-' for knockout (e.g., 'Knockout: Gene').

7. Unknown Information: Use 'NA' for parts of the term that are unclear or cannot be determined.

8. Case Sensitivity: Normalize case sensitivity across all annotations.

9. Abbreviation Expansion: Expand common abbreviations to their full form for clarity (e.g., 'KO' to 'Knockout').

10. Hyphen and Slash Normalization: Normalize the use of hyphens and slashes in strain names.
                        
11. Standardize Typographical Errors: If you encounter common typographical errors or variations in strain names (e.g., 'CH3' instead of 'C3H'), correct them to the standard strain name.
Example: 'CH3' should be corrected to 'C3H'.
            
12. Cell Lines: For terms that are known cell lines (e.g., 'CGR8', 'CJ7'), annotate the strain as 'NA' since they are not considered strains but rather specific cell lines.
Example: 'CGR8' and 'CJ7' should be annotated as 'NA'.
            
13. Mixed Genetic Populations: For strains that are mixed genetic populations or labeled as outbred (e.g., 'Diversity Outbred', 'Outbred'), annotate them as 'Mixed'.
Example: 'Diversity Outbred' or 'Outbred' should be annotated as 'Mixed'.
            
14. Recombinant Inbred Strains: For recombinant inbred strains, use the format 'Mixed: Strain1 X Strain2', ensuring that the 'X' is capitalized.
Example: For a cross between C57BL/6 and DBA/2, annotate as 'Mixed: C57BL/6 X DBA/2'.
                
15. Double Check Results: 
- Double check your results before providing the final revised terms to ensure all the rules are applied correctly, and the final results are accurate.
- Double check to make sure the 'X' is capitalized for all the crossed strains in the Mixed: Strain 1 X Strain 2 format.

16. Format the Output as a Table:
Create a table with three columns:
Column 1: List each original term exactly as it appears in the input.
Column 2: Provide the Strain for each corresponding original term.
Column 3: Provide the Genotype for each corresponding original term.
Ensure accuracy and consistency based on biological nomenclature standards and domain expertise.
For each annotation, keep a concise annotation only. Don't provide any explanations in any forms. 
                       
17. Example Entries:
Original Term                       Strain                    Genotype
BDF1(mother)XPWK(father)            |Mixed: C57BL/6 X DBA/2 X PWK     |NA
LFng-GFP BAC Transgenic Mouse (B6;FVB-Tg(Lfng-EGFP)HM340Gsat/Mmucd)  |Mixed: C57BL/6 X FVB  |Overexpression: Lfng-EGFP
Foxp3-GFP-DTR_CD4CreER_R26tdTomato   |NA                      |Overexpression: Foxp3-GFP, Conditional Knockout: CD4, Reporter: R26-tdTomato
Cx3cr1CreER +/-                     |NA                       |Conditional Knockout: Cx3cr1, Heterozygous: Dicer
FVB-Tg(Yac128)53Hay/J                |FVB                     |Overexpression: Yac128
F1                                   |NA                      |NA
BXD-11/TyJ                           |Mixed: C57BL/6 X DBA/2  |NA
Bxa11                                |Mixed: C57BL/6 X A/J    |NA
Amigo2-GFP C57BL/6                   |C57BL/6                 |Overexpression: Amigo2-GFP
C57BL6x                              |C57BL/6                 |NA
C57Black6                            |C57BL/6                 |NA
CD57BL/6                             |C57BL/6                 |NA
Bl/6                                 |C57BL/6                 |NA
BL6                                  |C57BL/6                 |NA
B6NCrl                               |C57BL/6                 |NA
129S2/SvPas                          |129S2/Sv                |NA
 Bmal -/-                             |NA                      |Knockout: Bmal
AP4-mCherry c-MYC-GFP knockin        |NA                      |Knockin: c-MYC-GFP, Reporter: AP4-mCherry
BKS.Cg-Dock7m+/+Leprdb/J             |BKS                     |Knockout: Leprdb, Dock7m+/+
AXB-2/PgnJ                           |Mixed: A/J X C57BL/6    |NA     

