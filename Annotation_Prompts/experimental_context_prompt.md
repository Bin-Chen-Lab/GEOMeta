Role: Experimental Context
Annotate only the following fields for each GSM sample in this role:
GSM_ID, GSE_ID, Seq_Type, Organism, Strain, Genotype, RNA_Library, RNA_Source, Tissue, Experimental_Setting, Model_Type. Do not annotate any other fields in this role.

1. GSM_ID: The unique identifier for the sample within the GEO database.

2. GSE_ID: The GEO Series ID associated with the sample.

3. Seq_Type: Determine the sequencing type for each sample and annotate it using one of the following categories. All RNA-seq samples must fall into exactly one of these three labels - no spelling variations, hyphens, or extra terms are permitted.
- (1) SC-RNA: Mentions of 'single-cell', 'scRNA-Seq', 'single-nucleus', 'RNA-Seq', etc. Use technologies or methods like '10x Genomics', 'Fluidigm C1', 'SMART-Seq', 'Droplet-based', 'Microfluidics', 'CEL-Seq'. Phrases indicating individual cell analysis, such as 'cell count: 1', 'cells sorted into individual wells/droplets', 'isolation of single cells/nuclei'. Focus on cellular heterogeneity, individual cell types, or single-cell resolution. Never deviate from SC-RNA (no variants like SC RNA, Single-cell RNA, or scRNA-Seq)
- (2) BULK-RNA: General terms like 'Bulk-RNA' without mention of single-cell techniques. Mentions of 'Population': If the sample refers to a 'population' of cells (e.g., 'HSC population', 'CLP population'), classify it as BULK-RNA. References to tissues, organs, cell lines, biopsies, or cell populations (e.g., 'RNA extracted from tissue', 'pooled cells'). Always use the capitalized BULK-RNA (avoid variations like BULRNA, BULAIN-RNA, BULNA, etc.). 
- (3) Other: Any samples not belong to either SC-RNA or BULK-RNA. For techniques, such as 'ChIP-Seq', 'ATAC-Seq', 'DNA-Seq', 'WGS', 'Exome-Seq', 'Methyl-Seq', 'Hi-C', 'CLIP-Seq', 'Ribo-Seq', 'Bisulfite Sequencing', which are unrelated to RNA expression profiling, use 'Other' instead. Always label these as Other. Do not create sub-variants like RIBO-RNA, DNA-Seq, or RNA-other.
Some Examples:
If the metadata says 'This is a single-cell RNA-seq experiment using 10x Genomics,' → SC-RNA.
If the metadata says 'bulk RNA-seq of whole liver tissue,' →  BULK-RNA.
If the metadata says 'ChIP-seq of histone marks,' → Other.
Finally, do not add extra descriptors such as 'BULK-RNA-seq,' 'SC-RNA (10x Genomics),' or 'BULKRNA.' Stick to the three exact strings: SC-RNA, BULK-RNA, or Other.

4. Organism: The species or organism from which the sample was derived. Always use 'Genus species' in proper scientific form, e.g.: Homo sapiens (for human), Mus musculus (for mouse), Rattus norvegicus (for rat) etc.
- No Extra Words or Repetitions: Avoid invalid entries like 'Homo sapi sapiens' or 'Homo sapiensis'. If the sample is human, it must be 'Homo sapiens' exactly.
- Capitalization Matters: Genus (first word) capitalized; species (second word) lowercase. Do not add trailing letters or punctuation.
- Edge Cases: If the organism is ambiguous or missing, annotate as NA (but only if it truly cannot be determined).
- Do not add terms like (human), (mouse model), or (Escherichia coli strain K12). Just the pure binomial name.

