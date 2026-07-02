"use client";

import type {
  FootnoteItem,
  ImageItem,
  JobSummary,
  PageOcrInfo,
  TableItem,
  ValidationIssue,
} from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

type CheckStatus = "complete" | "manual" | "na" | "not_impl";

interface CheckItem {
  label: string;
  status: CheckStatus;
  detail: string;
}

interface CheckGroup {
  label: string;
  items: CheckItem[];
}

// ─── Signal derivation ────────────────────────────────────────────────────────

function buildChecklist(
  job: JobSummary,
  issues: ValidationIssue[],
  images: ImageItem[],
  footnotes: FootnoteItem[],
  pages: PageOcrInfo[],
  tables: TableItem[]
): CheckGroup[] {
  const pipelineRan = job.status === "complete" || job.status === "failed";

  // Helper: count issues by rule_id
  function byRule(...ids: string[]) {
    return issues.filter((i) => ids.includes(i.rule_id));
  }

  function pl(n: number, word: string) {
    return `${n} ${word}${n === 1 ? "" : "s"}`;
  }

  // ── Document Structure ────────────────────────────────────────────────────

  // Document Title — HEADING_002 fires only when no H1 is present
  const heading002 = byRule("HEADING_002");
  const titleStatus: CheckStatus =
    job.heading_count === null
      ? "not_impl"
      : heading002.length > 0
      ? "manual"
      : "complete";
  const titleDetail =
    titleStatus === "complete"
      ? "H1 heading detected"
      : titleStatus === "manual"
      ? "No H1 found — review heading structure"
      : "";

  // Heading Hierarchy — HEADING_001 fires on each level jump
  const heading001 = byRule("HEADING_001");
  const hierarchyStatus: CheckStatus =
    job.heading_count === null
      ? "not_impl"
      : heading001.length > 0
      ? "manual"
      : "complete";
  const hierarchyDetail =
    hierarchyStatus === "complete"
      ? `${pl(job.heading_count!, "heading")} verified`
      : hierarchyStatus === "manual"
      ? `${pl(heading001.length, "hierarchy jump")} detected`
      : "";

  // Front Matter — has_front_matter backed by Document.front_matter.title
  const frontMatterStatus: CheckStatus = !pipelineRan
    ? "not_impl"
    : job.has_front_matter
    ? "complete"
    : "na";
  const frontMatterDetail =
    frontMatterStatus === "complete"
      ? "Title and front matter extracted"
      : frontMatterStatus === "na"
      ? "Not applicable — no title page in document"
      : "";

  // Accessible Markdown
  const markdownStatus: CheckStatus = job.markdown_available ? "complete" : "not_impl";
  const markdownDetail = job.markdown_available ? "Generated successfully" : "";

  // Accessible DOCX
  const docxStatus: CheckStatus = job.docx_available ? "complete" : "not_impl";
  const docxDetail = job.docx_available ? "Generated with accessibility metadata" : "";

  // ── Navigation ────────────────────────────────────────────────────────────

  // Reading Order — PAGE_003
  const page003 = byRule("PAGE_003");
  const readingOrderStatus: CheckStatus =
    job.page_count === null
      ? "not_impl"
      : page003.length > 0
      ? "manual"
      : "complete";
  const readingOrderDetail =
    readingOrderStatus === "complete"
      ? `${pl(job.page_count!, "page")} verified`
      : readingOrderStatus === "manual"
      ? `${pl(page003.length, "page")} with order anomalies`
      : "";

  // Page Sequence — PAGE_001 (missing marker) and PAGE_002 (missing/duplicate)
  const pageSeqIssues = byRule("PAGE_001", "PAGE_002");
  const pageSeqStatus: CheckStatus =
    job.page_count === null
      ? "not_impl"
      : pageSeqIssues.length > 0
      ? "manual"
      : "complete";
  const pageSeqDetail =
    pageSeqStatus === "complete"
      ? `${pl(job.page_count!, "page")}, sequence verified`
      : pageSeqStatus === "manual"
      ? `${pl(pageSeqIssues.length, "sequence error")} detected`
      : "";

  // ── Images ────────────────────────────────────────────────────────────────

  const failedImages = images.filter((i) => i.extraction_failed);
  const imageExtractIssues = byRule("IMAGE_001", "IMAGE_002");

  const figuresStatus: CheckStatus =
    job.image_count === null
      ? "not_impl"
      : job.image_count === 0
      ? "na"
      : failedImages.length > 0 || imageExtractIssues.length > 0
      ? "manual"
      : "complete";
  const figuresDetail =
    figuresStatus === "complete"
      ? `${pl(images.length, "figure")} embedded`
      : figuresStatus === "manual"
      ? `${pl(failedImages.length, "extraction failure")}`
      : figuresStatus === "na"
      ? "No figures in document"
      : "";

  // Image Alt Text — pending_review means human hasn't confirmed the placeholder
  const pendingAlt = images.filter(
    (i) => i.figure?.alt_text_status === "pending_review"
  );
  const reviewedAlt = images.filter(
    (i) => i.figure?.alt_text_status === "human_reviewed"
  );
  const imagesWithFigures = images.filter((i) => i.figure !== null);

  // AI Alt Text — FEATURE_012 implemented; tracks images where AI generated alt text awaiting human confirmation
  const aiGeneratedImages = images.filter((i) => i.figure?.alt_text_status === "ai_generated");
  const aiDisposedImages = images.filter((i) =>
    ["human_reviewed", "approved", "decorative", "skipped", "complex"].includes(
      i.figure?.alt_text_status ?? ""
    )
  );
  const aiStatus: CheckStatus =
    job.image_count === null
      ? "not_impl"
      : job.image_count === 0
      ? "na"
      : aiGeneratedImages.length > 0
      ? "manual"
      : imagesWithFigures.length > 0 && aiDisposedImages.length === imagesWithFigures.length
      ? "complete"
      : "na";
  const aiDetail =
    aiStatus === "manual"
      ? `${pl(aiGeneratedImages.length, "image")} with AI alt text awaiting confirmation`
      : aiStatus === "complete"
      ? "All images reviewed with AI assistance"
      : aiStatus === "na"
      ? "Available on request in image review panel"
      : "";

  const altStatus: CheckStatus =
    job.image_count === null
      ? "not_impl"
      : job.image_count === 0
      ? "na"
      : pendingAlt.length > 0
      ? "manual"
      : imagesWithFigures.length > 0 && reviewedAlt.length === imagesWithFigures.length
      ? "complete"
      : "manual";
  const altDetail =
    altStatus === "manual" && pendingAlt.length > 0
      ? `${pl(pendingAlt.length, "image")} require alt text review`
      : altStatus === "manual"
      ? "Alt text review required"
      : altStatus === "complete"
      ? "All alt text reviewed"
      : altStatus === "na"
      ? "No figures in document"
      : "";

  // ── Footnotes ─────────────────────────────────────────────────────────────

  const actualFootnotes = footnotes.filter((f) => f.note_type === "footnote");
  const actualEndnotes = footnotes.filter((f) => f.note_type === "endnote");

  const footnoteStatus: CheckStatus =
    job.footnote_count === null
      ? "not_impl"
      : job.footnote_count === 0
      ? "complete"
      : job.docx_available
      ? "complete"
      : "manual";

  let footnoteDetail = "";
  if (footnoteStatus === "complete" && job.footnote_count === 0) {
    footnoteDetail = "No footnotes detected";
  } else if (footnoteStatus === "complete") {
    const parts: string[] = [];
    if (actualFootnotes.length > 0) parts.push(pl(actualFootnotes.length, "footnote"));
    if (actualEndnotes.length > 0) parts.push(pl(actualEndnotes.length, "endnote"));
    footnoteDetail =
      parts.length > 0
        ? `${parts.join(", ")} embedded as native OOXML`
        : "Embedded as native OOXML";
  } else if (footnoteStatus === "manual") {
    footnoteDetail = "Footnotes detected but DOCX not generated";
  }

  // ── Page Numbering ────────────────────────────────────────────────────────

  const pagesWithLabel = pages.filter((p) => p.printed_label !== null);
  const printedStatus: CheckStatus =
    pages.length === 0
      ? "not_impl"
      : pagesWithLabel.length > 0
      ? "complete"
      : "na";
  const printedDetail =
    printedStatus === "complete"
      ? `${pl(pagesWithLabel.length, "page")} with printed labels`
      : printedStatus === "na"
      ? "No printed labels detected in document"
      : "";

  // ── Validation ────────────────────────────────────────────────────────────

  // Overall errors
  const validationStatus: CheckStatus =
    job.error_count === null
      ? "not_impl"
      : job.error_count === 0
      ? "complete"
      : "manual";
  const validationDetail =
    validationStatus === "complete"
      ? `${pl(job.warning_count ?? 0, "warning")} — no errors`
      : validationStatus === "manual"
      ? `${pl(job.error_count!, "error")} detected`
      : "";

  // OCR Quality — OCR_001 (low confidence), OCR_002 (artifacts)
  const ocrIssues = byRule("OCR_001", "OCR_002");
  const ocrPages = pages.filter(
    (p) => p.extraction_method === "docling" || p.extraction_method === "surya"
  );
  const ocrStatus: CheckStatus =
    pages.length === 0
      ? "not_impl"
      : ocrPages.length === 0
      ? "na"
      : ocrIssues.length > 0
      ? "manual"
      : "complete";
  const ocrDetail =
    ocrStatus === "complete"
      ? `${pl(ocrPages.length, "OCR page")} — acceptable quality`
      : ocrStatus === "manual"
      ? `${pl(ocrIssues.length, "page")} with quality concerns`
      : ocrStatus === "na"
      ? "Direct text extraction — no OCR required"
      : "";

  // XML Sanitization — DOC_004 records each auto-sanitized character
  const xmlIssues = byRule("DOC_004");
  const xmlStatus: CheckStatus =
    job.error_count === null
      ? "not_impl"
      : xmlIssues.length === 0
      ? "complete"
      : "manual";
  const xmlDetail =
    xmlStatus === "complete"
      ? "No XML-illegal characters found"
      : `${pl(xmlIssues.length, "character")} auto-sanitized — confirm text integrity`;

  return [
    {
      label: "Document Structure",
      items: [
        { label: "Document Title",      status: titleStatus,       detail: titleDetail },
        { label: "Heading Hierarchy",   status: hierarchyStatus,   detail: hierarchyDetail },
        { label: "Front Matter",        status: frontMatterStatus, detail: frontMatterDetail },
        { label: "Accessible Markdown", status: markdownStatus,    detail: markdownDetail },
        { label: "Accessible DOCX",     status: docxStatus,        detail: docxDetail },
      ],
    },
    {
      label: "Navigation",
      items: [
        { label: "Reading Order",  status: readingOrderStatus, detail: readingOrderDetail },
        { label: "Page Sequence",  status: pageSeqStatus,      detail: pageSeqDetail },
      ],
    },
    {
      label: "Images",
      items: [
        { label: "Figures Embedded", status: figuresStatus, detail: figuresDetail },
        { label: "Image Alt Text",   status: altStatus,      detail: altDetail },
        { label: "AI Alt Text",   status: aiStatus,       detail: aiDetail },
      ],
    },
    {
      label: "Footnotes",
      items: [
        { label: "Native Word Footnotes", status: footnoteStatus, detail: footnoteDetail },
      ],
    },
    {
      label: "Page Numbering",
      items: [
        { label: "Printed Page Labels", status: printedStatus, detail: printedDetail },
      ],
    },
    {
      label: "Validation",
      items: [
        { label: "Validation Errors",  status: validationStatus, detail: validationDetail },
        { label: "OCR Quality",        status: ocrStatus,        detail: ocrDetail },
        { label: "XML Sanitization",   status: xmlStatus,        detail: xmlDetail },
      ],
    },
    {
      label: "Tables",
      items: (() => {
        const equationItem: CheckItem = {
          label: "Equation Accessibility",
          status: "not_impl",
          detail: "Phase 2 — not yet implemented",
        };
        if (!pipelineRan) {
          return [{ label: "Table Detection", status: "not_impl" as CheckStatus, detail: "" }, equationItem];
        }
        if (tables.length === 0) {
          return [{ label: "Table Detection", status: "na" as CheckStatus, detail: "No tables detected" }, equationItem];
        }
        const captionIssues    = byRule("TABLE_001", "TABLE_002");
        const structIssues     = byRule("TABLE_003", "TABLE_004");
        const confidenceIssues = byRule("TABLE_005", "TABLE_006", "TABLE_007");
        const reviewedTables   = tables.filter((t) => t.status === "reviewed");
        const pendingTables    = tables.filter((t) => t.status !== "reviewed");
        return [
          {
            label: "Table Detection",
            status: "complete" as CheckStatus,
            detail: `${pl(tables.length, "table")} detected`,
          },
          {
            label: "Tables Reviewed",
            status: (pendingTables.length > 0 ? "manual" : "complete") as CheckStatus,
            detail: pendingTables.length > 0
              ? `${reviewedTables.length}/${tables.length} reviewed — ${pl(pendingTables.length, "table")} pending`
              : `All ${tables.length} reviewed`,
          },
          {
            label: "Captions & Summaries",
            status: (captionIssues.length > 0 ? "manual" : "complete") as CheckStatus,
            detail: captionIssues.length > 0
              ? `${pl(captionIssues.length, "table")} missing caption or summary`
              : "Captions and summaries verified",
          },
          {
            label: "Structure & Headers",
            status: (structIssues.length > 0 ? "manual" : "complete") as CheckStatus,
            detail: structIssues.length > 0
              ? `${pl(structIssues.length, "issue")}: header row or merge problems`
              : "Header rows and structure verified",
          },
          {
            label: "Detection Confidence",
            status: (confidenceIssues.length > 0 ? "manual" : "complete") as CheckStatus,
            detail: confidenceIssues.length > 0
              ? `${pl(confidenceIssues.length, "warning")}: verify no false positives`
              : "No false positive risk",
          },
          equationItem,
        ];
      })(),
    },
  ];
}

