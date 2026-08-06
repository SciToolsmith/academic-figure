# Verified implementations

Reference cases and runnable implementations are deliberately separate.
Retrieve a case for scientific expression first. Select an implementation only
after the Figure Contract and Semantic Distance Gate are complete.

The machine index is
[`implementations/implementation-index.json`](../implementations/implementation-index.json).
Validate it with:

```bash
python scripts/validate_implementations.py --pretty
```

## `composition-bars-v1`

Purpose: compare category shares across sample-level compositions, optionally
separated into declared facets.

Use only when:

- every bar has a meaningful and explicit common denominator;
- the analysis unit is a sample within a facet;
- every sample has the same declared category set, with known zeros represented
  explicitly;
- the task phase is `descriptive` when counts are converted to shares, or
  `presentation` when already finalized proportions are only communicated;
- the task is not inferential.

The renderer accepts a long CSV and explicit column bindings. Proportion mode
requires every sample to sum to one within a declared tolerance. Count mode
performs the requested count-to-share conversion and records every denominator
in the Render Manifest. It rejects nonfinite values, negative values, duplicate
keys, incomplete category grids, unknown orders, simulated rows passed as
production, and output overwrites.

Example smoke test:

```bash
python implementations/python/composition-bars-v1/render.py \
  --input implementations/python/composition-bars-v1/examples/demo.csv \
  --data-manifest implementations/python/composition-bars-v1/examples/demo-data.json \
  --figure-contract references/figure-contract.descriptive-composition.example.json \
  --output-dir /tmp/sciplot-composition-smoke \
  --run-mode smoke \
  --value-mode proportion \
  --facet-order "Day 0,Day 7" \
  --category-order "Alpha,Beta,Gamma,Other"
```

The smoke fixture is visibly watermarked and its data manifest sets
`production_use_allowed: false`. Production runs require `--run-mode
production` and a non-synthetic data manifest whose input hash matches the
CSV. They also require `--figure-contract`; the renderer refuses to run unless
the contract phase, included-row count, formats, physical dimensions, raster
DPI, and native implementation ID agree with the validated input and CLI.

Outputs are SVG, PDF, PNG, `analysis-table.csv`, `data-validation.json`, and
`composition.manifest.json`. The renderer sets physical dimensions before
layout, writes the bundle through a temporary staging directory, refuses a
non-empty destination, and does not use a tight-crop export that would silently
change the page box.

Declare all three formal outputs in `target.formats`; use `primary_format` and
`preview_format` only to assign their roles. Because PNG is present, the Figure
Contract must also declare a positive `resolution_dpi`.

The CLI's 183 × 105 mm and 300 dpi values are implementation defaults, not
journal requirements. For a production run, explicitly pass values approved by
the Figure Contract after the actual facet, sample, and category counts are
known.

## `raw-distribution-v1`

Purpose: show every declared independent observation before a descriptive
within-group median and interquartile range.

Use only when:

- one stable observation ID identifies one analysis and replicate unit;
- values are finite and groups are mutually interpretable;
- there is no paired or repeated-measures structure to preserve;
- median and IQR are intended as descriptive summaries, not confidence
  intervals;
- the task does not ask this renderer to establish a statistical or causal
  group difference.

The renderer rejects duplicate observation IDs, blank roles, nonfinite values,
groups with fewer than two observations, incomplete declared group orders, and
synthetic inputs presented as production. Jitter is a deterministic
SHA-256-derived display offset, so it does not change between runs. The
analysis table retains every input value and the group-local summary used by
the marks.

## `paired-change-v1`

Purpose: preserve identity while showing change between exactly two declared
timepoints, separately for declared groups when present.

Use only when:

- `(subject, timepoint)` is unique;
- every included subject has exactly the same two timepoints;
- group membership is stable within subject;
- `end − start` is the declared descriptive change;
- incomplete pairs have already been handled by an explicit scientific rule.

The renderer fails closed on duplicate keys, incomplete pairs, group drift,
unknown timepoint or group orders, and nonfinite values. Every plotted line is
one subject. It reports the within-group median change for orientation, but
does not compute a between-group effect, confidence interval, p-value, or
causal result.

## `effect-forest-v1`

Purpose: present finalized, precomputed point estimates and intervals without
refitting a model or inventing statistical semantics.

Use only when:

- every row has a unique label and finite `estimate`, `lower`, and `upper`;
- every interval satisfies `lower ≤ estimate ≤ upper`;
- the effect scale, interval definition, reference value, and display order
  are declared;
- the source analysis and its estimand remain authoritative.

The renderer does not compute estimates, intervals, p-values, pooling, subgroup
tests, or causal identification. Its Render Manifest records that the input is
precomputed and preserves the supplied scale, interval label, reference, and
row order. When a Figure Contract is supplied, the renderer also requires an
exact match for the label/group/estimate/lower/upper column roles, effect
scale, interval label, reference value, and x-axis label declared under
`implementation.native_implementation.semantic_bindings`. It rejects reused
`estimate`/`lower`/`upper` columns before reading values.

## Shared verification boundary

All four native renderers:

- require a non-synthetic, authorized data manifest and a Figure Contract in
  production mode;
- require the canonical Figure Contract `final` gate to return `PASS` before
  creating an output directory, and record its lint summary in the Render
  Manifest;
- bind the task phase, included-row count, formats, physical size, raster DPI,
  and selected implementation ID before rendering;
- write SVG/PDF/PNG, `analysis-table.csv`, `data-validation.json`, and a
  hash-bearing Render Manifest through a temporary staging directory;
- refuse a non-empty destination instead of overwriting existing outputs;
- keep demo fixtures visibly watermarked and impossible to declare as
  production, including when their CSV bytes are copied elsewhere or only a
  provenance field, row order, column order, surrounding whitespace,
  equivalent decimal notation, or a mapped scientific-role column name is
  changed and the copy is paired with a forged production manifest;
- have a checked source hash, deterministic smoke fixture, final-size visual
  review, and live artifact QA evidence.

These implementations cover four common evidence structures; they are not a
closed chart menu. If none is semantically compatible, record
`no-suitable-case`/`build-new` as appropriate and implement from the Figure
Contract rather than forcing a near match.
