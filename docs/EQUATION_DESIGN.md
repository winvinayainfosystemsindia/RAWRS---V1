# Equation / STEM Remediation — Design

**Status:** Phase A (Mathpix route) **implemented 2026-10-01, uncommitted** — see §8 for what differs from this text and what real data showed. Phase B (PDF-only) is not built.

## 0. Facts this design rests on (verified)

| # | Fact | Evidence |
|---|---|---|
| F1 | **Display equations are silently lost on the Mathpix path.** `_parse_env` handles figure/table/tabular/abstract only and returns `None` for `equation`, `align`, `gather` (starred or not) | `src/mathpix/mmd_parser.py:549-582`; parser probe: `F=ma` in `equation*` and both `align*` rows absent from the P2Document |
| F2 | `$$…$$` and `\[…\]` become three PARAGRAPH blocks (`$$`, raw LaTeX, `$$`) | same probe |
| F3 | Inline `\(…\)` is untouched; `$…$` is rewritten only for note markers and `$p \leq 0.001$`-style statistics — everything else reaches the DOCX as raw LaTeX | `src/mathpix/math_transformer.py:88-113` |
| F4 | Nothing creates Word equations; `DR-EQ` counts `m:oMath` so it always reports "no equations" | `src/validation/checklist_audit.py:529-534`; no `oMath` in `src/docx` |
| F5 | PDF-native path: formulas are PyMuPDF text; Docling runs only on OCR pages, with OCR only (no formula model) | `src/ocr/docling_config.py:44-49` |
| F6 | `SemanticObject` already names `Equation` as a planned subclass | `src/models/semantic_object.py:8` |
| F7 | The Mathpix package `.docx` already contains OMML (Bruner 9, Brinkman 21) but also wraps non-maths: years `(1970,1972)`, `$400` | `samples/mathpix/**/*.docx` |
| F8 | Company material is STEM textbooks: checklist heading example "UNIT 6 - RAY OPTICS" | `docs/Checklist for Document Remediation1.docx` |

## 1. Company rules (verbatim)

| Source | Rule |
|---|---|
| Eq 1 | remove extra spaces in the equation |
| Eq 2 | separate the equation if multiple equation inside the equation |
| Eq 3 | use sin, tan, cos, sin-1 etc from the equation tool. Do not type manually. |
| Eq 4 | keep the equation number outside the equation |
| Eq 5 | Any text connecting the equation should not be in the equation box |
| Eq 6 | All equation should look exact same as pdf like superscripts and subscript |
| Eq 7 | Simple equations should be outside the equation box |
| Final formatting | Equation numbering should be right aligned, bookmarking and cross reference |
| xlsx (STEM) | All equations are created using MathType or Word Equation Editor (not as images) · Add alt text or descriptions for complex equations · Mark equation objects inline with surrounding text when appropriate · Ensure chemical formulas/notations are properly tagged and accessible · Ensure STEM data tables use accessible Math and scientific notation |

## 2. Decisions

| Area | Decision | Reason | Rejected |
|---|---|---|---|
| **Input route** | **Phase A: Mathpix route only** (MMD LaTeX). **Phase B, owner's call:** PDF-only via Docling's formula model `docling-project/CodeFormulaV2` (0.3B, CDLA-Permissive-2.0, reachable through installed docling 2.87 `do_formula_enrichment`) | Mathpix already emits LaTeX, so Phase A needs no new model. CodeFormulaV2 needs no new package | A new formula-OCR package (not evaluated). Phase B cost is unmeasured and Docling currently runs only on OCR pages (F5) |
| **Data model** | New `Equation(SemanticObject)` in `src/models/equation.py`; `Document.equations`. Fields: `id` (`equation-line-{source_line}-{k}`, same scheme as `paragraph-line-…`, `paragraph.py:110`), `page_number`, `display: bool`, `latex_source` (immutable), `latex` (reviewable), `number: Optional[str]`, `label: Optional[str]`, `status` CONVERTED/FLAGGED/PLAIN, `flag_reasons`, `description: Optional[str]`. Inline: `paragraph_id` + `anchor_offset`/`anchor_length` into `Paragraph.text`, which holds a readable Unicode rendering of the span | Mirrors how notes anchor into prose (`note_references.py:69`, `Footnote.anchor_offset`); keeps `Paragraph.text` free of sentinels | Sentinel tokens in paragraph text (leak into every consumer); storing OMML in the model (a projection must not own semantics) |
| **Display node** | `ContentKind.EQUATION` for display equations; inline ones render inside their paragraph | Same dispatch as TABLE/IMAGE (`content_stream.py:39-62`) | A paragraph subtype |
| **Correction rail** | `EquationVerifier` registered with `engine.register` like callouts; editable fields `latex`, `display`, `number`, `description`, status. Revert restores `latex_source` | ADR-016: every reviewer change is a reversible `CorrectionRecord` | Direct mutation from routes |
| **Converter** | LaTeX → OMML with **pandoc/texmath**, invoked as a subprocess (shipped via `pypandoc-binary`, MIT wrapper; pandoc itself GPL-2), then RAWRS post-processing (next table). Conversion happens at DOCX projection time | Probe: fractions, roots, sub/sup, matrices correct; fails **loudly** on unknown macros (`\ce` warning) | `latex2mathml` (MIT, already installed via docling-core) + `mathml2omml` (0.0.2, 2019): probe showed **silent** wrong output — `aligned` rows collapsed with `&` as an identifier, `\ce` emitted as an identifier. Mathpix package OMML as primary source: wraps non-maths (F7); used only as a verifier signal |
| **Markdown** | Emit `$latex$` / `$$latex$$` | Markdown is a projection | Unicode approximation |

