# RAWRS Status Report — measured 2026-09-30

Every number below was measured or fetched on 2026-09-30 unless a **Source** column says otherwise. "Not re-measured" means it comes from an older project document.

> **Update 2026-10-01 — equations.** Phase A of `docs/EQUATION_DESIGN.md` (Mathpix route) is built and uncommitted: native Word equations, `\ce` chemistry subset, correction-rail edits, review queue, `DR-EQ` audit. On real arXiv equations 81 of 82 confident rows convert and round-trip. **Open for the company:** the command allowlist is narrow (about half of real physics display equations are flagged), the PDF-only route is not built, and nothing has been read in Word or with a screen reader. Sections below are otherwise as of 2026-09-30; §5 "Planned" no longer lists equations as unstarted.

## 1. Verdict

| Question | Answer |
|---|---|
| Does it work end to end? | Yes — PDF (born-digital or scanned) → Markdown + checklist-audited DOCX, with a review workspace. Mathpix is optional. |
| Is it shippable to a team today? | **No.** No authentication, one-process in-memory job state, no concurrency control, and **CI is red** (§4). |
| Can it be hosted at $0 with no card? | Only from your own PC through a Cloudflare tunnel. Oracle is unusable without a card (§6). |

## 2. Measured snapshot

| Item | Value | Source |
|---|---|---|
| Git history | 127 commits, 2026-06-30 → 2026-09-28, branch `main` only | `git log` |
| Backend | 157 Python files, ~36.4k lines, 45 HTTP routes | `find src`, `@router` count |
| Validation/verification rule IDs | 68 distinct IDs in `src/validation` + `src/verification` | grep of rule-ID strings |
| Checklist audit | 40 checks (`DR-*`, `SUB-*`) | `src/validation/checklist_audit.py` |
| Backend tests (CI, run 36454387742, 2026-09-28) | **2537 passed, 5 failed** in 12 batches | `gh run view --log` |
| Frontend tests (same run) | 38 Jest tests / 14 suites passed; typecheck + production build passed | same |
| Checklist result on O'Leary scan | 28 pass / 0 fail; 98.9 % of OCR words present | `docs/CHECKLIST_COMPLIANCE.md` (not re-measured) |
| Processing time, this laptop (i5-1135G7, 4 cores, 7.7 GB RAM, no GPU) | 126 finished local jobs: median 7.5 s; slowest 782 s (O'Leary, scanned, OCR) and 432 s (Brinkman) | `outputs/jobs/*.json` (median is pulled down by repeat test runs) |
| Alt text | ~2.5 min per image on CPU with `qwen2.5vl:3b` | `docs/KNOWN_LIMITATIONS.md` (not re-measured) |
| Disk per processed document | 682 MB / 127 jobs ≈ 5.4 MB average | `outputs/` |
| Model caches on this PC | Hugging Face cache 17.4 GB; Ollama 9.1 GB (upper bounds — may include non-RAWRS models) | filesystem |

## 3. Completed

| Area | State | Evidence |
|---|---|---|
| Extraction | Native text, Docling OCR, Surya fallback, per-page routing | `src/ocr/`, `PHASE_STATUS.md` |
| Document model + correction rail | Every reviewer change is a reversible `CorrectionRecord`; 11 verifier types | `src/models/`, `src/verification/` |
| Structure | Headings H1–H6, lists, tables (4 detectors), footnotes/endnotes, images, callouts, front matter, page labels | `src/*` |
| Mathpix path | MMD import, proven page alignment, cross-source verification | `src/mathpix/`, `src/verification/` |
| Outputs | Markdown and DOCX (native Word notes, real headings, table header rows, language/title metadata) | `src/docx/`, `src/markdown/` |
| Checklist compliance | DOCX audited against both remediation checklists after every run | `CHECKLIST_COMPLIANCE.md` |
| Auto alt text | Local Ollama `qwen2.5vl:3b`; decorative detection; human review kept | `src/images/auto_alt_text.py` |
| Review workspace | Full-width, PDF + editable Markdown + live DOCX preview; workspaces for headings, reading order, images, tables, notes, page labels, corrections, metadata | `frontend/` |
| Persistence | Jobs and review state survive a restart (FE-0-001) | `MASTER_IMPLEMENTATION_BACKLOG.md` |
| Equations (added 2026-10-01) | Mathpix route: native Word equations, `\ce` subset, flagged-not-guessed, review queue, `DR-EQ` audit; 81 of 82 real arXiv equations round-trip | `docs/EQUATION_DESIGN.md` §8, `tests/test_equation_*.py` |
| Packaging | `Dockerfile` + `docker-compose.yml` (API, Ollama, Cloudflare tunnel); GitHub Actions CI | repo root, `.github/workflows/tests.yml` |

## 4. Not working or open

| # | Item | Effect | Status |
|---|---|---|---|
| 1 | **CI is red** — 5 failures in `tests/test_pipeline.py` (the last 3 runs that finished all failed, 2 others were cancelled; cause checked only for the latest) | No green baseline | 3 of 5 explained (one reproduced locally): `IMAGE_004` is raised only for *pending* alt text; since automatic alt text (`054a891`) images are no longer pending, so the test's "one `IMAGE_004` per image" (0 ≠ 4) is stale. The other 2 (`TestStructureDetectionDoesNotChangeExistingOutputs`, Nature of Enquiry + Bruner) **are not diagnosed**. |
| 2 | No authentication inside RAWRS | Anyone reaching the API can edit any document | Open, `DEPLOYMENT.md` |
| 3 | In-memory job state, `--workers 1` | One instance only | Open, `src/api/jobs.py` |
| 4 | No concurrency control | Two reviewers on one document overwrite each other | Open |
| 5 | Oracle deployment route | Unusable without a card; free allowance is now 2 OCPU / 12 GB, not 4 / 24 GB | Runbook rewritten in `DEPLOYMENT.md` |
| 6 | Export-readiness gate counts mirrored cross-source warnings | "Export Ready" stays red until ~300 warnings clear | Open, deferred |
| 7 | Markdown edits bypass the object model | A saved edit wins over later object reviews until discarded | By design, documented |
| 8 | 9 frontend lint errors (React Compiler) | CI lint is informational | Open |
| 9 | Line-by-line render path still text-keyed (41 of 161 corpus pages) | Largest obstacle to the projection refactor | Open, `KNOWN_LIMITATIONS.md` |
| 10 | Cross-page tables and paragraphs are not joined | Reviewer fixes by hand | Open, Phase 1 out of scope |
| 11 | First ARM Docker build (torch/docling/surya on aarch64) never run | Unproven | Open; an x86 VPS avoids it |

## 5. Planned

There is no single current roadmap file. This table is assembled from `KNOWN_LIMITATIONS.md`, `MASTER_IMPLEMENTATION_BACKLOG.md` and the decisions log. **"Proposed"** rows are mine, not agreed.

| Item | Source |
|---|---|
| Fix or rewrite the 5 CI tests → green baseline | Proposed |
| Pick a hosting route and run the first deployment | Proposed (§6) |
| Authentication + concurrency control before any multi-user use | `DEPLOYMENT.md` known gaps |
| Durable store beside in-memory jobs (A12-1), stable object IDs (A02) | Backlog |
| Finish DOCX-from-model projection; retire the line-by-line render path (A14-1) | Backlog, `KNOWN_LIMITATIONS.md` |
| Readiness keyed on unresolved corrections, not mirrored warnings | `KNOWN_LIMITATIONS.md` |
| Second live walkthrough on a figure/table-rich document (first covered neither) | Backlog, FE-0 |
| Frontend phases F–I (nav tree, policy-aware PAGE_001, performance on large documents) | Decisions log Part 25 |
| Out of Phase 1 by decision: equations/STEM, PDF/UA tagging, multi-reviewer collaboration, DB-backed multi-tenant | `PHASE1_SCOPE.md` |

## 6. Hosting estimates

Prices fetched 2026-09-30; excl. VAT. Throughput below is **not load-tested** — it is reasoned from §2.

| Option | Monthly cost | Blockers | Fit |
|---|---|---|---|
| Your PC + Cloudflare quick tunnel + Vercel Hobby | $0 | Up only while the PC is on; tunnel URL changes each run | Demo/pilot |
| Oracle Always Free (A1) | $0 | **Card required** for verification; allowance is now 2 OCPU / 12 GB | Fits API (~4 GB) + Ollama 3B (~3 GB) per existing docs; blocked for you |
| Hetzner CX43 (x86, 8 vCPU, 16 GB, 160 GB) | €15.99 (+ ~€0.50 IPv4) | Needs a payment method | Recommended if funded: 16 GB avoids the swap/OOM seen on this 8 GB laptop; x86 avoids the untested ARM build |
| Hetzner CAX31 (ARM, 8 vCPU, 16 GB) | €20.99 | ARM build unproven | Dearer and riskier than CX43 |
| Hetzner CX33 / CAX21 (4 vCPU, 8 GB) | €8.49 / €10.49 | 8 GB is marginal with Ollama + OCR | Not recommended |
| Cloudflare Tunnel + Access | $0 (Access free ≤ 50 users; $7/user beyond) | — | Yes |
| Vercel Hobby / Pro | $0 non-commercial / $20 per seat | Hobby is licensed for non-commercial use only | Ask §7 Q1 |
| Mathpix API (only if the MMD path is used) | $0.005/page + $19.99 one-time key fee | Not needed for the PDF-only path | e.g. 10,000 pages ≈ $50 |

| Scenario (12 months) | Cost |
|---|---|
| A: PC + tunnel + Vercel Hobby | $0 |
| B: Hetzner CX43 + Cloudflare free + Vercel Hobby | ≈ €198 (~€16.5 × 12) |
| C: B with Vercel Pro, one seat | ≈ €198 + $240 |

Storage: ~5.4 MB per document → 1,000 documents ≈ 5.4 GB, well inside an 80–160 GB disk. One document is processed at a time; OCR-heavy documents take minutes (§2).

## 7. Questions for the company

| # | Question | Why it matters |
|---|---|---|
| 1 | Is RAWRS internal/non-commercial, or does anyone pay for it? | Vercel Hobby is non-commercial only; licences below depend on it |
| 2 | **PyMuPDF is AGPL-3.0 (or a paid Artifex licence).** Is publishing RAWRS's source to its users acceptable? | AGPL §13 applies to a network service. The GitHub repo is public but has **no LICENSE file**. A commercial licence is reported at $10k–50k/yr (third-party blog — ask Artifex). |
| 3 | Does WinVinaya fall under the Surya model-weights licence terms? | Weights are free below a revenue/funding cap ($2M in older versions, $5M in current) and the cap differs by version — read `datalab-to/surya-ocr-2` LICENSE for the pinned 0.20.0 |
| 4 | Is using `qwen2.5vl:3b` acceptable? Its licence is **Qwen Research (non-commercial)** | The 7B model is Apache-2.0 but needs ~14 GB RAM (a larger server) |
| 5 | Budget and payment method: company card for a VPS, or an on-premises machine? | Decides §6 |
| 6 | Where may documents be stored? Are any PDFs student or personal data? | Privacy, retention, backups; hosting region |
| 7 | Are rights holders fine with the copyrighted benchmark PDFs sitting in the public repo? | Committed 2026-09-17 on the owner's approval; the company should confirm |
| 8 | Reviewer count, roles, and identity provider (Google Workspace, Microsoft, other)? | Authentication design; Cloudflare Access covers ≤ 50 users |
| 9 | Expected volume (documents and pages per month) and turnaround? | Server size; whether one-at-a-time processing is acceptable |
| 10 | Is the Mathpix path required, and is there an account/budget? | Mathpix is optional now; key fee and per-page cost apply |
| 11 | Uptime: business hours only, or 24×7? | A PC tunnel cannot be 24×7 |
| 12 | Is a company domain available for a stable API URL? | Named tunnels need a domain |
| 13 | Is AI alt text acceptable with human review, or must a person write every one? | Policy; changes the workflow |
| 14 | House-style rulings: punctuation rule 4 ("space after an open bracket"), TOC when a document has none, author when the source names none | Left open by design, `CHECKLIST_COMPLIANCE.md` |

## 8. Not verified in this report

| Item | Why |
|---|---|
| Docling's licence, and licences of other pinned Python packages | Not checked — request a full dependency licence scan |
| API RAM ~4 GB peak, Ollama ~3 GB | From `DEPLOYMENT.md`, not re-measured |
| Throughput on a server | Not load-tested |
| Hetzner payment methods, Cloudflare Pages commercial terms | Not checked |

## Sources

- [Oracle Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) · [Hacker News thread on the cut](https://news.ycombinator.com/item?id=49183750)
- [Hetzner price adjustment, 15 June 2026](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/)
- [Vercel pricing summary](https://costbench.com/software/developer-tools/vercel/)
- [Cloudflare Zero Trust pricing summary](https://zerotrustcost.com/cloudflare-zero-trust-pricing)
- [Mathpix API pricing](https://mathpix.com/pricing/api)
- [PyMuPDF licence discussion](https://github.com/pymupdf/PyMuPDF/discussions/971) · [Surya](https://github.com/datalab-to/surya) · [Qwen2.5-VL-3B licence](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct/blob/acbce9a6c80e81356680a632166380c8cc1d27ec/LICENSE)
