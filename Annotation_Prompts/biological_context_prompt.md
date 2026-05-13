Role: Biological Context
Annotate only the following field for each GSM sample in this role: Disease. Do not annotate any other fields in this role.

12. Disease: 1) When annotating the Disease field, carefully review both GSE and GSM details to determine the specific disease or medical condition associated with the given GSM sample. Use the exact disease names as provided or commonly accepted. Capitalize the first letter of each word in the disease name. Avoid abbreviations.

- Explicitly Mentioned Disease: If the disease or condition is explicitly mentioned in the provided information, the disease should be annotated as ‘[Disease Name] (Extracted)’. For example, study title: ‘Gene Level Expression Profiling in human tongue squamous carcinoma cell line (SAS),’ the Disease annotation: ‘Squamous Carcinoma (Extracted)’.

- Disease Inferred from Context: If the disease is not directly mentioned but can be reasonably inferred from the context, the disease should be annotated as ‘[Disease Name] (Inferred)’. For example, Transcriptional profiling of GIF-5 mouse gastric epithelial cells comparing CD133-positive and CD133-negative cells. The former formed CD133-positive and CD133-negative cells while the latter only CD133-negative cells, suggesting that CD133-positive cells are mother cells. The former produced differentiated type tumors while the latter undifferentiated types in vivo, indicating a relationship between CD133-expression and glandular structure formation.’ Disease field should include Gastric Tumor (Inferred) as disease information is not directly provided. Only infer diseases when there is strong evidence. Do not guess or assume diseases based on limited information.

- Multiple Diseases in a Study: annotate each GSM sample with the specific disease it represents. For example, in a study that includes both lung cancer and chronic obstructive pulmonary disease (COPD) samples, the disease should be annotated as ‘Lung Cancer (Extracted)’ for lung cancer samples and ‘Chronic Obstructive Pulmonary Disease (Extracted)’ for COPD samples. Separate distinct diseases with a semicolon if the GSM truly represents more than one disease in this format: for example, Disease A (Extracted); Disease B (Extracted). Similarly, when dealing with disease progression or staging, annotate samples based on their specific disease stage. For instance, in a study on liver disease, samples should be annotated as ‘Fatty Liver (Extracted)’ or ‘Cirrhosis (Extracted)’ depending on the stage of liver disease each GSM sample represents, while healthy liver samples should be annotated as ‘NA’.

- Healthy or Disease-Free Samples: For GSM samples from healthy, disease-free tissue, annotate as ‘NA’. For example, in a study where some alveolospheres are treated with bleomycin to induce pulmonary fibrosis and others are left untreated, the disease for bleomycin-treated samples should be ‘Pulmonary Fibrosis (Extracted)’ and for untreated samples, the disease should be ‘NA’.

- Genetic Disease Models: annotate as ‘[Disease Name] (Extracted)’ for the disease model and ‘NA’ for the wild-type controls. For example, in a study comparing knockin zQ175 Huntington’s disease model mice and Wild Type (WT) mice, the disease for zQ175 samples should be ‘Huntington’s Disease (Extracted)’ and for WT samples, the disease should be ‘NA’.

- For treatment controls derived from diseased sources: the disease should be retained as ‘[Disease Name] (Extracted)’. For example, in a study involving AML cell lines where some samples are drug-treated and others are treated with DMSO as a control, the Disease for both treated and control samples should be ‘Acute Myeloid Leukemia (Extracted)’.

- Unclear or Multiple Possible Diseases: annotate as ‘NA’. For instance, if a study description is vague or could relate to various conditions without clear evidence, the Disease should be annotated as ‘NA’.

2). Additional Rules for Disease Categorization: 
Apply the following classification guidelines to ensure standardization and consistency across annotations. These apply especially when information is ambiguous or partial.

Disease: Rules for Categorization

i). Normal
- If the sample is explicitly mentioned as derived from a healthy control or normal tissue.
Keywords: 'healthy control,' 'normal tissue,' 'control.'
Example: Tissue: Left ventricular free wall tissue. Disease state: Healthy control → Classification: Normal

ii). Adjacent Normal
- If the sample is explicitly mentioned as normal tissue but derived from a patient with a disease.
Keywords: 'normal tissue,' 'adjacent normal,' 'paracancerous tissue,' combined with a disease state.
Example: Tissue: Normal liver. Disease state: Hepatoblastoma patient → Classification: Adjacent Normal.

iii). Disease-Associated
- If disease is explicitly stated or strongly supported: 
Tissue: The sample's tissue explicitly indicates a diseased state (e.g., 'adenocarcinoma,' 'tumor tissue').
Cell Line: If the cell line's origin is well-documented and known to be derived from a diseased patient, assign the specific disease.
Examples: MDA-MB-231 → Breast Cancer (triple-negative).
PLC/PRF/5 → Hepatocellular carcinoma.
DLD-1 → Colorectal cancer.
Even if the disease is not explicitly mentioned in the sample metadata, assign the disease based on the cell line's established origin.

iv). No Disease Mentioned
Criteria: The sample has no explicit mention of being derived from a diseased or healthy source.
Modeling a disease does not count unless explicitly stated that the sample represents the disease.
Cell lines are classified as No Disease Mentioned unless their origin is known to be from a diseased state.
Example: Tissue: Chorionic villus. Disease state: Not mentioned → Classification: No Disease Mentioned

Special Consideration for Cell Lines
If the cell line's origin is well-known: Known disease origin: Assign the specific disease.
- Example: PLC/PRF/5 → Hepatocellular carcinoma.
Unknown or not explicitly mentioned: Classify as No Disease Mentioned.

v). Key Workflow
1). Read Metadata Carefully: Prioritize explicit mentions of 'healthy,' 'normal,' or a specific disease.
2). Classify Conservatively: Default to No Disease Mentioned unless there is clear evidence otherwise.
3). For Cell Lines: Cross-reference known origins (e.g., ATCC, Cellosaurus). Classify as No Disease Mentioned if the disease origin is not explicitly confirmed.

(vi) Summary
- Normal: Explicitly from healthy control.
- Adjacent Normal: Explicitly normal tissue from a diseased patient.
- Disease-Associated: Explicitly mentions disease or known diseased origin.
- No Disease Mentioned: Default for all cases without explicit mention.

(vii) Examples for Cell Line Handling
1). GSM12345: Cell line: MDA-MB-231.
- Metadata does not explicitly mention 'breast cancer.'
- Classification: Breast Cancer (triple-negative).
- Reason: MDA-MB-231 is a well-known cell line derived from triple-negative breast cancer.

2). GSM12346:Cell line: PLC/PRF/5.
- Metadata only states: 'Liver cell line.'
- Classification: Hepatocellular carcinoma.
- Reason: PLC/PRF/5 is a well-documented hepatocellular carcinoma cell line.

3). GSM12347: Cell line: iPSC-derived microglia (iMGL).
- Modeled Disease: Alzheimer's disease.
- Classification: No Disease Mentioned.
- Reason: Derived from healthy iPSCs, disease is modeled, not inherent to the sample.

(VIII). GSM Information Examples:
1). GSM12391: Tissue: Normal colon, Disease state: Healthy → Normal.
2). GSM12306: Tissue: Colon adenocarcinoma. Disease state: Colorectal cancer → Colon adenocarcinoma.
3). GSM12382: Tissue: Normal colon. Disease state: Colorectal cancer patient → Adjacent Normal.
4). GSM12348: Tissue: Chorionic villus. Disease state: Not mentioned → No Disease Mentioned.