5. Strain: Provide the specific strain or background information associated with the sample. Use the expanded and fully interpreted strain names in the final annotation, based on information from either the GSE or GSM record. The expanded information itself should not be included in the final annotation.
- Use the exact strain name provided in the record, fully expanded where necessary (e.g., C57BL/6J, BALB/c). Do not include any genetic variation or genotype details in this field; those belong in the genotype annotation.
- Mixed Populations: Annotate mixed populations like 'Heterogeneous stock-collaborative cross', 'Diversity outbred' as 'Mixed' if the exact strains involved are unclear.
- Crossed Strains: If the strain is a cross, specify it in the format using the capital 'X': 'Mixed: Strain1 X Strain2' using the expanded strain names.
- Handling Abbreviations: Expand abbreviations to their full strain names for the final annotation. Example: Given 'B6J.129S6-Actl6b<tm1Grc>', expand to 'B6J stands for C57BL/6J, 129S6 stands for 129S6/SvEvTac,' and annotate as 'Mixed: C57BL/6J X 129S6.'
- Strain with Embedded Genotype Information: Annotate the strain fully expanded without including genotype details. So 'B6J.129S6-Actl6b<tm1Grc>' should be annotated as 'Mixed: C57BL/6J X 129S6.' excluding genotype related information '-Actl6b<tm1Grc>'.
- Annotate as 'NA' when no strain details are provided.
Example Annotations:
Given: B6J.129S6-Actl6b<tm1Grc>
Final Annotation: Mixed: C57BL/6J X 129S6

6. Genotype
 'Genotype' refers to the genetic constitution of the organism or cell line. This includes wild-type, mutants, knockouts, knockins, transgenics, knockdowns, overexpressions, or vague genetic modifications.
 (1). Standardized Genotype Annotation Format:
 Use a consistent structure: 'Knockdown: [Gene]', 'Knockin: [Gene]', 'Knockout: [Gene]', 'Mutant: [Gene Mutation]', 'Transgenic: [Gene]', 'Overexpression: [Gene]', or 'WT' for wild-type.
For unspecified genetic modifications described as 'genetically modified' without details, annotate as 'Genetically modified (unspecified)'.
Remember that 'WT' and 'Genetically modified (unspecified)' are the only placeholders to use when the specific gene or modification detail cannot be determined from the metadata.

 (2). Annotation Workflow:
 Step 1: Extract Genotype Descriptions. Check GSE summaries and GSM metadata for terms like 'knockout', 'knockin', 'mutation', 'transgene', 'overexpression'.
 Step 2: Map to Standardized Format. For example, 'P53 knockout' → 'Knockout: P53', 'KRAS G12D mutation' → 'Mutant: KRAS G12D', 'EGFP transgene' → 'Transgenic: EGFP'.
 Step 3: Handle Multiple Modifications. If multiple modifications exist, separate them with a semicolon. For example, 'P53 knockout, KRAS G12D mutation' → 'Knockout: P53; Mutant: KRAS G12D'.
 Step 4: Unclear or Missing Genotype. If genotype is not mentioned or unclear, annotate as 'NA'.

 (3). Examples for Different Scenarios:
 Example 1: Single Knockout. GSM metadata: 'P53 knockout' → 'Knockout: P53'.
 Example 2: Mutation. GSM metadata: 'KRAS G12D mutation' → 'Mutant: KRAS G12D'.
 Example 3: Transgene. GSM metadata: 'EGFP transgene' → 'Transgenic: EGFP'.
 Example 4: Knockdown. GSM metadata: 'P53 knockdown' → 'Knockdown: P53'.
 Example 5: Multiple Modifications. 'P53 knockout, KRAS G12D mutation' → 'Knockout: P53; Mutant: KRAS G12D'.
 Example 6: Unknown Genotype. 'genotype: Not reported' → 'NA'.

 (4). Edge Cases:
  Non-Specific Descriptions: 'genetically modified' → 'Genetically modified (unspecified)'.
 Wild-Type Samples: Any mention of 'wt', 'WT', 'wild-type' or similar → 'WT'.

7. RNA_Library: Specify the type of RNA library used for sequencing by choosing the most appropriate category from the list provided below , and ensure that the exact spelling and case are used without introducing any variations or special characters. When determining the RNA library type, consider the specific kit used and the description provided in the GSM information. The categories are:

- mRNA-based: Select this category when the library preparation involves the selection or enrichment of RNA molecules with a polyadenylated (Poly(A)) tail, specifically targeting mature mRNA transcripts while excluding other RNA species like ribosomal RNA and non-coding RNA. This category is typically associated with kits like the TruSeq RNA Sample Preparation Kit. Keywords: Poly(A) selection, mRNA enrichment, oligo(dT) beads.

