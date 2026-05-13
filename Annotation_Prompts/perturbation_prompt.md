Role: Perturbation
Annotate only the following fields for each GSM sample in this role:
GSE_Pert, GSM_Pert, Pert, Pert_Dose, Pert_Freq, Pert_Duration, Route_Admin. Do not annotate any other fields in this role.

Identify the presence of Perturbations, which may include details such as dose, frequency, and duration.
- Prioritizing Information Sources: GSM Information should be your main reference for sample-specific details. Use GSE Information for general experiment context or when GSM details are missing.
- Maintain Consistent Formatting: Use the exact units and terms throughout all annotations. Ensure that entries for multiple Perturbations are in the correct order across all fields.
- For multiple Perturbations, list doses, frequencies and durations in the same order as the Perturbations, separated by ' + '.
- Avoid assumptions and unsupported inference. Only use information explicitly provided in the GSE or GSM records. Do not assume doses, frequencies, or durations.
Annotate as 'NA' for each field when information for those specific fields is not available or not applicable. Do not leave fields blank. 
Annotate all assigned perturbation-related fields for each GSM sample in this role. 

13. GSE_Pert: It indicates whether the overall experiment described in the GSE information involves any Perturbations. It reflects whether the study includes any deliberate interventions applied to the samples. Carefully review GSE Summary and GSE Overall Design to determine if the study includes Perturbations.
Perturbations can be: 
- Genetic: gene knockouts, knockdowns, overexpression.
- Chemical: drug treatments, toxin exposure.
- Environmental: changes in temperature, lighting, housing conditions.
- Physiological: surgical interventions, induced injuries.
If any part of the GSE involves Perturbations, annotate as 'Yes' even if not all samples are perturbed. If the study is purely observational with no interventions, annotated as 'No'.
Examples: 
- Yes: A study where mice are treated with a drug to observe gene expression changes.
- No: A study analyzing gene expression in healthy human tissues without any treatments.

14. GSM_Pert: It specifies whether an individual GSM sample is a 'Perturbed' sample or a 'Control' sample within the GSE. Examine the GSM Information to determine the sample's status. Look for indications of treatments, interventions, or genetic manipulations in the GSM information. If the sample is untreated or received a placebo/control substance or served as baseline or control then annotate as 'Control'. If the sample received any form of Perturbation, annotate as 'Perturbed'.
Examples:
- Perturbed: A cell line treated with a chemotherapeutic agent.
- Control: A cell line treated with vehicle only (e.g., DMSO) or left untreated.

15. Pert: Extract information from the GSM record about the treatments or interventions.
- For Perturbed Samples: List the specific Perturbations applied. Use precise terms, including drug names, genetic modifications, or environmental changes.
- For Control Samples: Indicate the control substance or condition (e.g., 'DMSO', 'Vehicle Control', 'Untreated'). Sometimes GSM_Info only mentions ‘Control’ or ‘Vehicle’ but GSE_Info includes specific details about control samples so carefully review and extract the Perturbations.
- List multiple Perturbations separated by ' + '. Use exact names of drugs or agents, and avoid abbreviations unless they are standard and unambiguous.
For genetic Perturbations, specify the gene and type of modification (e.g., 'Knockout: PTEN').

16. Pert_Dose: It specifies the dose of the Perturbation applied to the sample. Provide the dose amount along with appropriate units (e.g., '20 mg/kg', '10 μM') to maintain clarity. Exclude Perturbation names from this field and use 'NA' for unspecified dosages. 
Examples:
Sample Treated with CCL4 at 20 mg/kg: Pert_Dose: '20 mg/kg'.
Sample Treated with Drug A 5 μM + Drug B 10 μM: Pert_Dose: '5 μM + 10 μM'.
Control Sample with DMSO at 0.1%: Pert_Dose: '0.1%'.
Dose Not Specified: Pert_Dose: 'NA'

17. Pert_Freq: It indicates the frequency at which the Perturbation was applied. Describe the frequency using standard expressions (e.g., 'Once daily', 'Twice weekly', 'Single dose').
Use consistent terminology for clarity. Examples of Standard Expressions:'Once daily', 'Every 12 hours', 'Twice weekly, 'Single dose'.
Examples:
Daily Treatment for a Week: Pert_Freq: 'Once daily'.
Administered Every Other Day: Pert_Freq: 'Every other day'.
Single Injection: Pert_Freq: 'Single dose'.
Frequency Not Specified: Pert_Freq: 'NA'.

18. Pert_Duration: It specifies the total duration over which the Perturbation was applied. Provide the duration along with units (e.g., '1 week', '48 hours', '6 months').
Pert_Duration: '7 days'
Treatment Lasting 3 Weeks: Pert_Duration: '3 weeks'.
Single Dose Sampled After 24 Hours: Pert_Duration: '24 hours'.
Duration Not Specified: Pert_Duration: 'NA'
 
- Some Examples Incorporating All Pert Fields:
1). For Perturbed Sample with Complete Information:
GSE_Pert: 'Yes'
GSM_Pert: 'Perturbed'
Pert: 'CCL4'
Pert_Dose: '20 mg/kg'
Pert_Freq: 'Once daily'
Pert_Duration: '1 week'

2). For Control Sample Treated with DMSO:
GSE_Pert: 'Yes'
GSM_Pert: 'Control'
Pert: 'DMSO'
Pert_Dose: '0.1%'
Pert_Freq: 'Once daily'
Pert_Duration: '1 week'
 
3). For Control Sample Without Treatment:
GSE_Pert: 'Yes'
GSM_Pert: 'Control'
Pert: 'Untreated'
Pert_Dose: 'NA'
Pert_Freq: 'NA'
Pert_Duration: 'NA'
 
4). For Perturbed Sample with Multiple Perturbations:
GSE_Pert: 'Yes'
GSM_Pert: 'Perturbed'
Pert: 'Drug A + Drug B'
Pert_Dose: '5 mg/kg + 10 mg/kg'
Pert_Freq: 'Once daily + Once daily'
Pert_Duration: '2 weeks + 2 weeks'
                
19. Route_Admin: When annotating the Route_Admin through which a unique Perturbation or drug was administered to the sample, select from the following standardized options: Intraperitoneal for injection into the peritoneal cavity, Intravenous for injection directly into a vein, Oral for administration by mouth, Subcutaneous for injection into the tissue layer between the skin and muscle, Intramuscular for injection directly into a muscle, Topical for application directly to the skin or mucous membranes, Inhalation for administration through the respiratory tract, Intranasal for administration through the nasal passages, Intracerebral for injection directly into brain tissue, Intraventricular for injection into the brain's ventricles, Intrathecal for injection into the spinal canal, Ocular for administration directly to the eye, and Transdermal for absorption through the skin, typically via a patch. If the drug was added to the culture media, annotate as 'In Media' without specifying the drug name. If multiple drugs were used, list the corresponding routes of administration in the order they appear, separated by ‘+’.

If only 'injection' is mentioned without specifying the route, annotate as 'Injection (unspecified)' and seek further clarification if possible. Use 'Other [specify]' if the route does not fit into any of the predefined categories, and replace [specify] with the specific route used. If no unique route is applicable or if no drug was used, annotate as 'NA.' It is crucial to maintain the exact case format and avoid variations in upper and lower case, as well as special characters, to ensure consistency across all annotations.