### Post-processing (each mapped to a rule)

| Rule | Action |
|---|---|
| Eq 1 | Drop explicit spacing macros (`\,` `\;` `\!` `\quad`) except one space before a unit (checklist "Before the kg or units leave the space") |
| Eq 2 | `align`/`gather`/`aligned` rows → one equation per row, never `m:eqArr` |
| Eq 3 | `\sin \cos \tan \cot \sec \csc \log \ln \exp \lim` (and `^{-1}` forms) → `m:func`/`m:fName`. Pandoc emits plain upright runs (probe: 0 `m:func`) |
| Eq 4 + final | `\tag`/auto-number → text after the equation on a right-aligned tab stop; bookmark `_Eq{n}`; `\ref`/`\eqref` → `REF` field to that bookmark |
| Eq 5 | Leading/trailing `\text{…}` moved out of the box into the paragraph; `\text` in the middle → FLAG |
| Eq 6 | Guaranteed by the round-trip check below, not by eye |
| Eq 7 | "Simple" (digits, single letters, `+ − = × ÷ %`, no fraction/root/script/matrix) and non-maths (years, currency, citations — F7) → plain text via `_LATEX_OPS` (`math_transformer.py:34`), status PLAIN |

### Confident vs flag for human

| CONVERTED only if **all** hold | Otherwise FLAGGED |
|---|---|
| Every command is on the allowlist: `\frac \dfrac \sqrt \sum \prod \int \oint \lim`, `^ _`, Greek, `\pm \mp \times \div \cdot \leq \geq \neq \approx \equiv \propto \infty \partial \nabla \to \rightarrow \Rightarrow \leftrightarrow`, `\left \right`, `pmatrix bmatrix vmatrix matrix cases`, `\mathrm \mathbf \text \hat \bar \vec \dot \overline`, the Eq 3 functions | Any other macro; pandoc stderr non-empty; round-trip mismatch; `\color`, `\overset`/`\underset`, `array` with alignment specs, diagrams |
| Round trip: OMML → pandoc → LaTeX, normalised (whitespace, braces, `\left`/`\right`) equals the normalised input | A FLAGGED equation still gets pandoc's OMML if one was produced; if none, a Unicode linear text fallback. Both go to the review queue and `DR-EQ` = manual |

## 3. Chemistry

| Case | Decision |
|---|---|
| `\ce{…}` (mhchem; Mathpix MMD documents SMILES but not mhchem, arXiv chemistry uses `\ce` heavily) | RAWRS translator for a subset → LaTeX, then the normal converter: formulas with counts, charges `^{2+}`, coefficients, states `(aq)(s)(l)(g)`, arrows `-> <- <=> <->`. Element symbols upright. Anything else → FLAG |
| `\mathrm{H_2SO_4}` already in LaTeX | Normal converter |
| SMILES / structure diagrams | Not an equation — image path + existing alt text |
| Plain-text formulas in prose (`H2O` typed with subscript runs) | Not detected in Phase A. Open question 3 |

## 4. Screen-reader accessibility

