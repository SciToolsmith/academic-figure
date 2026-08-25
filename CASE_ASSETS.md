# Case asset scope and provenance

This repository separates searchable atlas material from executable open templates.

## Asset classes

### `assets/case-atlas/`

- 436 project-maintained thumbnails associated with 180 searchable figure cases.
- Used for semantic retrieval and visual inspection after a case is selected.
- Atlas status does **not** mean that the corresponding private case source code or research data are included.
- The repository owner has approved these project-controlled renderings for inclusion and redistribution in this release.

### `assets/open-templates/`

- 46 rendered previews: Python and R outputs for 23 open templates.
- Generated from the template-local demonstration inputs.
- Demonstration inputs are neutral and fixed where simulation is used; they are not scientific evidence.

## What is not distributed

- private implementations for the other 157 atlas-only cases;
- publisher PDF pages or journal website screenshots;
- raw research datasets, patient records, credentials, or local filesystem paths;
- statistical claims copied from a paper or inferred from a thumbnail.

Text embedded inside a rendered preview is part of that visual reference. It must not be extracted, reanalysed, or presented as user data or as a result generated for a new study.

## License boundary

Project-authored code, documentation, demonstration data, and generated open-template previews are distributed under the repository's Apache-2.0 license. The case-atlas thumbnails are project-controlled visual index assets approved by the repository owner for this release; they remain subject to any asset-specific notice added in the future.

The atlas is an aid to scientific-figure selection, not permission to copy a publisher's layout, paper-specific labels, numerical values, thresholds, or conclusions into new work.

## Independence

`academic-figure` is not affiliated with or endorsed by Nature Portfolio, Springer Nature, OpenAI, or any journal, publisher, paper author, or data provider. Names of journals and publication styles are used only for descriptive, critical, and retrieval purposes.

The machine-readable asset mapping is maintained in:

- `skills/academic-figure/references/cases/case-index.jsonl`
- `skills/academic-figure/references/cases/open-template-roadmap.json`
