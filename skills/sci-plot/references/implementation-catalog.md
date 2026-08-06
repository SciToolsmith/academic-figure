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