| Item | Decision |
|---|---|
| Structure | Native OMML only, never an image (xlsx rule). Word exposes Office Math to NVDA/JAWS (MathCAT) and Narrator, which read it part by part |
| Inline vs display | Inline equations stay in their paragraph (xlsx "inline … when appropriate"); display equations get their own paragraph |
| Numbers and connecting words | Outside the box as ordinary text (Eq 4, Eq 5), so they are read as prose |
| Complex / FLAGGED | OMML has no alt-text attribute. `Equation.description` (reviewer-written, never AI-invented) renders as a normal paragraph directly after the equation. Open question 2 |

## 5. Test plan

| Check (runs without Word) | Pass criterion | Ground truth |
|---|---|---|
| Parser, no content loss (F1–F3) | Every `$…$`, `\(…\)`, `$$…$$`, `\[…\]`, `equation`, `align`, `gather` in an MMD fixture yields exactly one Equation per equation/row; zero raw-LaTeX paragraphs | Synthetic MMD fixtures using the delimiters in Mathpix's syntax reference |
| OMML well-formed | Output DOCX opens in python-docx; every `m:` element name on an allowlist | Generated DOCX |
| Round trip | 100% of CONVERTED equations pass; a deliberately broken input is FLAGGED | arXiv `.tex` sources below |
| Eq 2, 3, 4, 5, 7 | Counts of `m:oMath` per row, `m:func` for every function, number outside `m:oMath` + bookmark + `REF`, no `\text` edge in the box, simple spans have no `m:oMath` | Fixtures + arXiv |
| Chemistry subset | Subset converts; outside it FLAGs, never silently | arXiv 2609.33784 (519 `\ce` uses) |
| Correction rail | Edit → apply → revert restores `latex_source`; projection updates | Unit test |
| Projection correctness | Add Equation to the ADR-020 PI checks (no lost or invented equation objects) | `src/benchmark/projection.py` |
| `DR-EQ` | Reports converted / flagged / plain counts; manual when any are flagged | Generated DOCX |

**Human, in Word:** 10 equations per sample (inline, display, numbered, matrix, chemistry): look vs PDF (Eq 6), NVDA + MathCAT reading, Word Accessibility Checker.

**Samples** (git-ignored, `data/cache/equation_samples/`, see `SOURCES.txt`; never commit):

| Source | Licence | Use |
|---|---|---|
| arXiv 2208.04306 *Unfolded Dynamics Approach and QFT* (PDF + `.tex`) | CC BY 4.0 | Physics ground truth |
| arXiv 2609.33784 *On mechanistically accessible copolymer sequences* | CC BY 4.0 | Chemistry `\ce` ground truth |
| arXiv 2609.36306 *A note on Rainwater's Theorem* | CC BY 4.0 | Maths `align` ground truth |
| OpenStax College Physics 2e, Chemistry 2e, Calculus Vol 1 (PDF URLs in `SOURCES.txt`, not downloaded) | **CC BY-NC-SA 4.0** (OpenStax CMS API, 2026-10-01 — not CC BY) | Textbook layout, eyeball only, internal non-commercial testing |

## 6. Risks and what was not verified

| Item | Status |
|---|---|
| Real Mathpix MMD for a STEM textbook | **Not seen** — no Mathpix run on these samples; fixtures are synthetic |
| CodeFormulaV2 RAM/CPU/quality | Not measured (Phase B only) |
| Pandoc Linux binary size in Docker; GPL-2 obligations if the image is distributed | Not checked — company question |
| Screen-reader behaviour | From Microsoft/NV Access docs; not tested on this machine |
| `mathml2omml-as` 0.1.0 (2025 fork) | Not tested |
| Word rendering of post-processed OMML (`m:func`, tab-stop numbers) | Needs a human in Word |

## 7. Open questions (owner / company)

1. Is Phase B (PDF-only STEM, CodeFormulaV2) wanted, and on what hardware?
2. For complex equations: is a reviewer-written description paragraph acceptable as "alt text or description"?
3. Should plain-text chemical formulas in prose be detected and converted?
4. Equation font: Word equations use Cambria Math; the checklist says Times New Roman for all styles. Which wins?
5. Equation numbering format and cross-reference text (e.g. "(6.1)" vs "Equation 6.1").
6. May pandoc (GPL-2) ship inside the deployment image?
7. Can the company supply one real remediated STEM chapter (the "Ray Optics" book) as ground truth?

## 8. Implementation notes (Phase A, 2026-10-01)

