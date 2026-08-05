# Principle-first figure grammar

The skill must remain fully capable when no case library is available. Cases
are optional design priors; this grammar is the default design engine.

## Contents

- [Two-pass design](#two-pass-design)
- [Data relationship to visual grammar](#data-relationship-to-visual-grammar)
- [Evidence architecture](#evidence-architecture)
- [Counter-reading test](#counter-reading-test)
- [Case-assisted path](#case-assisted-path)

## Two-pass design

### Pass 1 — Semantic composition

Ignore styling and decompose the task into evidence atoms:

- **observation** — raw values, images, events, or records;
- **estimate** — center, effect size, fitted relation, or ranked score;
- **uncertainty** — interval, distribution, measurement error, or posterior;
- **identity** — pairing, subject, sample, lineage, or repeated unit;
- **process** — time, transition, sequence, or event history;
- **structure** — matrix, membership, topology, hierarchy, or space;
- **diagnostic** — residuals, calibration, sensitivity, or data quality;
- **context** — units, denominators, thresholds, provenance, or orientation.

Choose only atoms required by the Figure Contract. Assign each atom to a panel
or a layer within a panel. Do not add a panel merely because a case contains
one.

### Pass 2 — Visual composition

After semantics are frozen, choose:

- geometry and statistical transform;
- axes and scale;
- grouping, ordering, and small multiples;
- panel hierarchy and reading order;
- color, shape, line, typography, and annotation;
- physical size and export format.

Visual decisions may simplify reading but must not alter the semantic pass.

## Data relationship to visual grammar

| Data relationship | Default evidence grammar | Required guard |
|---|---|---|
| Independent continuous groups | raw observations + estimate/interval; add density only when supported by `n` | define analysis unit and uncertainty |
| Paired observations | preserve pair ID with links or differences + paired estimate | report complete pairs, ties, and missingness |
| Longitudinal measurements | individual trajectories + declared group model/summary | preserve subject and time; do not treat rows as independent |
| Time-to-event | step function + censor marks + risk table/interval when needed | define origin, event, censoring, competing risks |
| Effect estimates | point + interval + aligned labels/numerical values | keep effect scale, reference, and model provenance |
| Composition | common-denominator parts; show totals separately when important | verify closure and distinguish zero from unobserved |
| Set membership | exact-intersection bars + membership matrix | define membership, deduplication, and displayed tail |
| Multi-stage flow | nodes + ribbons based on real record linkage or declared weights | state ribbon units and test conservation |
| Matrix/pattern | cells + meaningful ordering + aligned annotations | declare transform, missingness, distance, and clustering |
| Embedding | supplied coordinates + density/category encoding | label as precomputed; avoid global-distance claims |
| Spatial | valid geometry + scale/legend + uncertainty or coverage when relevant | declare CRS, join success, and boundary source |
| Model relationship | observations + fit/interval + at least one relevant diagnostic | align model assumptions and claim level |

These are starting grammars, not mandatory chart types. Replace them when the
data-generating process or reader task demands another encoding.

## Evidence architecture

Build the smallest sufficient figure:

1. Choose one primary panel that most directly bears the main claim.
2. Add a supporting panel only when it contributes a different measurement,
   population, scale, or robustness check.
3. Add a diagnostic panel when model or measurement adequacy is necessary to
   interpret the primary result.
4. Add context only when the reader cannot otherwise decode the evidence.
5. Apply the removal test to every panel.

Use shared scales only for quantities that are genuinely comparable. Align
panels by the entity or dimension the reader must trace.

## Counter-reading test

Before styling is final, write the most plausible wrong reading of each panel.
Check whether it could be caused by:

- an ambiguous denominator or `n`;
- ordering by the displayed outcome;
- area/radius confusion;
- truncated or transformed axes;
- smoothing or interpolation;
- hidden missingness or exclusions;
- categorical colors implying an ordinal scale;
- a descriptive pattern appearing inferential or causal;
- precomputed coordinates appearing newly analyzed.

Change the encoding, annotation, or claim until the likely wrong reading is
blocked or visibly qualified.

## Case-assisted path

After the principle-first design exists, consult the case index to:

- compare alternate layouts;
- borrow an audited evidence arrangement;
- inherit visual tokens or annotation grammar;
- identify a known failure mode.

Record exactly which decisions a case influenced. A case cannot override the
Figure Contract, introduce an unnecessary panel, or define the limits of what
the skill can draw.

If no case passes semantic compatibility, set:

```yaml
implementation:
  case_influence:
    case_ids: []
    reuse_level: build-new
    borrowed_decisions: []
```

Then continue normally with the principle-first design.
