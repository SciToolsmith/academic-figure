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
- [Case and implementation status](#case-and-implementation-status)
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

Reject a case when a hard constraint conflicts. Record `no suitable case`
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

## Case and implementation status

Track two separate states:

- logical-figure status: `admitted`, `conditional`, `inspiration`,
  `quarantined`;
- implementation status: `verified`, `language-specific`,
  `static-reviewed`, `failed`, `unreviewed`.

A folder can contain multiple logical figures. Python and R files with similar
names are not assumed equivalent. Use a conditional case only after satisfying
its stated repair gate. Never retrieve a quarantined or failed implementation
as a production template.

## Selection record

Add this block to the Figure Contract:

```yaml
case_selection:
  primary: rf-xxxx | none
  contrast: rf-xxxx | none
  reuse_level: exact | structural | style-only | build-new
  decisive_match:
    - analysis_unit
    - data_relationship
    - evidence_goal
  rejected_near_match:
    id: rf-yyyy
    reason: ...
```
