Agent task: Perturbation-type inference

Infer the `Perturbation_Type` from each standardized `Pert` term according to the rules below. Preserve the input order and return one inferred Perturbation_Type value for each original term.

## General Requirements

- Preserve the original input order.
- Maintain a strict one-to-one correspondence between original and inferred terms.
- Infer Perturbation_Type only from the standardized Pert term.
- Do not infer a perturbation from disease, age, sex, tissue, or other
  naturally occurring metadata attributes.
- Preserve the order and separators of multi-component perturbations.

## Inference Rules

1. Perturbation_Type Categories

Use the standardized `Pert` term to assign one of the following categories:

- CTL (Control): An explicit experimental control condition, including Untreated, Vehicle, Placebo, DMSO, PBS, Saline, or Baseline/pre-treatment when explicitly used as a control condition.

- CP (Chemical Perturbation): Encompasses drugs, inhibitors, toxins, and any synthetic chemical compounds.

- BIO (Biological Perturbation): Covers biological agents like cytokines, growth factors, antibodies, peptides, live cells, and biological extracts.

- KO (Knockout): Genetic perturbations where a gene is completely inactivated or deleted.

- KD (Knockdown): Reduction of gene expression using methods like siRNA, shRNA, or antisense oligonucleotides.

- OE (Overexpression): Perturbations involving increased expression of a gene or protein.

- ES (Environmental Perturbation): Changes in environmental conditions like diet, hypoxia, or physical injury.

- VIR (Viral Infection): Use only when a virus or viral particle is applied as an infectious or
challenge agent.

- OTHER: A deliberate perturbation is clearly present but does not fit any of the defined perturbation categories.

- NA: No deliberate perturbation is represented and the term does not describe an explicit experimental control condition. This includes missing perturbation information or naturally occurring observational attributes such as disease state, age, sex, or tissue.

2. Common Classification Examples:
- Doxycycline → CP
- Tamoxifen → CP
- Cycloheximide → CP
- Interferon-γ → BIO
- Recombinant EGF → BIO
- Monoclonal antibody → BIO
- Hypoxia → ES
- High-fat diet → ES
- UV irradiation → ES
- Influenza virus infection → VIR
- HIV infection → VIR
- DSS-Induced Colitis → CP
- Retinoic Acid → CP
- Lentiviral MYOD Overexpression → OE

3. Multi-component Perturbations
When a Pert term contains multiple components, classify each component separately while preserving the original component order.
- Use + (plus): Combined agents in one perturbation; classify each separately, keep original order, join with +.
- Use ; (semicolon): Distinct genetic modifications or separate perturbations in one sample; classify each separately, keep original order, join with ; .

## Examples:
Doxycycline + Tamoxifen → CP + CP
Bicuculline Methiodide + DL-Norepinephrin Hydrochloride + Carbamolylcholine Chloride → CP + CP + CP
Aflibercept + AMG386 + Anti-PD1 → BIO + BIO + BIO
Conditional Knockout: Yap; Conditional Knockout: Taz; Cre: VE-cadherin-CreERT2 → KO; KO; OTHER
Conditional Knockout: Mst1; Conditional Knockout: Mst2; Cre: alb-CreF → KO; KO; OTHER
Conditional Knockout: NIKdeltaT3flSTOP; Conditional Knockout: Notch2ICN; Cre: CD19Cre → KO; KO; OTHER

## Output Requirements

Return exactly one inferred Perturbation_Type value for each original Pert term.
Use only the following category codes: `CTL`, `CP`, `BIO`, `KO`, `KD`, `OE`, `ES`, `VIR`, `OTHER`, or `NA`.
For multi-component perturbations, preserve the original component order and separator structure using ` + ` or `; ` as defined above. Do not include explanations or additional commentary.