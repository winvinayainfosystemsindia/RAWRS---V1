# Front Matter Generalization — Audit & Design Review

**Status: AUDIT/DESIGN ONLY. No code changed.** Per explicit instruction, this is a benchmark audit and implementation design, gated for sign-off before any code is written — the same "audit before implementation" discipline as `bug_001`/`bug_002`/`feature_005`/`feature_007`'s own design-only phases.

Ticket: `feature_008_front_matter_generalization`. (Not `bug_008` — `PROJECT_SAVE_STATE.md` explicitly records that `bug_008` "does not exist" and was never created; this is an architecture-level generalization of `feature_006_front_matter_extraction`, not a single-symptom bug, matching the `feature_NNN` naming convention.)

All evidence below was gathered by actually running `parse_pdf` → `extract_text` → `detect_structure` → `extract_front_matter` against the real PDFs in `samples/benchmark/pdfs/` and reading `Document.blocks`' real `font_size`/`order`/`text` values directly — not inferred from code inspection alone.

---

## 1. Benchmark-Wide Classification Table

| PDF | Has Front Matter? | Current Result | Failure Reason | Candidate Signals (measured) |
|---|---|---|---|---|
| `1. Nature of Enquiry.pdf` | **No** — page 1 is mid-chapter body text (a textbook excerpt with no title page in this PDF), confirmed by direct inspection: first real line is `"This large chapter explores..."` at body size. | Empty (correct) | N/A — not a defect. | body=9.5pt; first page-1 line is already body-sized; no line on page 1 reaches the 1.3x title threshold (12.35pt). |
| `1.Aims of Education...pdf` | **Yes.** | **Empty (defect — named in task brief)** | No `_ZONE_BOUNDARY_KEYWORDS` match (`abstract`/`keywords`/`introduction`/`summary`) anywhere in the first 20 lines of page 1 — this document has no Abstract section, it goes straight from title/author into an epigraph and then body prose. `_find_zone_boundary()` returns `None` unconditionally, so `_build_front_matter()` bails before title/author detection ever runs. | title="AIMS OF EDUCATION: DO TEACHERS NEED"/"TO BOTHER ABOUT THEM?" at **16.0pt** (×2 lines); author="Rohit Dhankar" at **14.0pt**; body=**12.0pt**; title_threshold(1.3x)=15.6. Title and author sit cleanly on either side of the threshold — the only problem is the zone is never opened at all. |
| `2. Social research strategies Bryman.pdf` | **Unknown — architecturally unmeasurable.** | Empty | `detect_structure()` independently re-opens the PDF via PyMuPDF and reads `page.get_text("dict")` (`structure_detector.py:132`) — it does **not** consume OCR output at all. This PDF has **zero blocks across all 26 pages** (confirmed: `document.blocks` is empty, `_dominant_font_size()` returns `None`), meaning PyMuPDF found no embedded text layer whatsoever — a genuinely scanned/image-only PDF. | None available — there is no font-size signal to read until/unless this PDF goes through Docling/Surya OCR, and even then, OCR output carries no font-size metadata for `front_matter_extractor.py` to use (it depends entirely on `TextBlock.font_size`). **Out of scope for any font-size-based fix.** |
| `2.FolkPedagogy_Bruner_PsychDimensions_New.pdf` | **Yes.** | **Empty (defect — named in task brief, "author not captured")** | Same root cause as Aims: no boundary keyword on page 1 (this is a book half-title/series page — title, author, publisher, city, country, then the page ends; no Abstract section exists because this isn't a journal article). A second, independent bug would also block correct extraction even if the boundary were found: the title-run loop's stopping condition is `while font_size >= threshold`, so it doesn't stop at "Jerome Bruner" (24.0pt, still ≥ the 16.9pt threshold) — it would **merge the author into the title**. | title="THE CULTURE OF EDUCATION" at **29.0pt**; author="Jerome Bruner" at **24.0pt**; "HARVARD UNIVERSITY PRESS" at **14.0pt**; "Cambridge, Massachusetts" at **11.0pt**; "London, England" at **10.0pt**; body=**13.0pt** (doc-wide dominant); title_threshold=16.9. Both title and author exceed the threshold — the threshold alone cannot separate them. |
| `3. sockett_profession.pdf` | **No (reliably) — decorative cover page, heavily OCR/font-corrupted.** A real chapter heading ("The Moral Core of Professionalism in Teaching") exists further down the page, but it is surrounded by large single-glyph noise (e.g. a lone `"e"` at **29.0pt**, larger than any real title in the corpus). | Empty (correct, currently by accident — no boundary keyword present) | N/A today. **Flagged as a regression risk for any generalization that loosens the boundary/title gates** — see §3. | body=8.0pt; lone glyph `"e"` at 29.0pt sits at index 0, exceeding the 1.3x threshold (10.4) by a wide margin. Any font-size-only title gate would treat it as a candidate title. |
| `4. O Leary_Developing the research questions.pdf` | **Unknown — architecturally unmeasurable.** | Empty | Same as Bryman: 0 blocks across all 13 pages, `_dominant_font_size()` returns `None`. Scanned/image-only PDF. | None available. Out of scope. |
| `4.Teaching as a professional discipline-Chapter 1.pdf` | **Unknown — architecturally unmeasurable.** | Empty | Same as Bryman: 0 blocks on page 1 specifically (despite 745 blocks document-wide — page 1 itself has no extractable text layer, though later pages do). | None available for page 1. Out of scope for this page. |
| `5.Teachingas a profession_Calderhead.pdf` | **Yes (not named in task brief, found during this audit).** Page 1 is structurally identical to Aims: chapter-label + title + author, then body prose, no Abstract section. | Empty (same root cause as Aims/Bruner) | No boundary keyword; additionally, the existing kicker-skip condition (`font_size < title_threshold`) does not fire on `"Chapter 9"` (14.0pt), because 14.0 **exceeds** this document's 1.3x threshold (13.0) — so even if a boundary were found, `"Chapter 9"` would itself start (and corrupt) the title run. | "Chapter 9" at **14.0pt**; title="Teaching as a professional activity" at **18.0pt**; author="James Calderhead" at **14.0pt** (same size as the chapter label, by coincidence); body=**10.0pt**; threshold=13.0. |
| `6. Fullan&Hargreaves_teacherasaperson.pdf` | **Yes (not named in task brief, found during this audit).** Same structure as Calderhead. | Empty (same root cause) | Identical to Calderhead. | "Chapter 7" at **14.0pt**; title="The teacher as a person" at **18.0pt**; author="Michael Fullan and Andy Hargreaves" at **14.0pt**; body=**10.0pt**; threshold=13.0. |
| `7.brinkman-...pdf` | **Yes.** | **Correct (`feature_006`'s calibration target).** | N/A. | kicker="Article" at 10.0pt; title (×3 lines) at **17.9pt**; author="Suzana Brinkmann" at **12.0pt**; affiliation="Institute of Education, London, UK" at **9.0pt**; body=**10.0pt**; boundary keyword="Abstract". |

**Summary: 5 of 10 PDFs have real, measurable front matter on page 1** (Brinkman ✓ working, Aims ✗, Bruner ✗, Calderhead ✗ unflagged, Fullan&Hargreaves ✗ unflagged). **3 of 10 are architecturally unmeasurable** (Bryman, O'Leary, Teaching-as-Discipline — no PyMuPDF text layer at all on the relevant page(s), regardless of any algorithm change). **2 of 10 correctly have no front matter** (Nature of Enquiry, sockett).

---

## 2. Root Cause Analysis

Two independent root causes, both in `front_matter_extractor.py`:

### 2.1 Zone-boundary detection only recognizes one structural pattern

`_find_zone_boundary()` requires a literal `abstract`/`keywords`/`introduction`/`summary` line within the first 20 lines of page 1. This models **journal-article** front matter (title → author → affiliation → Abstract), which is exactly Brinkman's shape. It does not model **book/chapter-excerpt** front matter (title → author → [publisher/series info] → body prose, with no Abstract section at all) — Aims, Bruner, Calderhead, and Fullan&Hargreaves are all this second shape, just with varying amounts of material between author and body.

### 2.2 Title/author tier separation uses one fixed global threshold as both a floor and a ceiling

`_TITLE_MIN_SIZE_RATIO` (1.3× body) is used three ways at once: (a) the minimum size to even qualify as "title-tier" at all, (b) the title run's **stopping condition** (`while font_size >= threshold`), and (c) the author run's **upper bound** (`while body < font_size < threshold`). This conflates "is masthead-tier" with "is the *same* masthead tier as the previous line." It works for Brinkman only because Brinkman's author (12.0pt) happens to sit just below the 1.3×-body line (13.0pt) while its title (17.9pt) sits well above it — a coincidence of this one document's specific sizes, not a structural guarantee. It silently breaks the instant a document's author line is *also* well above the threshold (Bruner: author 24.0pt vs. threshold 16.9) or a chapter-label kicker is *also* above the threshold (Calderhead/Fullan&Hargreaves: "Chapter N" at 14.0pt vs. threshold 13.0).

---

## 3. Proposed Implementation Plan (smallest deterministic change)

Empirically validated via a standalone prototype run against all 10 real benchmark PDFs (not just reasoned about on paper — see §4 for exact prototype output). Three small, independent changes, all inside `front_matter_extractor.py`, no model/architecture changes:

**3.1 — Boundary detection: keep the keyword check first (unchanged), add a font-size fallback.** If no keyword boundary is found, fall back to: the first line (after the kicker-skip) whose font size is within ~0.5pt of the document's body font size; if no such line exists within the masthead window either (e.g. Bruner — the whole page never drops back to body size), the boundary defaults to the end of the scanned window. This is strictly additive — the keyword path is untouched, so Brinkman's extraction is byte-for-byte unchanged (confirmed in §4).

**3.2 — Kicker-skip: compare against the next line's size, not a global threshold.** Change the kicker condition from "font_size < global title_threshold" to "font_size < the immediately following line's font_size" (still gated by the existing length cap). This is what lets `"Chapter 9"`/`"Chapter 7"` (14.0pt, which exceeds the 1.3× threshold) still be correctly recognized as a kicker rather than corrupting the title run, while leaving Brinkman's "Article" kicker-skip behavior unchanged.

**3.3 — Title and author runs: stop at the first font-size change, not at the threshold.** Once the first title-tier line is found (still gated by the unchanged 1.3×-body minimum, preserving the existing "fail closed if nothing exceeds 1.3×" safety net for non-title-page PDFs), the title run is the contiguous run of lines at *that same* font size (±0.3pt), not "every line ≥ threshold." The author run is then the contiguous run of lines at *its own* single font size, bounded above by the title's actual detected size (not the global threshold) and below by body size. This correctly separates Bruner's title(29.0)/author(24.0)/publisher(14.0) into three distinct tiers instead of merging the first two, and separates Calderhead's kicker(14.0)/title(18.0)/author(14.0) correctly despite the kicker and author sharing a coincidental size.

**3.4 — Defensive guard: require the title text to contain at least one space.** Suppresses single-glyph/no-space spurious titles (the sockett `"e"` case) without needing any new corpus-specific exclusion list. This is the one new safety net needed *because* §3.1's more permissive boundary fallback would otherwise let sockett's giant lone glyph pass the (unchanged) minimum-size gate.

None of this touches `Document`, `Heading`, or `FrontMatter`'s model shape, and none of it introduces AI/ML — it's a refinement of the existing deterministic, rule-based tier-detection logic only.

---

## 4. Empirical Validation (prototype, run against real PDFs, no source file modified)

A standalone prototype implementing §3.1-3.4 was run against all 10 benchmark PDFs' real, measured `Document.blocks`:

| PDF | Prototype Result | vs. Current |
|---|---|---|
| Nature of Enquiry | No title found (boundary fallback trivially resolves to a single page-number line, which still fails the unchanged 1.3× minimum-size gate) | **Unchanged (still correctly empty)** |
| Aims of Education | title="AIMS OF EDUCATION: DO TEACHERS NEED TO BOTHER ABOUT THEM?", authors=["Rohit Dhankar"], affiliations=["“There is nothing more practical than theory.” - Boltzmann"] | **Fixed** (title+author now correctly captured; the epigraph quote falls into "affiliations" as a known, accepted imprecision — see §5.3) |
| Bryman | No blocks at all — prototype cannot run | **Unchanged (still correctly empty, architecturally)** |
| FolkPedagogy_Bruner | title="THE CULTURE OF EDUCATION", authors=["Jerome Bruner"], affiliations=["HARVARD UNIVERSITY PRESS"] | **Fixed** (author no longer merged into title; publisher line lands in "affiliations" — imprecise label, but isolated correctly) |
| sockett_profession | Title rejected by the §3.4 space guard (`text='e'`) | **Unchanged (still correctly empty — confirms the new guard prevents a new false positive)** |
| O'Leary | No blocks at all — prototype cannot run | **Unchanged** |
| Teaching-as-Discipline | No blocks on page 1 — prototype cannot run | **Unchanged** |
| Calderhead | title="Teaching as a professional activity", authors=["James Calderhead"] | **New correct capture (not requested, but consistent — see §5.4 for the scope question this raises)** |
| Fullan&Hargreaves | title="The teacher as a person", authors=["Michael Fullan and Andy Hargreaves"] | **New correct capture (same scope question)** |
| Brinkman | title, authors, affiliations all byte-for-byte identical to current production output (keyword boundary path, unchanged) | **Unchanged — confirmed, not assumed** |

---

## 5. Risk Analysis

**5.1 — sockett's lone giant glyph (`"e"` at 29.0pt).** The more permissive boundary fallback (§3.1) would, on its own, let this single-character line pass the unchanged title-size gate and become a spurious 1-character "title." Mitigated by §3.4's space-guard, empirically confirmed to suppress it (§4). This is the one genuinely new failure mode this generalization introduces, and the one place a future regression is most likely to surface if the guard is ever loosened.

**5.2 — The 3 architecturally-unmeasurable PDFs (Bryman, O'Leary, Teaching-as-Discipline).** Zero risk either way — `detect_structure()` reads PyMuPDF's native text dict directly (`structure_detector.py:132`, `page.get_text("dict")`), never consumes OCR output, so these PDFs produce zero blocks regardless of any change here. Not fixable within this module's architecture; would require a structurally separate signal (e.g. OCR-derived font-size estimation), explicitly out of this plan's scope ("does not redesign Document or Heading models").

**5.3 — Aims' epigraph quote becomes a mislabeled "affiliation."** The Boltzmann quote (55.5pt, even larger than the title) sits between author and the real body text, and isn't recognized as its own semantic category — it falls into the catch-all "affiliation" bucket by the same logic that already governs Brinkman's affiliation extraction (whatever's left in the bounded zone). This is a labeling imprecision, not a crash or a content-loss bug, and is consistent with "smallest deterministic improvement" — a more precise fix (e.g., a fourth "epigraph" category, or an affiliation-content sanity filter) would be a separate, larger change.

**5.4 — Calderhead and Fullan&Hargreaves are new captures beyond the named scope.** The task brief named only Aims and Bruner as targets; this audit's evidence shows the same fix mechanically also activates correct front-matter extraction for two more benchmark PDFs that happen to share the identical book/chapter-excerpt shape. This is presented as an open decision, not a unilateral scope expansion — see §6.

**5.5 — Calibration is now against 5 real positive examples (not 1).** A meaningful improvement over `feature_006`'s single-document calibration (Brinkman only), but still a small sample. The 0.5pt boundary tolerance and 0.3pt tier-equality tolerance were chosen to cleanly separate every real tier in this corpus with margin (no two distinct real tiers in any of the 5 working PDFs are within 1pt of each other), but, per this project's established practice with `feature_007`'s cross-block window, should be revisited if a future document's front matter misbehaves.

---

## 6. Open Decisions Needed Before Implementation

1. **Should Calderhead and Fullan&Hargreaves' front matter be captured at all?** They are excerpted book chapters, not standalone articles — front matter for them means "this chapter's title and author," which is arguably correct and desirable (consistent with how Aims, also a chapter excerpt, is being treated), but was not explicitly asked for. Needs a decision: capture it (no special-casing needed, it falls out of the same fix for free) vs. explicitly excluding excerpt-style documents (would need a new, separate signal to distinguish "chapter excerpt" from "full article," adding complexity not otherwise required).
2. **Is the Aims epigraph mislabeled as "affiliation" acceptable as shipped, or does it need a guard before release?** A cheap option if not acceptable: drop any "affiliation" line whose font size exceeds the title's own size (the epigraph is *larger* than the title, which no real affiliation line in this corpus ever is) — not yet validated against the corpus, would need a quick re-check before adopting.
3. **Confirm the 0.5pt/0.3pt tolerances** — chosen from real corpus margins, not arbitrary, but should be sanity-checked against a wider corpus if one becomes available before being treated as permanently calibrated.

---

## 7. Focused Affiliation-Validation Audit (2026-06-25, pre-implementation gate)

Per explicit instruction, before any code is written: re-ran the exact §3 prototype against all 10 benchmark PDFs and classified every non-empty `affiliations` value produced, to determine whether the design introduces semantic corruption (non-affiliation text labeled as an institutional affiliation).

### 7.1 Full table

| PDF | Title | Authors | Affiliations | Classification | Correct? |
|---|---|---|---|---|---|
| `1. Nature of Enquiry.pdf` | *(none — title gate fails)* | [] | [] | N/A | Yes (correctly empty) |
| `1.Aims of Education...pdf` | "AIMS OF EDUCATION: DO TEACHERS NEED TO BOTHER ABOUT THEM?" | ["Rohit Dhankar"] | ["“There is nothing more practical than theory.” - Boltzmann"] | **Epigraph/quote** | **No** |
| `2. Social research strategies Bryman.pdf` | *(no blocks)* | [] | [] | N/A | Yes (architecturally empty) |
| `2.FolkPedagogy_Bruner_PsychDimensions_New.pdf` | "THE CULTURE OF EDUCATION" | ["Jerome Bruner"] | ["HARVARD UNIVERSITY PRESS"] | **Publisher information** | **No** |
| `3. sockett_profession.pdf` | *(none — space guard rejects "e")* | [] | [] | N/A | Yes (correctly empty) |
| `4. O Leary_Developing the research questions.pdf` | *(no blocks)* | [] | [] | N/A | Yes (architecturally empty) |
| `4.Teaching as a professional discipline-Chapter 1.pdf` | *(no blocks on page 1)* | [] | [] | N/A | Yes (architecturally empty) |
| `5.Teachingas a profession_Calderhead.pdf` | "Teaching as a professional activity" | ["James Calderhead"] | [] | N/A | Yes (no affiliation claimed, none exists on this page) |
| `6. Fullan&Hargreaves_teacherasaperson.pdf` | "The teacher as a person" | ["Michael Fullan and Andy Hargreaves"] | [] | N/A | Yes (same as Calderhead) |
| `7.brinkman-...pdf` | "Learner-centred education reforms in India: The missing piece of teachers’ beliefs" | ["Suzana Brinkmann"] | ["Institute of Education, London, UK"] | **Genuine affiliation** | **Yes** |

No PDF in the corpus produces a "chapter metadata" or "running header/footer" misclassified affiliation — those two categories don't occur in this table at all; the only two non-genuine categories that actually appear are epigraph/quote (Aims) and publisher information (Bruner).

### 7.2 Answers

**A. Which PDFs gain correct front matter compared to the current implementation?**
Title+author are newly and correctly captured for `Aims`, `Bruner`, `Calderhead`, `Fullan&Hargreaves`. Of these, `Aims` and `Bruner`'s title/author fields are correct, but both also gain an **incorrect** affiliation value (see D).

**B. Which PDFs remain unchanged?**
`Brinkman` (byte-for-byte identical, keyword path untouched), `Nature of Enquiry`, `sockett_profession`, `Bryman`, `O'Leary`, `Teaching-as-Discipline` (all still correctly empty).

**C. Which PDFs become worse?**
None become worse in title/author — but `Aims` and `Bruner` go from "no affiliation field populated" (current: empty, since both currently fail the boundary check entirely) to "an affiliation field populated with wrong content." Going from absent to wrong is a regression in correctness, even though it's an improvement in title/author coverage for the same two documents.

**D. Are there any false-positive affiliations?**
**Yes, 2 of 2 non-empty affiliation values produced by documents not already in production are wrong:**
- `Aims`: `"There is nothing more practical than theory." - Boltzmann` — an epigraph, not an affiliation.
- `Bruner`: `"HARVARD UNIVERSITY PRESS"` — the publisher's imprint, not an institutional affiliation.
The only *correct* affiliation in the entire table (`Brinkman`) is the one already in production today, unaffected by this change.

**E. Are there any false-positive authors?**
**No.** Every author value produced (`Rohit Dhankar`, `Jerome Bruner`, `James Calderhead`, `Michael Fullan and Andy Hargreaves`, `Suzana Brinkmann`) is a real, correct author/byline for its document. The §3.3 equal-size-run fix (validated in §4) specifically prevents Bruner's "HARVARD UNIVERSITY PRESS" from being merged into the *author* list — it only fails to keep it out of *affiliations*.

**F. Are there any cases where a subtitle, epigraph, publisher imprint, journal metadata, chapter number, or running header is being misclassified?**
Yes, two, both already identified in D: Aims' **epigraph** and Bruner's **publisher imprint**. No subtitle, journal-metadata, chapter-number, or running-header misclassification occurs anywhere in the corpus — those categories are absent from the table entirely (chapter numbers like "Chapter 9"/"Chapter 7" are correctly consumed as kickers and discarded, not misclassified as affiliations; no running headers fall inside any front-matter zone in this corpus).

**G. Would you ship this implementation exactly as designed, or is an additional guard required?**
**One additional guard is required**, justified by the `Aims` document alone: a 55.5pt epigraph line would be written into `FrontMatter.affiliations` and rendered by `markdown_builder.py`/`docx_generator.py` as if it were an institutional affiliation — a clear, visible factual error in the generated output, worse than the current behavior of extracting nothing at all for this document.

### 7.3 Smallest deterministic guard, and the document that proves it

**Guard: reject any affiliation-tier line whose font size is ≥ the title run's own detected font size.**

Evidence: in `Aims`, the epigraph is 55.5pt against a title of 16.0pt (55.5 ≥ 16.0 → rejected). In every PDF in the corpus that has a *genuine* affiliation (`Brinkman`: affiliation 9.0pt vs. title 17.9pt) or no affiliation at all, this condition never fires — applying it changes no other document's output. This is the smallest possible single-condition deterministic check that removes the most severe (most visibly absurd) corruption case found in this corpus.

**This guard does not fix Bruner.** "HARVARD UNIVERSITY PRESS" (14.0pt) is *smaller* than its title (29.0pt) — the same condition that catches the Aims epigraph does not catch this case, because the corruption here isn't a size anomaly, it's a content-category anomaly (a publisher name, not an institution). No deterministic, size-based, or position-based signal in the measured data distinguishes "HARVARD UNIVERSITY PRESS" from "Institute of Education, London, UK" (both are short, single-line, immediately follow the author run, sit below the title's size) — the only distinguishing signal available is the literal text itself (e.g., a "publisher-name-like" keyword check), which is a new, untested heuristic with exactly one supporting example in this corpus. Per the instruction not to speculate or introduce new architecture, this is reported as an **honest, confirmed, residual gap** — not papered over with an invented rule — rather than folded into the one guard recommended for implementation.

### 7.4 Recommendation

**One additional guard required before implementation:** the title-size-ceiling guard on affiliation lines (§7.3), proven necessary by `Aims of Education`'s epigraph. Without it, this PDF would ship with a visibly wrong "affiliation" field, a regression from today's (empty, but not wrong) output.

The Bruner publisher-imprint misclassification (`HARVARD UNIVERSITY PRESS`) is **not** resolved by this guard and has no clean deterministic fix demonstrated by the evidence gathered so far. It should be carried forward as a named, open, accepted limitation (or a separate follow-up) rather than blocking this implementation on an unproven heuristic — it is a less severe error (a real publisher's name, plausible-looking, not absurd) than the epigraph case, and is the only remaining known imprecision once the guard above is added.

---

## 8. Bruner Publisher-Imprint: Deterministic-Signal Investigation (2026-06-25)

§7.3 reported no clean deterministic fix for the Bruner case "demonstrated by the evidence gathered so far." Per explicit follow-up instruction, gathered the missing evidence directly from both PDFs' raw PyMuPDF span data (font family, bold flag, exact bbox geometry) and a full document-wide text scan, rather than continuing to assume none exists.

### 8.1 Raw geometry, both documents, page 1

```
BRUNER page 1 (page width=612.0, centered-layout convention):
  y0=154.7  size=29.0  bold=True   font='Helvetica-Bold'  text='THE CULTURE OF EDUCATION'        <- title
  y0=317.5  size=24.0  bold=False  font='Helvetica'       text='Jerome Bruner'                    <- author
  y0=543.2  size=14.0  bold=True   font='Helvetica-Bold'  text='HARVARD UNIVERSITY PRESS'         <- false positive
  y0=565.5  size=11.0  bold=False  font='Helvetica'       text='Cambridge, Massachusetts'
  y0=580.3  size=10.0  bold=False  font='Helvetica'       text='London, England'

BRINKMAN page 1 (page width=481.9, left-aligned masthead convention):
  y0=95.3   size=17.9  bold=False  font='AdvP7D0F'  text='Learner-centred education'  (title, 3 lines)
  y0=165.0  size=12.0  bold=False  font='AdvP7D0F'  text='Suzana Brinkmann'                       <- author
  y0=179.0  size=9.0   bold=False  font='AdvP7D09'  text='Institute of Education, London, UK'     <- genuine affiliation
  y0=218.3  size=10.0  bold=False  font='AdvP7D0F'  text='Abstract'
```

### 8.2 Signal-by-signal findings

| Signal | Bruner ("HARVARD UNIVERSITY PRESS") | Brinkman ("Institute of Education, London, UK") | Separates them? |
|---|---|---|---|
| **Font size** | 14.0pt — smaller than author (24.0), smaller than title (29.0) | 9.0pt — smaller than author (12.0), smaller than title (17.9) | **No.** Both are simply "smaller than author," same relative pattern. Size alone cannot distinguish them — confirmed, matches §7.3's finding. |
| **Font family** | `Helvetica-Bold` — **identical** to the title's font (`Helvetica-Bold`) | `AdvP7D09` — **distinct** from both the title's and author's font (`AdvP7D0F`) | **Yes.** Brinkman's affiliation switches to a new font subset; Bruner's publisher line *reuses the title's exact font*, not a continuation in a new, smaller-text font. |
| **Bold state** | **Bold** — same as title, *not* the same as the immediately-preceding author line (not bold) | Not bold — same as both title and author (uniform, no reversion) | **Yes.** The author→affiliation transition in Brinkman never changes bold state. In Bruner, bold reverts from "off" (author) back to "on" (matching title) — a break in the expected monotonic title→author→affiliation de-emphasis sequence. |
| **Capitalization** | ALL CAPS — same convention as the title (`THE CULTURE OF EDUCATION`, also all caps) | Title Case — distinct from neither title nor author's casing pattern in a way that matches the title specifically | **Yes, but weaker** — a real, observed difference, but capitalization conventions vary more across publishers/documents than font/bold do, so this is corroborating, not load-bearing alone. |
| **Horizontal alignment** | Centered (x-center ≈289.5, page-center=306) — same as every other line on this page (title, author, city, country all centered) | Left-aligned (x0=42.5) — same as every other line on this page | **No.** Alignment reflects the whole page's layout convention; it does not distinguish this one line from its neighbors *within* either page. |
| **Vertical distance from author** | **225.7pt** (y0 317.5 → 543.2) — roughly 8-9× the author line's own height; a huge whitespace gap, placing the line in a visually separate block near the bottom of the page | **14.0pt** (y0 165.0 → 179.0) — tight, immediately the next line, no intervening whitespace | **Yes, strongly.** This is the same kind of signal (`gap_ratio`) already established and calibrated elsewhere in this codebase (`feature_007`'s continuation-detection). The magnitude difference here (225.7pt vs. 14.0pt) is not a borderline case. |
| **Page position** | Bottom third of page 1 (y0=543.2 of a ~792pt-tall page) | Upper portion of page 1 (y0=179.0), immediately above the Abstract | Consistent with, but redundant with, the vertical-distance-from-author signal above. |
| **Surrounding lines** | Followed immediately by "Cambridge, Massachusetts" / "London, England" — a self-contained publisher-colophon block (name + city + country), then the page ends | Followed immediately by "Abstract" (the zone-boundary keyword itself) | Corroborating: Bruner's block is structurally a *separate, self-contained unit*, not a continuation that terminates at the body-text boundary. |
| **Recurrence elsewhere in the document** | `"HARVARD UNIVERSITY PRESS"` (exact text) also appears on pages 24 and 25 of this 26-page document (verified via full-document text scan) | `"Institute of Education, London, UK"` appears **only** on page 1, nowhere else in this 18-page document | **Yes, strongly.** The author names themselves (`"Jerome Bruner"`, `"Suzana Brinkmann"`) each appear exactly once too — confirming "appears more than once" is specifically a publisher/imprint trait here, not just a generic property of any front-matter line. `Document.blocks` already contains every page's text (populated by `detect_structure()` document-wide, not just page 1), so this check requires no new PDF access — it is a scan over data already collected. |
| **Common publisher patterns (lexical)** | Contains `"PRESS"` — a common publisher-name token (also: "Publishing", "Publishers", "& Sons", "Books") | Contains none of these tokens | **Yes, but weakest evidence (n=1)** — a real pattern, but a keyword list calibrated against a single example is the most overfit of all the signals found; treat as corroborating only, consistent with the original audit's instruction not to introduce untested heuristics as the *primary* fix. |

### 8.3 Answer: yes, it can be excluded without harming Brinkman or any other benchmark document

Three independent, cheap, page-1-geometry-only signals — **bold-state reversion to the title's bold state**, **font-family match to the title's font** (rather than a distinct affiliation-tier font), and **vertical gap from the author line** — each cleanly separate this exact pair on their own, with no conflicting evidence between them. A fourth, the cross-page recurrence check, is also clean and requires no new PDF access (`Document.blocks` is already document-wide), though it is a different *kind* of check (text-equality scan, not pure typography) than the other three.

Validation scope is exactly the two documents in the corpus that currently produce any non-empty `affiliations` value under the proposed design (Bruner — false positive; Brinkman — true positive); no other benchmark PDF is affected by any of these candidate guards in either direction, since none of the others produce an affiliation value to check. Re-applying any one of the three geometry-based guards above to Brinkman's affiliation line confirms it is kept (not bold, distinct font from title, 14pt gap from author) while Bruner's is rejected (bold, same font as title, 225.7pt gap from author) — verified directly against the raw measurements in §8.1, not assumed.

This is reported as evidence only, per instruction not to implement: a deterministic signal demonstrably exists and was not found and reported in §7.3 only because that pass measured font size alone. Whether to adopt one of these signals now, defer to a follow-up, or continue accepting the imprecision as a named limitation remains an open decision for sign-off, not made here.

---

## 9. Implementation (2026-06-25)

**Status: IMPLEMENTED & VERIFIED.** All changes confined to `src/frontmatter/front_matter_extractor.py` (plus `tests/test_front_matter_extractor.py`); no other module, model, or pipeline stage touched.

### 9.1 What was implemented

1. **Boundary generalization** — `_find_zone_boundary()` tries the keyword check first (unchanged); if no keyword is found, falls back to the first line at-or-below body size (`_BODY_SIZE_BOUNDARY_TOLERANCE` = 0.5pt), or the end of the masthead window if neither signal fires.
2. **Kicker handling** — the kicker-skip condition now compares a short leading line against the *next* line's size, not the global threshold.
3. **Title/author tier separation** — both runs now stop at the first font-size change (`_TIER_SIZE_TOLERANCE` = 0.3pt), bounded by the title's own detected size rather than the global ratio constant.
4. **Affiliation guard #1 (mandatory, implemented)** — `_filter_affiliation_candidates()` rejects any candidate line at or above the detected title's font size, per line.
5. **Affiliation guard #2 (mandatory, implemented)** — rejects the entire affiliation remainder if the first candidate's `gap_ratio` from the preceding masthead line exceeds `_MAX_AFFILIATION_GAP_RATIO` = 2.0, calibrated against the real corpus values (Brinkman 0.169, Bruner 8.404 — see §9.2).
6. **Affiliation guard #3 (optional — skipped)** — the recurrence check needs document-wide blocks threaded through `extract_front_matter()` → `_build_front_matter()` → `_filter_affiliation_candidates()`, a larger plumbing change than the two mandatory guards required; skipped because both real benchmark false positives are already eliminated without it (documented in the module docstring).
7. **An additional guard not in the original 6-item list, added mid-implementation after stopping to report it (see §9.3):** title text must contain at least one space (rejects a single-token/glyph title) — this was already designed and validated in §3.4/§4 of this same audit, just not carried into this implementation pass's enumerated scope.

### 9.2 Gap-ratio calibration (guard #2), exact values

| | Author bbox (y0, y1) | Candidate bbox y0 | Author line height | gap_ratio |
|---|---|---|---|---|
| Brinkman (genuine, kept) | (164.98, 176.94) | 178.96 | 11.955 | **0.169** |
| Bruner (false positive, rejected) | (317.52, 341.52) | 543.22 | 24.000 | **8.404** |

`_MAX_AFFILIATION_GAP_RATIO = 2.0` sits with wide margin on both sides — over 10x Brinkman's real value, under a quarter of Bruner's.

### 9.3 Mid-implementation stop-and-report (per explicit instruction)

After implementing exactly the 6 enumerated required changes, the full-corpus verification (§9.4) surfaced that `sockett_profession.pdf` regressed from correctly-empty to a spurious title (`'e'`, a single 29.0pt OCR-garbled glyph) — the boundary-generalization fallback (item 1) now finds a boundary on this PDF where the old keyword-only logic never did, and nothing in the 6-item list screens out a single-glyph title. This exact risk and its mitigation (reject a title with no space) had already been designed and benchmark-validated in this same audit's §3.4/§4, but was not part of this implementation task's enumerated scope. Stopped and reported per instruction rather than silently adding or silently shipping the regression; user selected "add the already-audited §3.4 guard now." Implemented exactly as previously validated — no new, untested heuristic introduced.

### 9.4 Benchmark verification (real production code, not a prototype)

| PDF | Title | Authors | Affiliations |
|---|---|---|---|
| Brinkman | "Learner-centred education reforms in India: The missing piece of teachers' beliefs" | ["Suzana Brinkmann"] | ["Institute of Education, London, UK"] |
| Aims of Education | "AIMS OF EDUCATION: DO TEACHERS NEED TO BOTHER ABOUT THEM?" | ["Rohit Dhankar"] | [] |
| FolkPedagogy_Bruner | "THE CULTURE OF EDUCATION" | ["Jerome Bruner"] | [] |
| Calderhead | "Teaching as a professional activity" | ["James Calderhead"] | [] |
| Fullan & Hargreaves | "The teacher as a person" | ["Michael Fullan", "Andy Hargreaves"] | [] |

All 5 match the task's expected outcome exactly. Full 10-PDF sweep re-confirmed: `Nature of Enquiry`, `Bryman`, `O'Leary`, `Teaching-as-Discipline` unchanged (still empty); `sockett_profession.pdf` unchanged from its pre-feature_008 baseline (still empty, confirmed after §9.3's guard was added).

### 9.5 Test results

- `tests/test_front_matter_extractor.py`: 24 passed (18 pre-existing + 1 removed as obsolete by design + 7 new feature_008-specific tests covering boundary fallback, tier separation with both tiers above threshold, kicker-above-threshold, single-glyph rejection, and both affiliation guards individually).
- `tests/test_markdown.py` + `tests/test_docx.py`: 113 passed (includes `TestBrinkmanRegressionEndToEnd`, the only existing test that exercises front-matter rendering through the real pipeline) — confirms Brinkman's rendered output is unaffected.
- Full fast-subset suite (`pytest -m "not real_docling and not real_surya"`): see final summary appended after this run completes.

### 9.6 One test removed, not just left failing

`TestFailClosed::test_no_zone_boundary_keyword_within_window_yields_empty_front_matter` asserted the exact old behavior this feature deliberately supersedes (title + immediate body, no Abstract section → previously empty). Removed from `TestFailClosed` and replaced with `TestFeature008BoundaryGeneralization::test_title_with_no_keyword_boundary_extracted_via_body_size_fallback`, asserting the new, correct, intended outcome. The genuine fail-closed guarantee (no masthead-tier line at all) remains covered by the unchanged `test_no_title_sized_line_yields_empty_front_matter`.

### 9.7 Remaining known limitations

- **Bruner's publisher-imprint case is resolved by guard #2 here, but only because it happens to sit far below the author line.** A hypothetical document where a publisher name sits immediately after the author (small gap) would not be caught by either guard — no such case exists in the current 10-PDF corpus to validate against.
- **Aims' epigraph lands nowhere now** (correctly excluded from affiliations) but is also not captured as anything else — it's simply dropped from the zone's remainder. This is the same accepted imprecision flagged in §5.3/§6 item 2: no new "epigraph" category was introduced, consistent with "no model redesign."
- **Calderhead and Fullan&Hargreaves' title/author capture is implemented** per the task's explicit expected outcome, resolving the §6 item 1 open decision raised in the original audit in favor of "capture it."
- **Guard #3 (recurrence) remains unimplemented**, per §9.1 item 6 — both real false positives are eliminated without it; revisit only if a future document's affiliation false-positive isn't caught by guards #1/#2.

### 9.8 Full fast-subset suite, final result

`pytest -m "not real_docling and not real_surya"`: **871 passed, 7 skipped, 5 deselected, 0 failed** (15m34s) — up from the pre-feature_008 baseline of 865 passed/0 failed by exactly +6, matching `tests/test_front_matter_extractor.py`'s net change (18 pre-existing − 1 removed-as-obsolete + 7 new feature_008 tests = 24, +6 net). Zero regressions anywhere else in the suite.
