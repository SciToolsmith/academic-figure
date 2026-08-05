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
