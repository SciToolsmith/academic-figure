# Backends and export

## Backend selection

Resolve the backend in this order:

1. explicit request for the current task;
2. project-local configuration;
3. compatibility with the supplied data and required analysis;
4. a recommendation made for this task only.

Do not persist a global Python/R preference unless the user explicitly asks.
Reviewing an existing PDF, SVG, or PNG does not require choosing a plotting
backend.

Use Python when its data/analysis stack or integration is the better fit. Use
R when its statistical or domain package ecosystem is the better fit. Do not
choose a language for stylistic identity.

## Mixed workflows

Allow panel-level backends when scientifically justified. Record the backend,
entrypoint, inputs, and version for every panel, and assign one **final assembly
owner** responsible for:

- physical dimensions;
- typography and color tokens;
- panel alignment and labels;
- final export;
- provenance manifest.

Forbid opaque cross-language redraws. The goal is a traceable final artifact,
not language purity.

## Reproducibility

Record:

- interpreter and package versions;
- locale and fonts;
- random seeds;
- analysis entrypoint and renderer entrypoint;
- source file hashes when practical;
- warnings and excluded rows.

Do not auto-install packages, download unrequested assets, or execute
unreviewed case scripts.

## Renderer protocol

Keep four layers separate:

1. input schema validation and row-count ledger;
2. analysis or consumption of precomputed results;
3. panel rendering from explicit analysis tables;
4. final assembly, export, and artifact inspection.

Do not bury statistical analysis inside drawing calls. Make the renderer
consume named quantities whose units and uncertainty already match the Figure
Contract.

Prefer one non-interactive entrypoint with explicit arguments equivalent to:

```text
--input
--contract
--output-dir
--format
--width-mm
--height-mm
--seed
```

Return nonzero on invalid inputs or missing outputs. Emit an analysis/source
table, figure artifact, preview, and QA/provenance JSON when applicable.
Never depend on an absolute path from a case example.

## Export contract

Choose formats from the actual delivery need:

- editable vector master: SVG or PDF;
- review preview: PNG;
- raster-only scientific imagery: TIFF/PNG at a justified pixel density;
- source data and code alongside the figure when requested.

Specify the target physical width and height before layout. Measure the actual
artifact after export. Avoid export options that silently change the page box
or crop labels.

Do not hardcode journal specifications as universal truth. Verify the current
target-journal instructions when a submission target is named, then record the
source and access date in the Figure Contract.

## Delivery manifest

Deliver:

```text
figure source
analysis/renderer code
editable master
review preview
source-data mapping
QA report
provenance and environment manifest
```

Separate production artifacts from temporary renders and never overwrite user
inputs.
