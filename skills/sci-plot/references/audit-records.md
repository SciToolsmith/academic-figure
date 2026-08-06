# Auditable records

Use these records for publication-oriented Create, Adapt, or structural Revise
tasks. A small single-panel task may store them in one JSON document, but keep
their meanings separate.

## Contents

- [Figure Contract](#figure-contract)
- [Figure Plan](#figure-plan)
- [Render Manifest](#render-manifest)
- [QA Report](#qa-report)
- [Revision ledger](#revision-ledger)

## Figure Contract

The Figure Contract is the scientific fact source. Follow
[figure-contract.md](figure-contract.md). Do not put renderer-specific
coordinates or styling constants into scientific fields.

## Figure Plan

The plan compiles the contract into an evidence architecture:

```json
{
  "plan_version": 1,
  "contract": "figure-contract.json",
  "execution_state": "proceed",
  "reading_order": ["a"],
  "panels": [
    {
      "id": "a",
      "question": "What changed within each complete pair?",
      "evidence_role": "primary",
      "evidence_atoms": ["observation", "identity", "estimate", "uncertainty"],
      "supports_claims": ["C1"],
      "encoding": {
        "geometry": "paired points and links with interval summary",
        "x": "declared visit order",
        "y": "response in declared units",
        "color": "neutral identity-preserving marks",
        "annotation": "complete-pair n and interval definition"
      },
      "counter_reading": "unpaired rows could be mistaken for independent groups",
      "countermeasure": "retain pair links and state the paired estimand"
    }
  ],
  "case_influence_ref": "figure-contract.json#/implementation/case_influence"
}
```

Every panel must map to a contract claim, diagnostic need, or necessary
context. Keep the canonical case-selection record at
`implementation.case_influence` in the Figure Contract; the plan references it
instead of maintaining a second copy that can drift. Cases may influence the
plan but cannot change the contract.

## Render Manifest

Record what actually produced each artifact:

```json
{
  "render_version": 1,
  "figure_contract": {
    "file": "figure-contract.json",
    "sha256": "...",
    "phase": "descriptive",
    "formats": ["svg", "pdf", "png"]
  },
  "plan_sha256": "...",
  "environment": {
    "platform": "...",
    "locale": "...",
    "fonts": [],
    "packages": {}
  },
  "panels": {
    "a": {
      "backend": "python",
      "entrypoint": "render.py",
      "inputs": ["measurements.csv"],
      "seed": 20260805
    }
  },
  "final_assembly_owner": "python",
  "figure": {
    "width_mm": 89,
    "height_mm": 78,
    "dpi_for_raster": 300
  },
  "artifacts": [
    {
      "path": "figure.svg",
      "role": "editable-master",
      "sha256": "...",
      "width_mm": 89,
      "height_mm": 78
    }
  ],
  "warnings": []
}
```

Do not record temporary absolute paths in publication text. Hash source inputs
when practical; never modify the source merely to obtain a convenient hash.
Before delivery, run `scripts/validate_delivery.py` so the contract hash,
formal format set, dimensions, DPI, artifact paths, and hashes are reconciled
against the actual manifest rather than trusted independently.

## QA Report

Use stable IDs from [qa.md](qa.md). Every check contains:

```json
{
  "id": "AR-01",
  "status": "PASS",
  "message": "SVG opens and matches the declared dimensions",
  "evidence": ["figure.svg", "89.0 mm × 78.0 mm"]
}
```

`FAIL` blocks production delivery. `WARN` requires a stated limitation or
accepted rationale. A check must not be marked `PASS` when it was not run;
use `WARN` or an explicit `NOT-CHECKED` evidence message.

## Revision ledger

For Revise and Adapt, record:

```json
{
  "requested_changes": [],
  "meaning_locked": [
    "analysis unit",
    "included observations",
    "transformation",
    "denominator",
    "uncertainty",
    "test or model"
  ],
  "before": {},
  "after": {},
  "semantic_changes": [],
  "artifact_changes": [],
  "acceptance_results": []
}
```

An empty `semantic_changes` list is an assertion to verify, not boilerplate.
When a requested visual change necessarily changes interpretation, stop and
explain the consequence before applying it.

Compare serialized contracts with:

```bash
python scripts/semantic_diff.py before.json after.json \
  --pretty --output semantic-diff.json
```

Use `--allow-prefix` only for a scientific change the user explicitly
authorized after its consequence was explained.

The result follows `sciplot.semantic-diff/v1` and exposes a `checks` array, so
`scripts/build_qa_report.py` can merge it with contract and artifact results.