// ─── Status icon ──────────────────────────────────────────────────────────────

function StatusIcon({ status }: { status: CheckStatus }) {
  if (status === "complete") {
    return (
      <span
        className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-green-500"
        aria-label="Complete"
        title="Complete"
      >
        <svg className="h-3 w-3" viewBox="0 0 12 12" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M2 6l3 3 5-5" />
        </svg>
      </span>
    );
  }
  if (status === "manual") {
    return (
      <span
        className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-400"
        aria-label="Manual review required"
        title="Manual review required"
      >
        <svg className="h-3 w-3" viewBox="0 0 12 12" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
          <path d="M6 3v3m0 2.5v.5" />
        </svg>
      </span>
    );
  }
  if (status === "na") {
    return (
      <span
        className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-gray-200 bg-gray-50"
        aria-label="Not applicable"
        title="Not applicable"
      >
        <span className="text-[10px] font-semibold text-gray-400 leading-none" aria-hidden="true">—</span>
      </span>
    );
  }
  // not_impl
  return (
    <span
      className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 border-gray-200"
      aria-label="Not yet implemented"
      title="Not yet implemented"
    />
  );
}

// ─── Status label ─────────────────────────────────────────────────────────────

const STATUS_LABELS: Record<CheckStatus, string> = {
  complete:  "Complete",
  manual:    "Manual Review",
  na:        "N/A",
  not_impl:  "Not Yet Implemented",
};

