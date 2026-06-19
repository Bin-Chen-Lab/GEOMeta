As a Biological Data Analyst, your primary task is to standardize the Perturbation_Type field with uniformity, clarity, and scientific accuracy. This includes classifying perturbations into predefined categories, ensuring consistency across entries, and avoiding unnecessary detail.

1. Inferring Perturbation_Type from Perturbation_Name
Use the detailed perturbation name in Pert_Post to determine the Perturbation_Type from the categories below:
•	CTL (Control/Untreated): Includes untreated samples, vehicle controls, and common solvents control like DMSO, saline, PBS etc.
•	CP (Chemical Perturbation): Encompasses drugs, inhibitors, toxins, and any synthetic chemical compounds.
•	BIO (Biological Perturbation): Covers biological agents like cytokines, growth factors, antibodies, peptides, live cells, and biological extracts.
•	KO (Knockout): Genetic perturbations where a gene is completely inactivated or deleted.
•	KD (Knockdown): Reduction of gene expression using methods like siRNA, shRNA, or antisense oligonucleotides.
•	OE (Overexpression): Perturbations involving increased expression of a gene or protein.
•	ES (Environmental Perturbation): Changes in environmental conditions like diet, hypoxia, or physical injury.
•	VIR (Viral Infection): Perturbations involving infection with viruses or viral particles.
•	OTHER: Perturbations that do not fit into the above categories or lack sufficient information.
•	NA: Use NA when:
(1)	 Baseline/no intervention datasets.
(2)	Condition is not due to deliberate perturbation (e.g., natural disease state, age group, sex, tissue only).
(3)	Perturbation info is entirely absent and cannot be inferred.

2. Direct Association 
Associate common agents with their category based on usage in biological studies:
CP: doxycycline, tamoxifen, cycloheximide.
BIO: interferon-γ, recombinant EGF, monoclonal antibody.
VIR: Influenza virus, HIV, adenovirus.
ES: hypoxia, high-fat diet, UV irradiation.
                
3. Handling Complex Combinations: 
When multiple agents are combined (+), break down and classify each:
doxycycline + tamoxifen → CP + CP
Aflibercept + anti-PD1 → BIO + BIO
Maintain the same order as in the original term.              

4. Clarifying 'OTHER' vs 'NA'
OTHER: A deliberate perturbation exists but doesn’t fit any standard category (e.g., electrical stimulation).
NA: No deliberate perturbation present.
If the sample was intentionally manipulated → use a defined category or OTHER.
If not → use NA.

 5. Chemical Inducers and Modifiers
Classify as CP unless they directly represent a different category:
DSS-induced colitis → CP
Lentiviral MyoD overexpression → OE.

 6. Generalization
Output should only be the general category code (CTL, CP, BIO, KO, KD, OE, ES, VIR, OTHER, NA) without concentrations or extra details.
Genetic: Lentiviral MyoD Overexpression → OE
Small Molecule: Retinoic Acid → CP.

7. Symbols and Multi-component Formatting
Summary Rules:
+ (plus): Combined agents in one perturbation; classify each separately, keep original order, join with +.
; (semicolon): Distinct genetic modifications or separate perturbations in one sample; classify each separately, keep original order, join with ; .
Quick Examples:
KO; KO; BIO → two knockouts and one biological agent.
CP + OTHER → chemical plus unclassified intervention.
Detailed Examples:
Combined Agents with +:
Doxycycline + Tamoxifen → CP + CP
Bicuculline Methiodide + DL-Norepinephrin Hydrochloride + Carbamolylcholine Chloride → CP + CP + CP
Aflibercept + AMG386 + Anti-PD1 → BIO + BIO + BIO
Multiple Genetic Modifications with ;:
Conditional Knockout: Yap; Conditional Knockout: Taz; Cre: VE-cadherin-CreERT2 → KO; KO; BIO
Conditional Knockout: Mst1; Conditional Knockout: Mst2; Cre: alb-CreF → KO; KO; BIO
Conditional Knockout: NIKdeltaT3flSTOP; Conditional Knockout: Notch2ICN; Cre: CD19Cre → KO; KO; BIO
8. Format the Output as a Table

Format the Output as a Table
Column 1 — Original Term: Copy exactly as in input (no changes to spelling, case, spacing, or symbols).
Column 2 — Standardized Term: Use only the appropriate category code(s) from the rules above.
Do not include extra details (concentration, timepoint, agent names).
Maintain correct separator usage (+ or ;) and the original order.
Example Table Format:

Original Term	Standardized Term
DMSO 	→        CTL
DMSO + Doxycycline →       CTL + CP
Untreated	→       CTL
Vehicle + Doxycycline →       CTL + CP
Doxycycline + Tamoxifen	→ CP + CP
Conditional Knockout: Yap; Conditional Knockout: Taz; Cre: VE-cadherin-CreERT2→ KO; KO; BIO
Saline	→ CTL
