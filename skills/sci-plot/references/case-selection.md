# Case selection

Use cases as optional scientific decision references, not as screenshots to
imitate. Case retrieval is never a prerequisite for designing or rendering a
figure. When nothing matches, continue with
[figure-grammar.md](figure-grammar.md) and `build-new`.

## Contents

- [Retrieval order](#retrieval-order)
- [Semantic Distance Gate](#semantic-distance-gate)
- [Loading budget](#loading-budget)
- [Reuse levels](#reuse-levels)
- [Catalog status axes](#catalog-status-axes)
- [Selection record](#selection-record)

## Retrieval order

Match in this order:

1. scientific question and intended claim;
2. analysis unit and data relationship;
3. evidence the figure must expose;
4. statistical assumptions and uncertainty definition;
5. domain conventions;
6. visual grammar.

Never reverse this order. Similar colors or geometry do not make two cases
semantically compatible.

## Semantic Distance Gate

Treat these as hard constraints:

- analysis unit: subject, sample, cell, gene, method, site, event, or edge;
- relationship: independent, paired, longitudinal, time-to-event,
  compositional, set membership, flow, spatial, matrix, or embedding;
- denominator and weighting rules;
- transform domain and units;
- uncertainty meaning;
- whether coordinates, model outputs, or enrichment results are precomputed.

Reject a case when a hard constraint conflicts. Record `no-suitable-case`
instead of weakening the user's scientific question, then continue the
case-independent design workflow.

After hard constraints pass, compare:

- evidence-role distance: primary result, uncertainty, diagnostic, control,
  composition, trajectory, or topology;
- structural distance: tidy table, wide matrix, event log, edge list,
  membership matrix, geometry, or precomputed coordinates;
- domain distance;
- visual distance, last.

Record the selected case, rejected near-match, and decisive constraint in the
Figure Contract.

## Loading budget

Read [case-index.md](case-index.md) first. Then load at most:

- one primary case;
- one contrasting case when a design choice is ambiguous;
- one risk card when a known failure mode is relevant.

Do not load all case cards by default.

## Reuse levels

Choose exactly one level and record it:

1. **Exact reuse** — scientific meaning, dimensions, transform, uncertainty,
   and backend contract all match.
2. **Structural adaptation** — meaning and data structure match; provide an
   explicit field-mapping ledger.
3. **Style-only inheritance** — reuse visual tokens or layout principles only;
   rebuild analysis and encodings.
4. **Build anew** — no case passes the semantic gate.

Never copy a script merely because its preview looks suitable.

If code inspection is useful after selection, read
[case-code.md](case-code.md) and inspect [case-assets.json](case-assets.json).
Source availability is not a retrieval signal and must never make a
scientifically weaker case rank higher.

## Catalog status axes

Track two orthogonal catalog states:

- `audit_status`: `admitted`, `conditional`, `inspiration`,
  `quarantined`;
- `implementation_status`: `verified`, `language-specific`,
  `static-reviewed`, `failed`, `unreviewed`.

`audit_status` answers whether the scientific expression has passed review.
`implementation_status` answers what has actually been executed or inspected.
Neither axis describes how the current task will reuse the case.
`reuse_level` is selected per task and therefore belongs in the Figure
Contract, never in the case catalog.

For case entries, `implementation_status` applies to the logical figure at the
time of the source-project audit. It must not be read as a blanket claim that
both packaged Python/R entrypoints, unavailable case inputs, and a new field
mapping are production-verified.

The source-pack `smoke_status` is a third, narrower fact: whether the bundled
reproduction source was rerun with an explicitly non-production smoke input.
It neither upgrades `audit_status` nor proves that real input data are bundled.

A folder can contain multiple logical figures. Python and R files with similar
names are not assumed equivalent. A `conditional` result is
`repair-required`; satisfy every returned `repair_gate` before treating it as
a positive production reference. An `inspiration`, `quarantined`, or `failed`
result is blocked and must carry a `blocked_reason`. Never silently convert a
repair-required or blocked result into a production template.

The retriever has three distinct outcomes:

- `matched`: at least one eligible candidate is available;
- `repair-required-only`: semantic candidates exist, but every candidate has
  an open repair gate;
- `no-suitable-case`: nothing passes the semantic gate; continue with
  `build-new`.

Each returned candidate includes structured `match_reasons`, its `card` and
`asset`, and a `repair_gate` or `blocked_reason` when applicable.

An explicit `--structure`, `--family`, or `--domain` is authoritative over
query inference. Negated phrases such as “not paired” are not positive hard
gates. Candidates are ordered by scientific relevance first; audit and
implementation readiness classify reuse safety and only break semantic ties.

Explicit constraints filter the candidate pool; they do not award relevance
points. When a query is supplied, a candidate must still cross the semantic
relevance threshold. Items that satisfy only an explicit constraint are
returned separately as `constraint_only_candidates` for clarification or
manual inspection and can never turn `no-suitable-case` into `matched`.
Localized structure, domain, and transformation terms come from
[retrieval-lexicon.json](retrieval-lexicon.json); stable contract and catalog
enums come from [schema-vocabularies.json](schema-vocabularies.json).

`--include-conditional` is an inspection switch, not a readiness override. It
may place a semantically relevant conditional case in `matches`; the caller
must still honor `reuse_readiness`, `repair_gate`, and
`has_production_ready_match`.

## Selection record

Add this block to the Figure Contract:

```yaml
implementation:
  case_influence:
    primary: rf-xxxx | null
    contrast: rf-yyyy | null
    reuse_level: exact | structural | style-only | build-new
    borrowed_decisions: []
    retrieval_status: matched | repair-required-only | no-suitable-case
    audit_status_at_selection: admitted | conditional | inspiration | quarantined
    implementation_status_at_selection: verified | language-specific | static-reviewed | failed | unreviewed
    repair_gate_satisfied: true | false | not-applicable
    decisive_match:
      - analysis_unit
      - data_relationship
      - evidence_goal
    rejected_near_match:
      id: rf-yyyy
      reason: ...
```
