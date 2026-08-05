# Figure Contract

Create this compact contract before committing to a figure architecture. Treat it as the shared fact source for planning, implementation, QA, and delivery—not as paperwork for the user to complete.

Infer fields from supplied data, code, captions, and artifacts. Ask only blocking questions. Use `unknown` rather than guessing, and state the consequence of each unresolved field.

## Contents

- [Minimum gate](#minimum-gate)
- [Contract schema](#contract-schema)
- [Route-specific use](#route-specific-use)
- [Claim–evidence rules](#claimevidence-rules)
- [Completion check](#completion-check)

## Minimum gate

Do not begin publication-oriented implementation until these items are known or explicitly marked unresolved:

1. task route and research phase;
2. scientific question or bounded claim;
3. analysis unit and replicate unit;
4. primary evidence and intended panel roles;
5. quantity, units, denominator, center, and uncertainty semantics;
6. exclusions, missingness, transformations, aggregation, and sampling rules;
7. statistical annotations and multiplicity treatment;
8. target size, output formats, and editing requirements;
9. main integrity or reviewer risks.

For exploratory work, replace the claim with a question and keep interpretations provisional. For a quick cosmetic revision, fill only fields needed to prove that scientific meaning remains unchanged.

## Contract schema

Use YAML unless the surrounding project requires another structured format. Omit irrelevant optional fields; do not fill them with boilerplate.

A dependency-free JSON example is available at
[figure-contract.example.json](figure-contract.example.json) and can be
checked with `scripts/validate_contract.py`.

```yaml
contract_version: 1
task:
  mode: create | revise | review
  phase: exploratory | confirmatory | presentation
  requested_change: null
  meaning_locked: []          # semantics that a revision must not alter

question:
  text: ""
  population_or_system: ""
  comparison_or_exposure: ""
  outcome: ""

claims:
  - id: C1
    statement: ""
    level: descriptive | associational | predictive | causal
    status: proposed | supported | qualified | not-supported | unknown
    scope: ""
    not_claimed: ""           # a nearby overclaim the figure must avoid

evidence:
  primary: []
  supporting: []
  controls: []
  diagnostics: []
  context: []

panels:
  - id: a
    question: ""
    evidence_role: primary | supporting | control | diagnostic | context
    supports_claims: [C1]
    data_source: ""
    analysis_unit: ""
    replicate_unit: ""
    fields:
      x: ""
      y: ""
      group: null
      facet: null
      label: null
    quantity_and_units: ""
    encoding:
      geometry: ""
      position: ""
      color: ""
      size: ""
      order: ""
      scale_and_limits: ""
    statistics:
      center: null
      uncertainty: null
      test_or_model: null
      multiplicity: null
      n_definition: ""
    unique_contribution: ""
    known_risks: []

data_integrity:
  expected_rows_or_items: unknown
  included_rows_or_items: unknown
  exclusions: []              # exact predicate, reason, before/after count
  missingness: ""
  transformations: []         # formula, parameters, definition checks
  aggregation: null           # grouping keys, summary, weights, denominator
  sampling: none              # if used, scope, seed, counts, preview/final
  category_order: {}
  precomputed_results: []     # coordinates, p-values, model outputs, etc.

traceability:
  - claim_id: C1
    supported_by_panels: [a]
    source_fields_or_results: []
    limitations: []

visual_system:
  reading_order: ""
  emphasis: ""                # hero panel and visual hierarchy
  shared_scales: []
  color_semantics: {}
  accessibility_checks: [color-vision, grayscale, contrast]

target:
  audience: ""
  destination: manuscript | supplement | presentation | report | exploratory
  width_mm: unknown
  height_mm_max: unknown
  primary_format: svg | pdf | png | tiff | unknown
  preview_format: png
  editable_text_required: true
  resolution_dpi: null

implementation:
  backend_by_panel: {}
  final_assembly_owner: ""
  case_influence:
    case_ids: []
    reuse_level: exact | structural | style-only | build-new
    borrowed_decisions: []
  random_seed: null

review_risks:
  - risk: ""
    affected_claims_or_panels: []
    mitigation: ""
    status: open | mitigated | accepted

acceptance:
  - ""

unknowns:
  - field: ""
    consequence: ""
    blocking: true
```

Do not require the user to author this YAML. Generate and maintain it as part of the workflow. A Markdown table is acceptable for a simple one-panel task if it retains the same semantics.

## Route-specific use

### Create

Complete the minimum gate, then define the panel map. Freeze data semantics before fine styling. Update the contract whenever the analysis or evidence architecture changes.

### Revise

Record:

- the requested change;
- meanings that must remain locked;
- the original and revised encodings;
- any unavoidable semantic effect;
- a before/after validation check.

Do not expand a visual edit into a new analysis without explicit authorization. If the existing figure contains a scientific defect, report it separately from the requested revision.

### Review

Infer the apparent contract from the artifact and mark it `inferred`. Attach confidence to inferred claims, tests, units, and data mappings. Never convert a plausible visual interpretation into a factual assertion.

Report three outcomes separately:

- what the figure visibly communicates;
- what the available data/code supports;
- what remains unverifiable.

## Claim–evidence rules

### Use a bounded claim

Write one sentence that is specific enough to be falsifiable. State population/system, comparison, outcome, direction or pattern, and scope where relevant.

Prefer:

> Within the sampled cohort, treatment A is associated with a lower measured response than treatment B at week 8.

Avoid:

> Treatment A is better.

Use causal language only when the design and analysis support it.

### Maintain a claim–evidence ledger

Assign claim IDs and panel IDs. Require every claim to map to evidence, and every panel to contribute to at least one claim or to necessary context/diagnostics.

Apply two tests:

1. **Coverage test** — can a reader locate the evidence for every stated claim?
2. **Removal test** — if a panel is removed, does evidence, interpretation, or necessary orientation weaken? If not, remove or merge it.

Do not allow a decorative panel to masquerade as supporting evidence.

### Keep semantic checksums aligned

For each quantitative panel, ensure that these expressions describe the same quantity:

- source field or calculation;
- axis or legend label;
- center and uncertainty;
- annotation and caption wording;
- stated claim.

A mismatch is a semantic failure even when the rendered figure looks polished.

### Separate evidence roles

- **Primary** directly bears the main claim.
- **Supporting** adds a different measurement, population, or analysis that reinforces it.
- **Control** rules out a specific alternative explanation.
- **Diagnostic** shows model or measurement adequacy.
- **Context** orients the reader but does not establish the claim.

Use visual emphasis in the same order unless the reading task requires otherwise.

## Completion check

Before implementation, confirm:

- each panel has one explicit question and unique contribution;
- claim level matches study design;
- analysis and replicate units are not conflated;
- all values and marks are traceable to a source field or computed result;
- transformations, exclusions, aggregation, and sampling are disclosed;
- `n`, denominator, units, center, uncertainty, test, and multiplicity are defined;
- planned scales and encodings do not exaggerate the evidence;
- output requirements are physically specified or explicitly unresolved;
- open risks and unknowns have visible consequences;
- acceptance criteria can be checked on the rendered artifact.

After rendering, update the contract with actual outputs, deviations, and unresolved limitations rather than leaving it as an obsolete plan.
