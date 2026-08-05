# Data integrity

Treat the scientific meaning of the data as an invariant throughout plotting.

## Contents

- [Analysis-unit ledger](#analysis-unit-ledger)
- [Field-mapping ledger](#field-mapping-ledger)
- [Row-count ledger](#row-count-ledger)
- [Transform guards](#transform-guards)
- [Relationship-specific checks](#relationship-specific-checks)
- [Scientific Mutation Budget](#scientific-mutation-budget)
- [Demo and provenance separation](#demo-and-provenance-separation)

## Analysis-unit ledger

Before coding, record:

```text
analysis unit -> source rows/files -> biological or technical replicate
group field -> category order -> reference level
measurement -> units -> valid range
uncertainty -> source/calculation -> exact definition
```

Do not substitute rows, columns, units, denominators, or replicate definitions
to fit a template.

## Field-mapping ledger

For structural adaptation, record every mapping:

```text
case field -> user field -> semantic role -> units -> allowed values
```

Reject the adaptation when a required role has no valid user field. Do not
silently choose the first numeric columns.

## Row-count ledger

Report:

- rows received;
- rows excluded by each exact predicate;
- rows remaining;
- unique analysis units before and after;
- missing values by required field;
- duplicated keys and their resolution.

Use all in-scope observations by default. Preview sampling must be declared,
seeded, reversible, and isolated from final statistics.

## Transform guards

Validate the definition domain before applying:

- log or ratio transformations;
- square root;
- normalization and standardization;
- compositional closure;
- smoothing or interpolation;
- PCA, clustering, ordination, or distance calculations.

Record pseudocounts, reference levels, distance metrics, linkage, bandwidths,
and smoothing engines. Never let a visual default silently determine an
analytical choice.

## Relationship-specific checks

- **Paired:** preserve pair IDs; report complete-pair counts per comparison;
  handle ties and zero differences honestly.
- **Longitudinal:** preserve subject IDs and time ordering; distinguish
  within-subject trajectories from group trends.
- **Time-to-event:** validate event/censor definitions and event time within
  follow-up.
- **Composition:** state the denominator; verify closure tolerance; distinguish
  absent, zero, and unobserved categories.
- **Sets:** state deduplication and membership rules; distinguish all
  intersections from displayed top intersections.
- **Flow:** require a valid record key across stages; state whether ribbon
  width represents records, mass, or another weight; verify conservation when
  applicable.
- **Spatial:** record CRS, boundary source/date, join success, and missing
  geometries; make symbol area proportional to magnitude when claiming so.
- **Embedding:** state whether coordinates are supplied or recomputed; never
  present simulated geometry as analytical evidence.

## Scientific Mutation Budget

Allow visual adaptation freely only when it does not change scientific
semantics. Assign zero tolerance to unreported changes in:

- analysis unit;
- included observations;
- transformation;
- denominator;
- uncertainty;
- statistical test;
- model output;
- topology or record linkage.

Any required semantic change means `build anew`, not template adaptation.

## Demo and provenance separation

Keep synthetic/demo data on a separate path from production data. Mark
recreated examples with `recreated_by`, and record `inspired_by` and
`data_source` independently. A paper citation is provenance; it is not a
substitute for documenting the actual data supplied to the renderer.
