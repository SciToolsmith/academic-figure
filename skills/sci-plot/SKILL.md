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
- **Adapt**: reproduce or adapt a reference figure, case, or visual system to new
  data only after its scientific semantics pass the compatibility gate.
- **Revise**: change an existing figure, script, or layout while preserving all scientific meanings outside the requested change.
- **Review**: inspect figures, code, data mappings, or exports. Remain read-only unless the user also asks for implementation.
- **Export**: validate or convert existing figure artifacts without silently
  changing their visual or scientific meaning.

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
   - For each publication-confirmatory quantitative claim, declare its
     estimand before rendering: population or system, analysis unit, outcome
     and horizon, contrast or exposure, summary measure and effect scale,
     adjustment or aggregation, and missing-data policy. Link the claim and
     every primary or supporting panel that bears on it to the same
     `estimand_id`.
   - Set the execution state to `proceed`, `prototype-only`, or `blocked`.
     Never produce a production figure while a blocking scientific unknown
     remains.

3. **Design the evidence architecture**
   - Read [figure-grammar.md](references/figure-grammar.md) for the case-independent design path.
   - Assign every panel one question and one evidence role: primary, supporting, control, diagnostic, or context.
   - Link every stated claim to its supporting panels. Remove panels that add no unique evidence or necessary orientation.
   - Select encodings from the data structure and inferential goal, not from visual novelty.

4. **Optionally use cases semantically**
   - Treat cases as design priors, not dependencies. Complete the evidence
     architecture and resolve the relevant semantic hard constraints first.
   - Read [case-index.md](references/case-index.md) first; do not load the full case library.
   - Read [case-selection.md](references/case-selection.md) when matching a case or deciding the reuse level.
   - Load only the selected entries from [cases-core.md](references/cases-core.md) or [cases-extensions.md](references/cases-extensions.md).
   - Read [risk-cards.md](references/risk-cards.md) when reviewing a figure or when a planned encoding has a known failure mode.
   - Permit an explicit `no-suitable-case` outcome. Record `build-new` and
     continue through implementation; never stop merely because the library
     has no match.
   - If source code would help, read [case-code.md](references/case-code.md).
     Keep the semantic card, reference source, and verified implementation as
     separate layers.
   - For production, prefer a semantically compatible verified native
     implementation. Inspect a reference source pack when no native
     implementation matches or the user explicitly requests a faithful
     reconstruction; source availability never overrides semantic fit.

5. **Protect data and statistical meaning**
   - Read [data-integrity.md](references/data-integrity.md) whenever the task involves filtering, missing values, transformations, aggregation, sampling, repeated measures, uncertainty, or statistical annotations.
   - Preserve all requested observations by default.
   - Record every exclusion, transformation, aggregation, and preview sample with its rule and before/after count.
   - Keep demo data separate from production data. Never replace missing results with invented values.
   - Do not silently recompute or change the user's analysis during a visual revision.

6. **Implement and export**
   - Read [backends-and-export.md](references/backends-and-export.md) after the contract fixes the output requirements.
   - Read [implementation-catalog.md](references/implementation-catalog.md)
     when the provisional contract contains enough fields to judge
     compatibility. While blocked, catalog inspection may remain read-only,
     but implementation selection and execution must wait.
   - A verified implementation is optional acceleration, not a capability
     boundary. If none matches the analysis unit, relationship, input
     structure, evidence goal, and task phase, record `build-new` and continue
     from the Figure Contract.
   - Choose Python, R, or a documented mixed workflow per task; do not persist a global backend preference.
   - Use one declared owner for final multi-panel assembly and retain panel-level provenance.
   - Treat bundled case code as inspectable reference source, not as a
     production template. Use `scripts/stage_case.py` to copy one selected
     backend into a new task directory; never edit or execute it in place.
   - Exact or structural reuse requires a completed field/unit/replicate/
     uncertainty mapping and every relevant transformation guard. Style-only
     reuse must not execute the case's statistical logic.
   - Use generated demo inputs only for smoke tests. Never place demo values in
     a production figure or Render Manifest.
   - Prefer editable text and vector geometry; rasterize only dense marks or inherently raster data.
   - Treat implementation defaults for height, DPI, order, and palette as
     disclosed proposals only. Confirm or derive them in the Figure Contract
     before production rendering.

7. **Render and verify**
   - Read [qa.md](references/qa.md) before declaring completion.
   - Run the actual code, open the actual artifacts, and inspect them at the intended physical size.
   - Verify statistical semantics, data-to-mark traceability, accessibility, clipping, typography, panel alignment, dimensions, fonts, and file integrity.
   - Distinguish code lint, runtime success, artifact validity, visual quality, and scientific validity; none proves the others.
   - Iterate `render → inspect → fix → rerender` until no production-blocking
     failure remains.

Use `scripts/rank_cases.py` only to retrieve candidates after scientific hard
constraints are known. Use `scripts/validate_contract.py` to lint a serialized
Figure Contract. Use `scripts/validate_delivery.py` to reconcile its declared
formats, dimensions, DPI, hash, and included outputs with the actual Render
Manifest. Use `scripts/inspect_artifacts.py` on rendered files and
`scripts/build_qa_report.py` to assemble the machine-readable delivery report.
For Revise or Adapt, use `scripts/semantic_diff.py` to detect changes to locked
scientific meanings.
Use `scripts/stage_case.py` to inspect or stage a selected reference source
pack and `scripts/generate_case_demo.py` only for supported synthetic smoke
tests.
Use `scripts/validate_implementations.py` before running a bundled native
implementation; its presence never overrides the semantic gate.
Use `scripts/sciplot_doctor.py` when local Python or native-renderer
dependencies are uncertain; it diagnoses without rendering. The
index-driven `scripts/run_implementation_smoke.py` is a maintainer and release
gate, not a substitute for per-figure scientific and final-size visual QA.
These tools make deterministic checks; none replaces scientific or final-size
visual judgment.
Script paths in this skill are relative to the installed `sci-plot` directory.
From this repository root, prefix them with `skills/sci-plot/`.

## Maintain four auditable records

Keep these concepts distinct even when a simple task combines them in one
compact file. Read [audit-records.md](references/audit-records.md) when
implementing, revising, or delivering a production figure:

1. **Figure Contract** — scientific question, claims, analysis units,
   statistical meanings, constraints, and unresolved risks.
2. **Figure Plan** — evidence atoms, panel roles, visual encodings, reading
   order, and case influence.
3. **Render Manifest** — backend, entrypoint, inputs, environment, dimensions,
   outputs, and hashes for each panel and final assembly.
4. **QA Report** — stable check IDs, evidence, artifact measurements,
   unresolved warnings, and final readiness.

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

For **Create**, **Adapt**, or **Revise**, deliver:

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

For **Export**, deliver the converted or validated artifacts, measured output
properties, provenance of any conversion, and a QA report. Do not claim
scientific validation when only file-level checks were possible.