// ─── Single check row ─────────────────────────────────────────────────────────

function CheckRow({ item }: { item: CheckItem }) {
  const labelColor =
    item.status === "complete"
      ? "text-gray-900"
      : item.status === "manual"
      ? "text-gray-900"
      : "text-gray-400";

  const badgeClass =
    item.status === "complete"
      ? "bg-green-50 text-green-700 ring-1 ring-inset ring-green-200"
      : item.status === "manual"
      ? "bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200"
      : item.status === "na"
      ? "bg-gray-50 text-gray-400 ring-1 ring-inset ring-gray-200"
      : "bg-gray-50 text-gray-400 ring-1 ring-inset ring-gray-100";

  return (
    <li className="flex items-center gap-3 py-2.5 px-4">
      <StatusIcon status={item.status} />
      <span className={`flex-1 text-sm ${labelColor}`}>{item.label}</span>
      <div className="flex items-center gap-2 shrink-0">
        {item.detail && (
          <span className="hidden sm:inline text-xs text-gray-400 max-w-[200px] text-right leading-snug">
            {item.detail}
          </span>
        )}
        <span className={`inline-flex rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${badgeClass}`}>
          {STATUS_LABELS[item.status]}
        </span>
      </div>
    </li>
  );
}

// ─── Group block ─────────────────────────────────────────────────────────────