- rRNA-depleted: Use this category when the library preparation method involves the depletion of ribosomal RNA (rRNA) to allow for the sequencing of a broader range of RNA species, including both mRNA and various non-coding RNAs. Kits like the TruSeq Stranded Total RNA Sample Preparation Kit and TruSeq Ribozero Gold fit here. Keywords: rRNA depletion.

- Noncoding RNA: Choose this category if the library preparation specifically targets non-coding RNAs, such as microRNAs, long non-coding RNAs, or other small RNA species. Kits like the TruSeq Small RNA Library Prep Kit fall under this category. Keywords: miRNA, small RNA, noncoding RNA, IncRNA.

- Riboseq: Select this category if the assay type is specifically ribosome profiling, which involves sequencing ribosome-protected mRNA fragments to study translation. Keywords: Riboseq, ribosome profiling, ribosome-protected fragments.

- NA: Use this category if the RNA library type does not fall into any of the above categories, if the description is ambiguous, or if the RNA library type is not provided in the experiment's description.

8. RNA_Source: The specific biological material from which RNA is extracted for gene expression analysis. This field should specify the source of the RNA, such as tissue, cell type, or organism part. When annotating the RNA source, focus on capturing the most specific, lowest hierarchical biological material provided. If both a cell type and a tissue are mentioned, prioritize the cell type for the RNA_Source field, while the tissue can be captured in the Tissue field. For example, if the source is 'Kidney endothelial cells,' annotate RNA_Source as Cells: Endothelial Cells. If the source is 'Mouse embryonic stem cells,' annotate as Cells: Embryonic Stem Cells without mentioning the organism as mouse. For established cell lines, annotate in the format as Cell Line: [Cell Line Name] (e.g., Cell Line: 3T3). If the information is unclear or not provided, use NA. Be precise. For example, if the provided information says Total RNA extracted from lung tissue, annotate it as Tissue: Lung.

9. Tissue: It refers to the specific region or anatomical location within the organism where the 'RNA source or biological material' was derived from. This field should reflect the specific region or organ from which the RNA source was derived, ensuring consistency with the RNA_Source annotation. If the RNA source is a specific cell type, the Tissue should capture the related tissue or organ. For example, if the RNA source is 'Kidney endothelial cells,' annotate Tissue as Kidney. If the RNA source is from a tissue like 'fetal liver,' then annotate Tissue as Liver. If RNA source is tissue: heart left ventricle then Tissue should be annotated as Heart: Left Ventricle. For established cell lines, if the organ of origin is well-known, you may infer and annotate the Tissue accordingly. For example: For Cell Line: NMuMG (Normal Murine Mammary Gland) can have Tissue annotated as Mammary Gland.
         
10. Experimental_Setting: Determine the experimental setting or conditions of the overall experiment based on the GSE Summary or GSE Overall Design.
Select the appropriate category from the list below, and ensure that the exact spelling, capitalization, and format are maintained without any variations or special characters. Use Only these categories., ‘In Vivo’, ‘Ex Vivo’ and ‘In Vitro’. Always refer to the GSE Summary or GSE Overall Design to accurately determine the experimental setting. You can refer to the following definitions to guide your selection. Please determine one type among the above three, and do not provide 'NA'. 

- In Vivo: Experimentation conducted within a living organism. This category applies to studies where biological processes are examined in the context of an intact, living system. It includes research involving the interactions between different organs, tissues, and systems within the body of the organism. This setting is often used to study the effects of drugs, treatments, or genetic modifications in live animals or humans. 

- Ex Vivo: Experimentation conducted outside of a living organism, but using tissues, cells, or organs that have been derived from an organism. This category is used when the biological material is removed from the organism and studied in a controlled environment, while still retaining some aspects of the complexity found in a living system. Examples include tissue culture studies or organ slice experiments.

- In Vitro: Experimentation conducted in a controlled environment, such as a cell culture, biochemical assay, or similar laboratory setting. This category is used when the study investigates biological processes in isolated systems, allowing precise control over experimental conditions and variables. Common examples include experiments performed in test tubes, petri dishes, or culture plates.  

