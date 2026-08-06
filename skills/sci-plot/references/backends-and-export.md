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

When a SciPlot-native implementation matches the completed Figure Contract,
validate its index with `scripts/validate_implementations.py`, inspect its
manifest, and run it from a task staging directory. A verified runtime does not
override semantic incompatibility. Reference case packs and native
implementations are separate layers.

Renderer defaults are not publication requirements. A default height, DPI,
palette, order, or label policy may be proposed for a prototype, but production
values must be confirmed or justified in the Figure Contract after the actual
panel, category, and sample counts are known.

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

After the renderer succeeds, inspect the exported files rather than inferring
their properties from plotting arguments:

```bash
python scripts/inspect_artifacts.py output/figure.svg \
  --width-mm 180 --height-mm 90 --require-svg-text \
  --output output/artifact-report.json
```

For raster deliverables, pass exact pixel dimensions when known. When physical
dimensions and DPI are both declared, the inspector derives the expected
pixel dimensions:

```bash
python scripts/inspect_artifacts.py output/figure.png \
  --width-mm 180 --height-mm 90 --dpi 300 \
  --output output/preview-report.json
```

Merge the artifact result with the Figure Contract validator output through
`scripts/build_qa_report.py`. Before merging, run
`scripts/validate_delivery.py` against the Figure Contract, Render Manifest,
and output directory. Preserve every input report so a reviewer can trace each
conclusion to its validator.

## Export contract

Choose formats from the actual delivery need:

- editable vector master: SVG or PDF;
- review preview: PNG;
- raster-only scientific imagery: TIFF/PNG at a justified pixel density;
- source data and code alongside the figure when requested.

List every formal artifact in Figure Contract `target.formats`.
`primary_format` names the preferred master and `preview_format` names the
review convenience artifact; neither field implicitly adds a deliverable. If
any declared format is PNG or TIFF, record a positive `resolution_dpi` and
validate the resulting pixel dimensions.

Specify the target physical width and height before layout. Measure the actual
artifact after export. Avoid export options that silently change the page box
or crop labels.

Treat absent DPI metadata as unresolved metadata, not proof that the raster was
rendered at low resolution. Conversely, a correct DPI tag does not compensate
for insufficient pixels. Check pixel dimensions and metadata independently.

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
