# Quality assurance

Static code checks are useful but never prove scientific or visual correctness.
Complete every applicable layer and report `PASS`, `WARN`, or `FAIL` with a
stable check ID.

## QA layers

### FC — Figure Contract

- `FC-01`: one-sentence claim exists.
- `FC-02`: every panel has one distinct question and evidence role.
- `FC-03`: analysis unit, uncertainty, transform, and source mapping are
  defined.
- `FC-04`: target physical size and output stage are defined.

### DI — Data integrity

- `DI-01`: row-count and exclusion ledger reconciles.
- `DI-02`: required keys are unique or an explicit aggregation is declared.
- `DI-03`: transforms pass domain checks.
- `DI-04`: relationship-specific constraints pass.
- `DI-05`: demo data cannot enter production outputs.

### ST — Statistical semantics

- `ST-01`: `n` means the declared analysis unit.
- `ST-02`: center and uncertainty are named exactly.
- `ST-03`: test/model, sidedness, adjustment, and reference level are stated.
- `ST-04`: model assumptions and diagnostics are reported or explicitly
  deferred.
- `ST-05`: descriptive evidence is not labeled inferential or causal.

### RT — Runtime

- `RT-01`: the declared backend runs from a clean entrypoint.
- `RT-02`: all declared outputs are produced.
- `RT-03`: warnings, seeds, dependency versions, and skipped rows are captured.
- `RT-04`: original user files and previous outputs are not overwritten
  unexpectedly.

### DV — Delivery reconciliation

- `DV-01`: the Render Manifest records the exact Figure Contract hash.
- `DV-02`: the delivered formal format set exactly matches `target.formats`.
- `DV-03`: manifest width, height, and raster DPI agree with the contract.
- `DV-04`: every manifest artifact path is safe, exists, and matches its hash.

### AR — Artifact

- `AR-01`: every output opens and has the declared page/pixel dimensions.
- `AR-02`: SVG retains editable text and valid structure when requested.
- `AR-03`: PDF page box, font embedding, and vector/raster content match the
  delivery contract.
- `AR-04`: PNG/TIFF dimensions, DPI metadata, transparency, and color mode are
  appropriate.
- `AR-05`: filenames and panel provenance are unambiguous.

### VV — Final-size visual review

Render at the final physical width, not only at a large screen preview.

- `VV-01`: labels, legends, symbols, and uncertainty marks remain readable.
- `VV-02`: nothing is clipped, overlapped, or hidden by a panel boundary.
- `VV-03`: color remains distinguishable in grayscale and common color-vision
  deficiencies when category identity matters.
- `VV-04`: visual prominence follows evidence hierarchy.
- `VV-05`: axes, baselines, transformations, and truncation cannot mislead.

### CE — Claim–Evidence Checksum

- `CE-01`: every claim has a visible supporting panel or annotation.
- `CE-02`: every panel has a declared claim/evidence role.
- `CE-03`: removing a panel would remove unique evidence; otherwise merge or
  delete it.
- `CE-04`: figure text does not claim more than the supplied analysis supports.

### PR — Provenance

- `PR-01`: code author, data source, inspiration source, and reuse level are
  recorded separately.
- `PR-02`: each panel records its renderer/backend and source inputs.
- `PR-03`: external thresholds, boundaries, gene sets, and precomputed model
  outputs have sources.

## Evidence ownership

The check ID names a scientific or delivery assertion; it does not imply that
one script can prove the whole assertion. Keep automatic evidence and required
judgment explicit:

| Layer | Primary evidence source | Automation boundary |
|---|---|---|
| `FC`, `DI`, `ST`, `CE`, `PR` | Figure Contract, source mapping, analysis records, reviewer judgment | `validate_contract.py` checks structural precursors with separate `CT-*` IDs; it does not award these end-to-end IDs automatically |
| `RT` | clean-entrypoint run, logs, environment record, Render Manifest | renderer/runtime specific; a zero exit code is insufficient |
| `DV` | Figure Contract, Render Manifest, delivered files | `validate_delivery.py` emits deterministic `DV-*` results |
| `AR` | bytes and measured file metadata | `inspect_artifacts.py` emits `AR-*`; its documented heuristics remain limitations |
| `VV` | original-resolution render reviewed at target physical size | human/visual review required; never infer `VV-02` from a coarse bounding-box estimate alone |

