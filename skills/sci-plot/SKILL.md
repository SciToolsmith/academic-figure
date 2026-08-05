---
name: sci-plot
description: Design, implement, revise, and audit data-driven scientific figures and multi-panel evidence layouts. Use for 科研绘图、论文图、Nature-style or journal-ready publication figures, selecting evidence-appropriate visual encodings, adapting an audited case to new data, improving an existing plot without silently changing its scientific meaning, or reviewing figure code and rendered artifacts for statistical semantics, data integrity, readability, reproducibility, and export quality. Supports Python/R workflows and editable vector or raster deliverables.
---

# SciPlot

Treat a scientific figure as an auditable visual argument:

`question or claim → evidence → panel roles → visual encoding → rendered artifact`

Optimize scientific fidelity and reader reasoning before aesthetics. Do not imitate a reference image at the expense of the data-generating process, analysis unit, uncertainty, or claim.

Treat “Nature-style” as a request for restrained, evidence-led publication
design, not as an official affiliation or a universal visual preset.

## Route the task

Classify the request before acting:

- **Create**: design and render a new figure from data, results, or a scientific question.
- **Revise**: change an existing figure, script, or layout while preserving all scientific meanings outside the requested change.
- **Review**: inspect figures, code, data mappings, or exports. Remain read-only unless the user also asks for implementation.

For open-ended exploration, record an exploratory question instead of inventing a confirmatory claim. Produce candidate views and label them exploratory.

For a small cosmetic revision, use a minimal contract and avoid redesigning unrelated parts. For a structural revision, treat the task as Create while preserving a before/after change ledger.

## Follow the core workflow

1. **Inspect inputs**
   - Inventory data, code, existing figures, captions, analysis outputs, requested formats, and available runtimes.
   - Identify what is observed, computed, inferred, or still unknown.
   - Never infer units, replicate units, uncertainty definitions, or test meanings from appearance alone.

2. **Establish the Figure Contract**
   - Read [figure-contract.md](references/figure-contract.md).
   - Write the smallest contract appropriate to the route before choosing a layout.
   - Ask only questions that block a scientifically valid result; mark non-blocking gaps as `unknown` and disclose them.

3. **Design the evidence architecture**
   - Read [figure-grammar.md](references/figure-grammar.md) for the case-independent design path.
   - Assign every panel one question and one evidence role: primary, supporting, control, diagnostic, or context.
   - Link every stated claim to its supporting panels. Remove panels that add no unique evidence or necessary orientation.
   - Select encodings from the data structure and inferential goal, not from visual novelty.

4. **Optionally use cases semantically**
   - Treat cases as design priors, not dependencies. Complete the evidence architecture first.
   - Read [case-index.md](references/case-index.md) first; do not load the full case library.
   - Read [case-selection.md](references/case-selection.md) when matching a case or deciding the reuse level.
   - Load only the selected entries from [cases-core.md](references/cases-core.md) or [cases-extensions.md](references/cases-extensions.md).
   - Read [risk-cards.md](references/risk-cards.md) when reviewing a figure or when a planned encoding has a known failure mode.
   - Permit `no suitable case`. Record `build-new` and continue through implementation; never stop merely because the library has no match.

5. **Protect data and statistical meaning**
   - Read [data-integrity.md](references/data-integrity.md) whenever the task involves filtering, missing values, transformations, aggregation, sampling, repeated measures, uncertainty, or statistical annotations.
   - Preserve all requested observations by default.
   - Record every exclusion, transformation, aggregation, and preview sample with its rule and before/after count.
   - Keep demo data separate from production data. Never replace missing results with invented values.
   - Do not silently recompute or change the user's analysis during a visual revision.

6. **Implement and export**
   - Read [backends-and-export.md](references/backends-and-export.md) after the contract fixes the output requirements.
   - Choose Python, R, or a documented mixed workflow per task; do not persist a global backend preference.
   - Use one declared owner for final multi-panel assembly and retain panel-level provenance.
   - Treat case code as a design reference unless it is explicitly audited and compatible. Never execute unknown example scripts merely because their preview looks suitable.
   - Prefer editable text and vector geometry; rasterize only dense marks or inherently raster data.

7. **Render and verify**
   - Read [qa.md](references/qa.md) before declaring completion.
   - Run the actual code, open the actual artifacts, and inspect them at the intended physical size.
   - Verify statistical semantics, data-to-mark traceability, accessibility, clipping, typography, panel alignment, dimensions, fonts, and file integrity.
   - Distinguish code lint, runtime success, artifact validity, visual quality, and scientific validity; none proves the others.

Use `scripts/rank_cases.py` only to retrieve candidates after scientific hard
constraints are known. Use `scripts/validate_contract.py` to lint a serialized
Figure Contract. Neither script replaces scientific judgment.

## Preserve these invariants

- Keep the scientific question, analysis unit, and replicate unit explicit.
- Make `n`, denominator, units, center, uncertainty, test, and multiplicity correction unambiguous wherever they affect interpretation.
- Do not hide inconvenient points, missingness, null results, or long tails for visual neatness.
- Do not use color, area, length, ordering, smoothing, or axis limits in ways that exaggerate evidence.
- Default bars and filled areas to a meaningful zero baseline; disclose any justified exception.
- Separate descriptive, associational, predictive, and causal claims.
- Keep precomputed coordinates or statistics labeled as such; do not imply they were recomputed.
- Preserve user-owned work and avoid unrelated file changes.

## Reuse a case at the right level

Choose exactly one:

1. **Exact reuse** — same scientific semantics, dimensions, transformations, and compatible input schema.
2. **Structural adaptation** — same evidence logic with an explicit field, unit, category-order, and replicate mapping.
3. **Style-only inheritance** — borrow visual tokens or annotation grammar, not statistical logic.
4. **Build anew** — use when the scientific question, data structure, or inferential assumptions differ.

The user's data and Figure Contract remain authoritative at every level.

## Deliver by route

For **Create** or **Revise**, deliver:

- runnable source code and any explicit configuration;
- an editable primary artifact when feasible, plus a review preview;
- the completed or updated Figure Contract;
- a concise record of exclusions, transformations, statistics, case influence, and backend provenance;
- QA results and unresolved limitations.

For **Review**, deliver:

- the inferred claim/evidence map, including confidence and unknowns;
- issues grouped by scientific meaning, data integrity, statistical semantics, visual communication, reproducibility, and export;
- severity, evidence, and a scoped remedy for each actionable issue;
- no file changes unless separately authorized.
