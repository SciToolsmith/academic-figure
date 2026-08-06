# Figure Contract

Create this compact contract before committing to a figure architecture. Treat it as the shared fact source for planning, implementation, QA, and delivery—not as paperwork for the user to complete.

Infer fields from supplied data, code, captions, and artifacts. Ask only blocking questions. Use `unknown` rather than guessing, and state the consequence of each unresolved field.

## Contents

- [Minimum gate](#minimum-gate)
- [Contract profiles and execution state](#contract-profiles-and-execution-state)
- [Validation stages](#validation-stages)
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

## Contract profiles and execution state

Use the smallest profile that can protect the task:

- **minimal** — cosmetic revision or export-only check; record the requested
  change, meanings that are locked, target artifact, and acceptance criteria;
- **publication** — create, adapt, or structural revision; complete the
  scientific, data-integrity, traceability, implementation, and target blocks;
- **inferred-review** — read-only review; mark inferred fields and attach
  confidence instead of presenting visual guesses as facts.

Set one execution state:

- `proceed` — all production-blocking semantics and inputs are resolved;
- `prototype-only` — a clearly watermarked or labeled draft is useful, but one
  or more non-fabrication-critical inputs remain unresolved;
- `blocked` — an unknown affects the analysis unit, field mapping, statistical
  meaning, data truth, or another condition required for a valid artifact.

An entry with `unknowns[].blocking: true` cannot be `proceed`. A prototype must
not invent values, units, results, or mechanisms to bypass a block.

`task.phase` describes the figure's epistemic role, not whether the file is a
draft or “final”:

- `exploratory` — question-generating views and provisional interpretations;
- `descriptive` — the figure derives non-inferential summaries such as counts,
  proportions, distributions, or ranges from observations; every derivation
  still belongs in the transformation and traceability records;
- `confirmatory` — the figure computes or communicates prespecified
  inferential evidence;
- `presentation` — the figure only communicates already finalized,
  precomputed results and does not add new inference.

“论文终稿” belongs in the publication profile and target destination. Choose
`descriptive`, `confirmatory`, or `presentation` from the analysis role above,
not from the word “final.”

## Validation stages

Run the contract gate at the matching stage:

```bash
python scripts/validate_contract.py figure-contract.json --stage plan --pretty
python scripts/validate_contract.py figure-contract.json --stage pre-render --pretty
python scripts/validate_contract.py figure-contract.json --stage final --pretty
```

- `plan` checks structure, enums, claim–panel links, ledgers, and whether the
  declared execution state is honest; explicit placeholders and incomplete
  predictive/causal support records are warnings at this stage;
- `pre-render` blocks unresolved scientific inputs and missing acceptance
  criteria before production rendering, including placeholders in scientific
  or artifact-critical fields and unauditable predictive/causal claims.
  Read-only Review and file-level Export may retain an unaudited strong claim
  as `WARN` only when its status is `unknown` or `not-supported`; their output
  must explicitly avoid claiming scientific validation;
- `final` also blocks open review risks that were not mitigated or explicitly
  accepted.

Contract lint uses `CT-*` IDs. The `FC/DI/ST/RT/AR/VV/CE/PR` IDs in
[qa.md](qa.md) are reserved for end-to-end figure QA.

## Contract schema

Use JSON by default so validation remains dependency-free. YAML is acceptable
only when the environment already provides a YAML parser. Omit irrelevant
optional fields; do not fill them with boilerplate.

A dependency-free JSON example is available at
[figure-contract.example.json](figure-contract.example.json) and can be
checked with `scripts/validate_contract.py`.
The separate
[descriptive composition example](figure-contract.descriptive-composition.example.json)
shows a guarded raw-count-to-share workflow without inferential claims.
Stable machine values used below are defined once in
[schema-vocabularies.json](schema-vocabularies.json); localized retrieval and
transformation terms live separately in
[retrieval-lexicon.json](retrieval-lexicon.json).

`target.formats` is the authoritative set of deliverables. `primary_format`
identifies the preferred editable/master artifact and `preview_format`
identifies the review convenience artifact; both must also appear in
`target.formats`. This avoids silently treating PDF or PNG as informal side
products. If any declared deliverable is PNG or TIFF, record a positive
`resolution_dpi`. Publication contracts must resolve both roles before
pre-render validation.

```yaml
contract_version: 1
task:
  mode: create | adapt | revise | review | export
  phase: exploratory | descriptive | confirmatory | presentation
  profile: minimal | publication | inferred-review
  execution_state: proceed | prototype-only | blocked
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
    # Required for predictive and causal claims before production rendering:
    design_basis: ""          # identification/evaluation design, not a panel role
    support_basis:            # traceable records, not unstructured assurances
      - source: ""            # file/result/protocol/model record
        evidence: ""          # exact design, method, metric, or result used
    assumptions: []           # explicit assumptions that bound interpretation

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
    # Use the literal "not-applicable" instead when no statistics apply.
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
  height_mm: unknown            # exact height; optional if height_mm_max is set
  height_mm_max: unknown        # publication requires one positive height constraint
  formats: [svg, pdf, png]       # every formal deliverable; explicit for publication/export
  primary_format: svg | pdf | png | tiff | unknown
  preview_format: png            # role within formats, not an extra implicit deliverable
  editable_text_required: true
  resolution_dpi: 300           # positive if any item in formats is PNG/TIFF

implementation:
  backend_by_panel: {}
  final_assembly_owner: ""
  case_influence:
    primary: null
    contrast: null
    reuse_level: exact | structural | style-only | build-new
    borrowed_decisions: []
    retrieval_status: matched | repair-required-only | no-suitable-case
    audit_status_at_selection: admitted | conditional | inspiration | quarantined | null
    implementation_status_at_selection: verified | language-specific | static-reviewed | failed | unreviewed | null
    repair_gate_satisfied: true | false | not-applicable
    decisive_match: []
    rejected_near_match: null # case ID and semantic rejection reason
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

Do not require the user to author this serialization. Generate and maintain it
as part of the workflow. A Markdown table is acceptable for a simple one-panel
task if it retains the same semantics.

## Route-specific use

### Create

Complete the minimum gate, then define the panel map. Freeze data semantics before fine styling. Update the contract whenever the analysis or evidence architecture changes.

### Adapt

Record the reference, requested scientific purpose, field mapping, transform
and uncertainty compatibility, borrowed decisions, and rejected incompatible
decisions. Use `style-only` or `build-new` when scientific semantics do not
match; visual similarity cannot override the gate.

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

### Export

Use the minimal profile. Lock the existing scientific and visual meaning,
record the source artifact, requested conversion, dimensions, text-editability
requirement, color mode, and acceptance criteria. Report file-level validation
separately from any scientific checks that could not be performed.

## Claim–evidence rules

### Use a bounded claim

Write one sentence that is specific enough to be falsifiable. State population/system, comparison, outcome, direction or pattern, and scope where relevant.

Prefer:

> Within the sampled cohort, treatment A is associated with a lower measured response than treatment B at week 8.

Avoid:

> Treatment A is better.

Use causal language only when the design and analysis support it.

### Audit predictive and causal claims

For every `predictive` or `causal` claim, record all four claim-local fields:

- `design_basis` — the identification or evaluation design, such as
  randomization, a stated quasi-experimental design, or held-out validation;
- `support_basis` — a non-empty list of records that each identify `source`
  and the exact `evidence` used for this claim; a statement such as “accuracy
  was high” without a traceable result is not sufficient;
- `assumptions` — a non-empty list of assumptions that must hold for the
  stated interpretation;
- `not_claimed` — the nearest stronger or out-of-scope conclusion the figure
  explicitly does not establish.

A control or diagnostic panel may contribute evidence, but its presence does
not itself establish causal identification or predictive validity. Keep these
records on the claim even when related panels exist. The contract gate warns
about incomplete records during `plan` and fails them at `pre-render` and
`final` for Create, Adapt, and Revise.

For Review and Export, an artifact may legitimately contain a strong claim
whose support cannot be reconstructed. Mark that claim `unknown` or
`not-supported`; the validator retains an explicit warning instead of
blocking a read-only finding or file conversion. Marking it `proposed`,
`qualified`, or `supported` still requires the complete audit record before
the final gate.

Use explicit unresolved values only while planning. Tokens such as `TBD`,
`TODO`, `placeholder`, `???`, `待补`, and `待填` are detected recursively;
they warn during `plan` and fail in scientific or artifact-critical fields
before rendering. Short legitimate terms such as `pH`, `BMI`, and `n` are not
treated as placeholders.

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