`build_qa_report.py` merges evidence and preserves its source layer; it does
not upgrade an unperformed manual check to `PASS`.

## Failure policy

Do not deliver a production figure with unresolved `FAIL`. `WARN` requires a
plain-language note explaining the remaining limitation. A successful process
exit or an attractive preview cannot override a semantic failure.

## QA report

Deliver a compact machine-readable report containing:

```json
{
  "status": "PASS|WARN|FAIL",
  "checks": [{"id": "FC-01", "status": "PASS", "evidence": "..."}],
  "unresolved": [],
  "artifacts": [],
  "final_size_reviewed": true
}
```

## Deterministic artifact inspection

Run artifact inspection **after** export against the files that will actually
be delivered. Do not substitute source-code linting for this step.

First reconcile the production contract and Render Manifest:

```bash
python scripts/validate_delivery.py \
  --contract figure-contract.json \
  --manifest output/composition.manifest.json \
  --artifact-dir output \
  --pretty --output delivery-report.json
```

This fails if a renderer produced a different formal format set, dimensions,
or raster DPI, if it did not bind the exact contract hash, or if a manifest
artifact is missing or was changed after rendering. It complements artifact
inspection, which measures the file content itself.

```bash
python scripts/inspect_artifacts.py figure.svg \
  --width-mm 180 --height-mm 90 --require-svg-text \
  --pretty --output artifact-report.json

python scripts/inspect_artifacts.py preview.png \
  --width-px 2126 --height-px 1063 --dpi 300 \
  --pretty --output preview-report.json
```

The inspector emits `sciplot.artifact-qa/v1` JSON with stable `AR-*` check IDs,
artifact hashes, measured metadata, and unresolved findings. It reads SVG,
PDF, and PNG structure using the Python standard library. TIFF metadata and
raster-content heuristics use Pillow only when it is already installed; an
unavailable optional dependency produces `WARN` and is never auto-installed.
PDF inputs must contain a coherent terminal cross-reference table or
cross-reference stream; a file that merely contains PDF-looking markers fails
closed.

Use `--strict` for a release gate only when every warning must block delivery.
It promotes every `WARN` to `FAIL`. A non-strict `WARN` still requires a
plain-language limitation in the handoff.

The inspector is deliberately conservative:

- SVG clipping checks only inspect basic viewBox/text-anchor risk.
- Raw PDF checks can inspect MediaBox and common font/content markers, but
  cannot prove visual correctness or font embedding in every PDF encoding.
- Raster blank-image heuristics are stronger when Pillow is available.

Therefore, artifact inspection does not replace the `VV-*` final-size visual
review.

All helper commands that accept `--output` refuse to write to one of their own
input paths, including equivalent hard-link or resolved paths. Keep reports in
separate files; this guard prevents a QA command from overwriting the artifact,
contract, or report it is meant to inspect.

## Merge validator evidence

Keep each validator report, then merge them without discarding provenance:

```bash
python scripts/validate_contract.py contract.json \
  --stage final --pretty > contract-report.json
python scripts/build_qa_report.py \
  contract-report.json delivery-report.json \
  artifact-report.json preview-report.json \
  --pretty --output qa-report.json
```

`build_qa_report.py` accepts one report for normalization or multiple reports
for merging. It emits `sciplot.qa-report/v1`, normalizes `message` to
`evidence`, preserves the source layer for each check, deduplicates artifacts,
collects SHA-256 hashes, and derives the overall result using
`FAIL > WARN > PASS`. Missing or malformed check arrays fail closed rather than
becoming an implicit pass. Explicit unresolved findings also contribute to the
overall severity and are promoted into checks when no equivalent check already
represents them.