function CheckGroupBlock({ group }: { group: CheckGroup }) {
  const completeCount = group.items.filter((i) => i.status === "complete").length;
  const manualCount   = group.items.filter((i) => i.status === "manual").length;

  return (
    <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
      <div className="flex items-center justify-between gap-2 border-b border-gray-100 bg-gray-50 px-4 py-2">
        <span className="text-xs font-semibold text-gray-700 uppercase tracking-wide">
          {group.label}
        </span>
        <span className="text-[10px] text-gray-400 tabular-nums">
          {completeCount}/{group.items.length}
          {manualCount > 0 && (
            <span className="ml-1.5 text-amber-600 font-medium">
              · {manualCount} review
            </span>
          )}
        </span>
      </div>
      <ul role="list" className="divide-y divide-gray-50">
        {group.items.map((item) => (
          <CheckRow key={item.label} item={item} />
        ))}
      </ul>
    </div>
  );
}

// ─── Summary bar ─────────────────────────────────────────────────────────────

function SummaryBar({ groups }: { groups: CheckGroup[] }) {
  const allItems = groups.flatMap((g) => g.items);
  // Exclude n/a items from the denominator: a document with no images should not
  // be penalized for image checks, and "not yet implemented" items should not
  // deflate the score below what the reviewer can actually act on.
  const applicable     = allItems.filter((i) => i.status !== "na" && i.status !== "not_impl");
  const completeCount  = allItems.filter((i) => i.status === "complete").length;
  const manualCount    = allItems.filter((i) => i.status === "manual").length;
  const notImplCount   = allItems.filter((i) => i.status === "not_impl").length;
  const total          = applicable.length;

  const completePct = total === 0 ? 100 : Math.round((completeCount / total) * 100);

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 space-y-3">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <div className="flex items-center gap-2">
          <span className="flex h-3 w-3 rounded-full bg-green-500" aria-hidden="true" />
          <span className="text-sm text-gray-700">
            <span className="font-semibold tabular-nums">{completeCount}</span> Complete
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="flex h-3 w-3 rounded-full bg-amber-400" aria-hidden="true" />
          <span className="text-sm text-gray-700">
            <span className="font-semibold tabular-nums">{manualCount}</span> Manual Review Required
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="flex h-3 w-3 rounded-full border-2 border-gray-300" aria-hidden="true" />
          <span className="text-sm text-gray-700">
            <span className="font-semibold tabular-nums">{notImplCount}</span> Not Yet Implemented
          </span>
        </div>
        <span className="ml-auto text-xs text-gray-400 tabular-nums">
          {completePct}% complete ({completeCount}/{total})
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-1.5 w-full rounded-full bg-gray-100 overflow-hidden" role="progressbar" aria-valuenow={completePct} aria-valuemin={0} aria-valuemax={100}>
        <div
          className="h-full rounded-full bg-green-500 transition-all"
          style={{ width: `${completePct}%` }}
        />
      </div>
    </div>
  );
}

// ─── Composed panel ───────────────────────────────────────────────────────────

export interface ChecklistPanelProps {
  job: JobSummary;
  issues: ValidationIssue[];
  images: ImageItem[];
  footnotes: FootnoteItem[];
  pages: PageOcrInfo[];
  tables: TableItem[];
}

export function ChecklistPanel({ job, issues, images, footnotes, pages, tables }: ChecklistPanelProps) {
  const groups = buildChecklist(job, issues, images, footnotes, pages, tables);

  return (
    <section aria-labelledby="checklist-heading">
      <div className="flex items-center gap-2 mb-3">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-slate-700 text-white" aria-hidden="true">
          <svg className="h-3 w-3" viewBox="0 0 12 12" fill="none" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2 3.5h8M2 6h5M2 8.5h3" />
          </svg>
        </span>
        <h2 id="checklist-heading" className="text-sm font-bold text-gray-900 uppercase tracking-wide">
          Accessibility Checklist
        </h2>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-600">
          WinVinaya Remediation Standard
        </span>
      </div>

      <div className="space-y-3">
        <SummaryBar groups={groups} />
        {groups.map((group) => (
          <CheckGroupBlock key={group.label} group={group} />
        ))}
      </div>
    </section>
  );
}
