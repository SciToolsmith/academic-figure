# Case code and adaptation

SciPlot keeps three layers separate:

1. **Semantic case card** — the scientific expression decision, risks, and
   reuse gates in `case-index.json` and the Markdown case cards.
2. **Reference source pack** — the project author's Python/R reproduction in
   `assets/case-packs/<case-id>/`, plus the already rendered preview.
3. **Verified implementation** — a reusable renderer with an explicit input
   contract, guards, fixtures, runtime evidence, export contract, and tests.

Available native implementations are listed separately in
[implementation-catalog.md](implementation-catalog.md). A case may influence
an implementation, but the implementation is new SciPlot code and carries its
own contract and verification evidence.

A source pack is useful evidence about layout and implementation choices, but
it is not automatically a verified implementation. The 18 bundled source
packs do not contain the papers' original data. Most expect input files that
are not distributed with the skill.

For a production task, prefer a compatible SciPlot-native verified
implementation after the semantic gate. Inspect or stage a reference source
pack only when no native implementation matches, when forensic comparison is
useful, or when the user explicitly requests a faithful reconstruction.

## Decide the execution state

Choose one state after the Semantic Distance Gate:

| State | Meaning | May run case source? |
|---|---|---|
| `EXACT_RUN` | Scientific and input contracts match exactly | Only a verified implementation |
| `BIND_ONLY` | Same evidence logic; explicit field binding is sufficient | Only after all mapping and repair gates pass |
| `STYLE_INHERIT` | Reuse visual parameters or annotation grammar only | No; rebuild the analysis and marks |
| `GENERATE_NEW` | No compatible case or implementation | No; use the figure grammar |
| `ASK_OR_BLOCK` | A scientific unknown prevents a valid result | No production rendering |

`EXACT_RUN` and `BIND_ONLY` are stricter than “the script runs.” A successful
example render does not prove that the new analysis unit, denominator,
uncertainty, or transformation is compatible.

The case catalog's `implementation_status` describes the logical case figure
at the time it was audited in the source project. It does not mean that both
bundled Python and R entrypoints, their missing inputs, or a new user's mapping
have all passed production verification. Use the source pack's separate
`smoke_status` and the native implementation manifest for those narrower
claims.

## Inspect before adapting

After semantic retrieval selects a case:

```bash
python scripts/stage_case.py --describe rf-0001 --json
```

The description exposes the available backends, expected filenames, code
provenance, licensing, and smoke-test status. If a source inspection is useful,
stage exactly one backend into a new empty task directory:

```bash
python scripts/stage_case.py rf-0001 \
  --backend python \
  --reuse-level structural \
  --workdir /path/to/new-task-directory
```

Never execute or edit the bundled source in place. Work only on the staged
copy, keep the original source hash in `case-adaptation.json`, and record every
change.

## Complete the mapping ledger

Before running staged code, fill in:

- source field → scientific role → renderer field;
- units and allowed values;
- analysis and replicate units;
- category and facet order;
- denominator or weighting rule;
- center and uncertainty definitions;
- precomputed versus recomputed quantities;
- exclusion predicates with before/after counts.

Add a guard for every relevant transformation:

- log: finite, strictly positive input;
- ratio or proportion: explicit denominator, denominator nonzero;
- square root: nonnegative input;
- min-max scaling: finite, nonconstant range;
- binning or density: declared bin or bandwidth rule;
- PCA, clustering, or embedding: input matrix and whether coordinates are
  precomputed;
- paired or longitudinal analysis: unique entity/time keys and explicit
  incomplete-pair policy.

An empty mapping ledger means `mapping-required`, not permission to run.

## Demo data is not evidence

`scripts/generate_case_demo.py` creates deterministic synthetic inputs only
for selected smoke tests. It writes `demo-data.json` with
`production_use_allowed: false`. Demo values must never enter a manuscript
figure, a reported statistic, or a production Render Manifest.

At present the smoke generator covers:

- `rf-0001`: a fixed-seed composition input required by the reproduction;
- `rf-0178`: positive-valued grouped data for log-domain and rendering checks.

The other source packs remain inspectable and stageable, but their required
data are not bundled. Do not fabricate replacements merely to make them run.

## Degrade safely

If a source pack is incomplete, incompatible, or fails:

1. do not patch around a scientific guard;
2. record the failure and the decisive incompatibility;
3. downgrade from `EXACT_RUN`/`BIND_ONLY` to `STYLE_INHERIT` or
   `GENERATE_NEW`;
4. preserve the intended evidence role with a new renderer;
5. run artifact and scientific QA on the new result.

Do not place a reference PNG inside a final PDF/SVG to simulate vector reuse.
When editable vector output is required, recreate the marks and text as vector
objects.