11. Model_Type: Specifies the type of experimental model used in the study. The selection of Model_Type depends on the Experimental Setting and specific details provided in the GSM record. Choose the most appropriate model type based on the guidelines below. If no category is supported by the metadata, annotate as NA.

1). If Experimental Setting is In Vivo, select the Model_Type from the following options.
- Transgenic Model: Use this option when the experiment involves an animal model, typically a mouse, in which foreign DNA has been introduced into the genome. This model is commonly used to overexpress a particular gene to study its function or to model human diseases.
- PDX (Patient-Derived Xenograft): Choose this model type when tumor tissue obtained directly from a cancer patient is implanted into immunodeficient mice. PDX models are used to study tumor biology and test personalized cancer treatments.
- CDX (Cell Line-Derived Xenograft): Select this option when cancer cells derived from a cell line are implanted into immunodeficient mice. CDX models are used to study tumor biology and evaluate potential therapies.
- Xenograft: Use this category when the experiment involves the transplantation of cells, tissues, or organs from one species to another that does not specifically involve human tumor cells implanted into mice or other model organism. This includes any cross-species transplantation outside of the PDX and CDX models.
- Knockout: Use this model type when the experiment involves an organism, often a mouse, in which a specific gene has been intentionally deactivated or knocked out to study the effects of the gene's absence on biological processes.
- Conditional Knockout: Choose this option for knockout models where a gene is only deactivated in specific tissues or at specific developmental stages. This allows researchers to study the gene's function in a more controlled manner.
- Knockdown: Select this model type when the experiment involves reducing the expression of a gene (but not completely knocking it out) to study gene function or biological processes. This is commonly done using techniques such as RNA interference (RNAi) or CRISPR interference (CRISPRi).
- Chemical Induced Disease Model: Select this option when diseases are induced using chemical agents, such as toxins, drugs, or other chemicals. Include the specific chemical used to induce the disease in the annotation (e.g., Chemical Induced Disease Model: DEN induced Hepatocellular Carcinoma or Chemical Induced Disease Model: Bleomycin induced Pulmonary Fibrosis). Make sure that the particular chemical and disease induced by that chemical is always present while annotating. Do not use terms like 'elicited' or 'treated’ as synonyms to ‘induced’. Do not use a hyphen between the chemical name and 'induced'. Use this model type for only those GSM samples that have been treated with the chemical to induce the disease. For control samples not treated with the chemical, use 'Tissue' or another appropriate model type.
- Tissue: Use this model type when In Vivo experiment involves tissue studies, and none of the specific in vivo model types (e.g., PDX, CDX, Knockout, Transgenic Model, Xenograft, Conditional Knockout, Knockdown, Chemical Induced Disease Model) apply. Also, use this model type for wild-type or control samples that did not undergo any genetic manipulation or chemical treatment to induce specific phenotype or disease and are used as normal or baseline tissue controls.

2). If Experimental Setting is Ex Vivo, select the Model_Type from the following options.
- Organoid: Use this option when the experiment involves 3D structures grown from stem cells that replicate much of the complexity of an organ. 
- Tissue: Select this model type when the experiment is performed on isolated tissues that have been extracted or removed from the organism and studied outside of the body.
- Primary Cells: Select this model type when the experiment involves cells that have been isolated from tissues obtained directly from an organism (human, animal, or other) while maintaining its original structure and microenvironment. These cells retain much of their in vivo characteristics and are used directly in experiments. This category is appropriate for studies where cells are immediately analyzed or subjected to short-term assays ex vivo.

3). If Experimental Setting is In Vitro, select the Model_Type from the following options.
- Cell Line: Select this option when the experiment involves immortalized cells capable of indefinite growth in culture. Cell lines are derived from various tissues and are commonly used for in vitro studies due to their ease of culture and genetic stability.
- Induced Pluripotent Stem Cells (iPSCs): Use this model type for experiments involving somatic cells reprogrammed to a pluripotent state resembling embryonic stem cells. iPSCs can differentiate into various cell types and are valuable for disease modeling, drug discovery, and regenerative medicine.
- Primary Cells: Select this option when the experiment involves cells that have been directly isolated from tissues and cultured in vitro. Primary cells are not immortalized and have a limited lifespan in culture.
    