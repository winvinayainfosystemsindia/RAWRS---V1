# ADR — Projection Correctness

**Date:** 2026-08-03 · **Status:** Accepted · **Supersedes:** byte equality as a projection gate

## Context

P2 moved paragraph grouping, note labelling and prose segmentation out of the Markdown
renderer and into the Semantic Document. Output changed on 3 of 10 benchmark documents.
The investigation established:

| Finding | Evidence |
|---|---|
| No content changed | Word multiset identical in all 3 documents (21384 / 7921 / 9009; 0 lost, 0 gained) |
| 20 headings appeared, 0 disappeared | The detector had produced them since 2026-06-25; the renderer discarded them |
| Cause: an unwritten renderer invariant | "heading text == exactly one extracted line, and that line survives the suppression cascade" |
| Failure was non-local | A sequential `pending[0]` queue stall deleted every later heading on the page (5 on sockett p1) |
| 3 of the 20 were detector false positives | Suppressed by accident — an *unrelated* heading stalled the queue upstream |

The last row is decisive: **the old output's heading precision was partly manufactured by a
rendering defect.** Byte parity would have protected that defect indefinitely.

## Decision

Byte equality is retired as the correctness criterion for a projection. Correctness is
redefined as a set of invariants between a projection and the Semantic Document that produced
it — checkable on any document, with no reference to a previous run.

---

## 1. What semantic parity means

| | Definition | Compares |
|---|---|---|
| **Byte parity** (retired) | `render(D) == bytes_from_a_previous_run` | present output vs **history** |
| **Semantic parity** (adopted) | every object and every word in `render(D)` is accounted for by `D`, and vice versa | present output vs **the model that produced it** |

A projection `P` of Semantic Document `D` is correct when:

1. every renderable object in `D` is realized exactly once in `P`, **or** its absence is
   authorized by a fact recorded in `D`;
2. every object realized in `P` traces back to an object in `D`;
3. the content of `P` is the content of `D` — no words invented, none lost except by
   authorized suppression.

Parity is a property of the **current state**, not of a diff against a stored artifact. That
is what makes it safe to improve a projection: fixing the renderer cannot fail the gate,
because the gate never asserted that yesterday's rendering was right.

## 2. Acceptable projection differences

| Difference | Why acceptable |
|---|---|
| Role reassignment the model authorizes (bold paragraph → heading) | `D` always said it was a heading; `P` finally says so too |
| Prose re-segmented into different paragraph boundaries | Same words, different block boundaries |
| Ordering that follows a recorded relationship | The relationship is the authority, not the previous order |
| Markup carrying no semantics (`**x**` vs `## x`, wrapping, whitespace) | No object and no word changed |
| Objects becoming visible because a projection defect was removed | The model already contained them |
| Paragraph count changing when a run boundary moves | Paragraph count is not a semantic quantity |

## 3. Forbidden projection differences

| Violation | Definition |
|---|---|
| **Lost object** | An object exists in `D`, is not realized in `P`, and no recorded fact authorizes its absence |
| **Invented object** | `P` realizes a heading / table / list / image / note with no counterpart in `D` |
| **Content loss** | Text present in `D` is absent from `P` without authorization |
| **Content invention** | Text present in `P` occurs nowhere in `D` |
| **Duplicate realization** | One object realized more than once |
| **Silent renderer decision** | Any suppression, promotion, merge or reorder a projection performs that no fact in `D` records |

The last is the class that caused this ADR, and it is forbidden **regardless of whether the
outcome happens to be desirable.** A projection that drops a false-positive heading is still
in violation: it made a semantic judgement it had no authority to make, and it will drop
correct headings by the same mechanism. It did, twenty times.

## 4. Invariants every renderer must satisfy

| ID | Invariant | Enforced by |
|---|---|---|
| **PI-1** | **Object realization.** Every renderable object in `D` appears in `P`, or its absence is authorized. | `check_projection` |
| **PI-2** | **No invention.** Every object realized in `P` resolves to an object in `D` by identity. | `check_projection` |
| **PI-3** | **Content conservation.** `words(P) ⊆ words(D)` and `words(visible D) ⊆ words(P)`. | `check_projection` |
| **PI-4** | **Authorized absence.** Every omitted line is explained by a recorded fact — a suppression correction, a containment edge, or a documented generation rule. | `check_projection` |
| **PI-5** | **Single realization.** No object is realized twice. | `check_projection` |
| **PI-6** | **No reconstruction.** A projection may not re-derive a semantic fact the model can state. It consumes; it does not decide. | Review — the other five make it enforceable |

PI-6 is the only one not mechanically checkable. It is the design rule the other five make
practical: once a projection cannot silently suppress or invent, the remaining way to be wrong
is to compute something the model should own, and that is visible in review.

## 5. Detector quality vs renderer correctness

They are **orthogonal axes and must be measured separately.**

| | Question | Ground truth | Range |
|---|---|---|---|
| Detector quality | Did RAWRS identify the right objects? | Human-remediated corpus | Graded (P / R / F1) |
| Projection correctness | Did the output faithfully express what RAWRS identified? | The Semantic Document itself | Binary (holds / violated) |

**A renderer defect contaminates detector metrics.** Heading P/R/F1 is computed from the
generated DOCX — a projection. Pre-P2 that projection was silently deleting 20 detected
headings, 3 of them wrong, so the measured precision of 0.5469 described neither the detector
nor the renderer but their combination. A renderer that filters false positives *flatters*
precision; a renderer that stalls *depresses* recall. Neither number is about the detector.

The resolution is not to re-plumb the measurement but to **make the projection provably
faithful.** Once PI-1 … PI-5 hold, the projection is a lossless view of `D` for every realized
object, so measuring the DOCX becomes equivalent to measuring the model. Detector metrics
become trustworthy *because* projection correctness is separately guaranteed.

Corollary: a change that improves projection correctness may move detector metrics in either
direction. That movement is **information about the detector**, newly visible — not a
regression. It must be attributed, never suppressed.

## 6. How benchmarks evolve

Three layers, evaluated independently:

| Layer | Asks | Corpus | Gate |
|---|---|---|---|
| **1. Projection correctness** | Does the output express the model? | **Any document** — no ground truth needed | Hard: any violation blocks |
| **2. Detector quality** | Did we find the right objects? | 10 human-remediated DOCX | Soft: must not regress without cause |
| **3. Remediation quality** | Is the result accessible? | Accessibility rules, WCAG | Soft |

Consequences:

- Layer 1 needs **no ground truth**, so it applies to every document RAWRS ever processes, not
  only the ten in the corpus. It is the stronger specification precisely because it is
  self-referential.
- Byte comparison is **retained as an investigative signal, not a gate.** It correctly told us
  to look; it was wrong only as an arbiter. Keep running it; treat a diff as a question.
- A new projection (DOCX, HTML, EPUB, the workspace itself) inherits Layer 1 for free: same
  invariants, same `D`.
- Layer 2 metrics must be reported **alongside** the Layer 1 result, never in place of it. A
  precision improvement accompanied by a PI violation is not an improvement.

## Consequences

- P2 is approved. Its output difference is a Layer-1 *repair*, not a Layer-2 regression.
- Byte parity is removed from the definition of done for projection work.
- The 3 detector false positives (`Chapter 3);`, `"ox.o..IA1.M· ~`, `NuN 14k`) become a
  detector ticket with its own before/after precision measurement — not a renderer concern.
- `src/benchmark/projection.py` implements PI-1 … PI-5. Production must not import it.