| Where | Finding | Evidence |
|---|---|---|
| Design gap | A numbered environment with no `\tag` is **FLAGGED** ("number unknown"), never auto-numbered | `src/equations/build.py`; 156 of 159 arXiv physics rows hit it (LaTeX sources auto-number, a Mathpix export carries `\tag`) |
| Design addition | `\rightleftharpoons`, `\leftarrow` added to the allowlist — §3's arrows could not otherwise pass | `src/equations/latex.py` |
| Converter | Uses `pandoc -f latex`, not markdown: the markdown reader turned `\\` row breaks in matrices into spaces | probe 2026-10-01; `tests/test_equation_omml.py::test_matrix_keeps_both_rows` |
| Revert | Reverting an edit restores the **previous** LaTeX (equal to the source for a first edit); `latex_source` itself is never written | `src/verification/equations.py` |
| **Bug found and fixed** | The note-marker detector read any `^{N}` — every `x^{2}` — as footnote N, so STEM prose proved a numbered list a note apparatus. Exponents inside a maths span are no longer markers | `src/mathpix/mmd_parser.py::_is_exponent_in_maths`; `tests/test_equation_parser.py::TestMathSuperscriptsAreNotNoteMarkers` |
| Limit | Inline maths is converted in **paragraphs**. Headings, list items and table cells keep raw `$…$` | `src/equations/build.py` only rewrites PARAGRAPH blocks |
| Limit | `\ce` translator covers 68 of 87 distinct bodies in the chemistry paper; the rest are flagged (`P A`-style species labels translate as plain roman letters) | `tests/test_equation_groundtruth.py` |
| Limit | Pandoc groups a sum's operand in braces (`{\sum … }`), so two physics equations fail the round trip and stay flagged | explored, not normalised |
| Decision for owner | **The allowlist is narrow.** Real arXiv physics: 82 of 159 rows CONVERTED; 71 more are flagged *only* for a command outside the list (`\square 37, \hbar 28, \bigl/\bigr 18, \langle/\rangle 12, \mathcal 5, \circ 5, \underline 2`). Maths paper: 10 of 17 (`\in 7, \limsup 3, \sup 2, \dots 2, \setminus 2, \cap 2, \bigcup 2, \bigcap 2, \inf 1`). The round trip already catches a wrong conversion, so widening is a one-line data change in `_ALLOWED_COMMANDS` — **not made**, since §2 fixes the list | `tests/test_equation_groundtruth.py`, scratch probes |

**Measured on real equations** (arXiv 2208.04306 physics + 2609.36306 maths, unnumbered display rows, `tests/test_equation_groundtruth.py`): 82 confident rows, **81 convert and round-trip (98.8 %)**; every verified equation keeps all letters and digits of its `.tex`; the round trip rejects every deliberately changed equation; 68 of 68 translatable `\ce` bodies convert and verify.

**Also changed after real-data runs:** a lone species such as `\ce{A}` (or any `\mathrm{X}` of plain characters) is now PLAIN text, not a box (Eq 7 consistency between ingest and the audit); the round-trip normaliser treats `\hat`/`\widehat`, redundant accent braces, empty scripts, `\mathrm{\hat{J}}` and `U'_{x}`/`U_{x}'` as equal. The enum-pinning test `tests/test_paragraph_content_nodes.py` gained `"equation"` (appended; no value moved) — the only existing test expectation edited.

**Regression run 2026-10-01:** existing DOCX/Markdown/Mathpix/scan/checklist tests 306 passed; validation/verification/stream/paragraph tests 429 passed, 5 skipped, plus the one test above; 240 equation-related tests passed. The full suite and `tests/test_pipeline.py` (5 known CI failures) were not re-run.

**Files to open in Word** (git-ignored, `data/cache/equation_samples/out/`): `1_synthetic_all_kinds.docx`, `2_arxiv_physics_2208.04306.docx` (compare with `2208.04306.pdf`), `3_arxiv_chemistry_2609.33784.docx` (regenerate first — built before the lone-species fix).

**Not verified:** rendering in Word, NVDA/MathCAT reading, Word's Accessibility Checker, the Docker image with `pypandoc-binary`, and any real Mathpix export of a STEM document.

## Implementation order (Phase A)

1. Parser: equation blocks and delimiters → P2 equation blocks (fixes F1–F3). 2. `Equation` model + ingestor + ContentKind. 3. Converter + post-processing + round trip. 4. DOCX/Markdown projections. 5. `EquationVerifier` + review queue. 6. `DR-EQ` + PI checks. 7. Docs.
