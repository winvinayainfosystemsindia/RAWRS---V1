"use client";

import { useEffect, useMemo, useState } from "react";
import {
  useDocumentData,
  selectHeadings,
  selectTables,
  selectImages,
  selectFootnotes,
  selectLists,
  selectCallouts,
  selectCorrections,
  footnoteKey,
  listKey,
  calloutKey,
} from "@/lib/store/DocumentDataContext";
import { useSelection, type SelectableObjectType } from "@/lib/store/SelectionContext";
import { usePdfViewport } from "@/lib/store/PdfViewportContext";
import { useMarkdownViewport } from "@/lib/store/MarkdownViewportContext";
import { useArrowKeyTabs } from "@/lib/hooks/useArrowKeyTabs";
import { HeadingCard } from "@/components/HeadingCard";
import { TableCard } from "@/components/TableCard";
import type { BoundingBox } from "@/lib/api";

export interface NavSection {
  id: string;
  label: string;
  count?: number;
  urgentCount?: number;
}

interface SemanticNavTreeProps {
  // "Special views" — whole-document editors that take over the center+
  // right area (Images gallery, Metadata, OCR Pages, Reading Order, Page
  // Labels, Corrections board, Readiness, Validation center). Distinct from
  // object-level selection below.
  specialViews: NavSection[];
  activeSpecialView: string | null;
  onSelectSpecialView: (id: string) => void;
  // Bumped by the toolbar's Search button (same nonce idiom as
  // PdfViewportContext's jumpTarget) so it can switch this nav to Search
  // mode without lifting `mode` state out of this component.
  focusSignal?: number;
}

type NavMode = "outline" | "by-type" | "corrections" | "validation" | "search";

const MODES: { id: NavMode; label: string }[] = [
  { id: "outline", label: "Outline" },
  { id: "by-type", label: "By Type" },
  { id: "corrections", label: "Pending" },
  { id: "validation", label: "Issues" },
  { id: "search", label: "Search" },
];
const MODE_IDS = MODES.map((m) => m.id);

// Reserved for Feature 021+ — not implemented this phase. Kept visible but
// disabled so later work slots into this nav without restructuring it.
const RESERVED_SECTIONS = [
  "Spread Detection",
  "Recovery Engine",
  "Evidence Fusion",
  "Semantic Region Inspector",
  "Benchmark Dashboard",
  "OCR Region Review",
  "AI Suggestions",
];

function NavRow({
  label,
  isActive,
  onClick,
  count,
  urgentCount,
  indentRem = 0,
}: {
  label: string;
  isActive?: boolean;
  onClick: () => void;
  count?: number;
  urgentCount?: number;
  indentRem?: number;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={isActive ? "true" : undefined}
      style={indentRem ? { paddingLeft: `${0.75 + indentRem}rem` } : undefined}
      className={`flex w-full items-center justify-between gap-2 border-l-2 px-3 py-1.5 text-left text-sm transition-colors ${
        isActive
          ? "border-accent bg-hover-row text-text-primary font-medium"
          : "border-transparent text-text-secondary hover:bg-hover-row hover:text-text-primary"
      }`}
    >
      <span className="truncate">{label}</span>
      <span className="flex shrink-0 items-center gap-1">
        {!!urgentCount && urgentCount > 0 && (
          <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-danger/20 px-1 font-mono text-[10px] text-danger">
            {urgentCount}
          </span>
        )}
        {typeof count === "number" && (
          <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-surface-elevated px-1 font-mono text-[10px] text-text-secondary">
            {count}
          </span>
        )}
      </span>
    </button>
  );
}

export function SemanticNavTree({
  specialViews,
  activeSpecialView,
  onSelectSpecialView,
  focusSignal,
}: SemanticNavTreeProps) {
  const [mode, setMode] = useState<NavMode>("outline");
  useEffect(() => {
    if (focusSignal) setMode("search");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusSignal]);
  // Phase F-3.2 — shared ARIA-tabs keyboard model.
  const navTabs = useArrowKeyTabs({ ids: MODE_IDS, active: mode, onChange: setMode });
  const state = useDocumentData();
  const { selection, select } = useSelection();
  const { jumpToObject } = usePdfViewport();
  const { jumpToLine } = useMarkdownViewport();

  const headings = useMemo(() => selectHeadings(state), [state]);
  const tables = useMemo(() => selectTables(state), [state]);
  const images = useMemo(() => selectImages(state), [state]);
  const footnotes = useMemo(() => selectFootnotes(state), [state]);
  const lists = useMemo(() => selectLists(state), [state]);
  const callouts = useMemo(() => selectCallouts(state), [state]);
  const corrections = useMemo(() => selectCorrections(state), [state]);

  // Selecting any document object returns to the document view (PDF +
  // Markdown + Context Inspector), leaving whatever special view was open.
  function selectObject(
    objectType: SelectableObjectType,
    objectId: string | number,
    pageNumber: number,
    bbox: BoundingBox | null,
    sourceLine?: number | null
  ) {
    select(objectType, objectId);
    onSelectSpecialView("");
    jumpToObject(pageNumber, bbox);
    if (sourceLine != null) jumpToLine(sourceLine);
  }

  const isSelected = (type: SelectableObjectType, id: string | number) =>
    selection?.objectType === type && selection.objectId === id;

  return (
    <nav aria-label="Document sections" className="flex flex-col py-2">
      <div
        role="tablist"
        aria-label="Navigation mode"
        ref={navTabs.tablistRef as React.RefObject<HTMLDivElement>}
        className="flex flex-wrap gap-1 border-b border-border px-2 pb-2"
      >
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            {...navTabs.getTabProps(m.id)}
            className={`rounded px-2 py-1 text-[11px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
              mode === m.id
                ? "bg-accent text-accent-contrast"
                : "text-text-secondary hover:bg-hover-row hover:text-text-primary"
            }`}
          >
            {m.label}
          </button>
        ))}
        <button
          type="button"
          disabled
          title="Reserved for a future phase"
          className="rounded px-2 py-1 text-[11px] font-medium text-text-secondary/40 cursor-not-allowed"
        >
          Bookmarks
        </button>
      </div>

      {mode === "by-type" && (
        <>
          <ExpandableCategory
            label="Headings"
            count={headings.length}
            defaultOpen
          >
            {headings.length === 0 && <EmptyRow text="No headings detected." />}
            <ul>
              {headings.map((h) => (
                <HeadingCard
                  key={h.document_order}
                  heading={h}
                  isSelected={isSelected("heading", h.document_order)}
                  onSelect={() => selectObject("heading", h.document_order, h.page_number, h.bbox, h.source_line)}
                />
              ))}
            </ul>
          </ExpandableCategory>

          <ExpandableCategory label="Tables" count={tables.length}>
            {tables.length === 0 && <EmptyRow text="No tables detected." />}
            <ul>
              {tables.map((t) => (
                <TableCard
                  key={t.table_id}
                  table={t}
                  isSelected={isSelected("table", t.table_id)}
                  onSelect={() => selectObject("table", t.table_id, t.page_number, t.bbox, t.source_line)}
                />
              ))}
            </ul>
          </ExpandableCategory>

          <ExpandableCategory label="Lists" count={lists.length}>
            {lists.length === 0 && <EmptyRow text="No lists detected." />}
            <ul>
              {lists.map((l) => {
                const key = listKey(l);
                return (
                  <li key={key}>
                    <NavRow
                      label={l.items[0]?.text || "(empty list)"}
                      isActive={isSelected("list", key)}
                      indentRem={0.5}
                      onClick={() => selectObject("list", key, l.page_number, l.bbox, l.source_line)}
                    />
                  </li>
                );
              })}
            </ul>
          </ExpandableCategory>

          <ExpandableCategory label="Callouts" count={callouts.length}>
            {callouts.length === 0 && <EmptyRow text="No callouts detected." />}
            <ul>
              {callouts.map((c) => {
                const key = calloutKey(c);
                return (
                  <li key={key}>
                    <NavRow
                      label={c.label}
                      isActive={isSelected("callout", key)}
                      indentRem={0.5}
                      onClick={() => selectObject("callout", key, c.page_number ?? 1, c.bbox, c.source_line)}
                    />
                  </li>
                );
              })}
            </ul>
          </ExpandableCategory>

          <ExpandableCategory label="Footnotes" count={footnotes.length}>
            {footnotes.length === 0 && <EmptyRow text="No footnotes detected." />}
            <ul>
              {footnotes.map((n) => {
                const key = footnoteKey(n);
                return (
                  <li key={key}>
                    <NavRow
                      label={n.body}
                      isActive={isSelected("footnote", key)}
                      indentRem={0.5}
                      onClick={() => selectObject("footnote", key, n.anchor_page_number, null)}
                    />
                  </li>
                );
              })}
            </ul>
          </ExpandableCategory>

          <div className="mt-3 border-t border-border pt-2">
            <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-text-secondary/70">
              Workspaces
            </p>
            <ul>
              {specialViews.map((section) => (
                <li key={section.id}>
                  <NavRow
                    label={section.label}
                    isActive={activeSpecialView === section.id}
                    onClick={() => onSelectSpecialView(section.id)}
                    count={section.count}
                    urgentCount={section.urgentCount}
                  />
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-3 border-t border-border pt-2">
            <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-text-secondary/70">
              Reserved
            </p>
            <ul>
              {RESERVED_SECTIONS.map((label) => (
                <li key={label}>
                  <button
                    type="button"
                    disabled
                    title="Reserved for a future phase"
                    className="flex w-full items-center gap-2 border-l-2 border-transparent px-3 py-1.5 text-left text-sm text-text-secondary/40 cursor-not-allowed"
                  >
                    <span className="truncate">{label}</span>
                    <span className="ml-auto text-[10px]">soon</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}

      {mode === "outline" && (
        <ul className="mt-2">
          {headings.length === 0 && <EmptyRow text="No headings detected." />}
          {headings.map((h) => (
            <li key={h.document_order}>
              <NavRow
                label={h.text || `(untitled H${h.level})`}
                isActive={isSelected("heading", h.document_order)}
                indentRem={(h.level - 1) * 0.75}
                onClick={() => selectObject("heading", h.document_order, h.page_number, h.bbox, h.source_line)}
              />
            </li>
          ))}
        </ul>
      )}

      {mode === "corrections" && (
        <ul className="mt-2">
          {(() => {
            const pending = corrections.filter((c) =>
              ["proposed", "pending_review"].includes(c.status)
            );
            if (pending.length === 0) return <EmptyRow text="No pending corrections." />;
            return pending.map((c) => (
              <li key={c.correction_id}>
                <NavRow
                  label={`${c.object_type}: ${c.problem}`}
                  isActive={isSelected("correction", c.correction_id)}
                  onClick={() => {
                    select("correction", c.correction_id);
                    onSelectSpecialView("");
                  }}
                />
              </li>
            ));
          })()}
        </ul>
      )}

      {mode === "validation" && (
        <ul className="mt-2">
          {state.validationIssues.length === 0 && <EmptyRow text="No validation issues." />}
          {state.validationIssues.map((issue) => (
            <li key={issue.issue_id}>
              <NavRow
                label={`${issue.rule_id}: ${issue.message}`}
                isActive={isSelected("validation-issue", issue.issue_id)}
                onClick={() => {
                  select("validation-issue", issue.issue_id);
                  onSelectSpecialView("");
                  if (issue.page_number !== null) jumpToObject(issue.page_number, null);
                }}
              />
            </li>
          ))}
        </ul>
      )}

      {mode === "search" && (
        <SearchMode
          headings={headings}
          tables={tables}
          images={images}
          footnotes={footnotes}
          lists={lists}
          callouts={callouts}
          isSelected={isSelected}
          onSelectObject={selectObject}
        />
      )}
    </nav>
  );
}

function EmptyRow({ text }: { text: string }) {
  return <p className="px-3 py-2 text-sm text-text-secondary">{text}</p>;
}

function ExpandableCategory({
  label,
  count,
  defaultOpen = false,
  children,
}: {
  label: string;
  count: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm font-medium text-text-primary hover:bg-hover-row"
      >
        <span className="flex items-center gap-1.5">
          <svg
            className={`h-3 w-3 shrink-0 transition-transform ${open ? "rotate-90" : ""}`}
            viewBox="0 0 12 12"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M4 2.5 8.5 6 4 9.5" />
          </svg>
          {label}
        </span>
        <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-surface-elevated px-1 font-mono text-[10px] text-text-secondary">
          {count}
        </span>
      </button>
      {open && <div className="pb-1">{children}</div>}
    </div>
  );
}

interface SearchableResult {
  key: string;
  objectType: SelectableObjectType;
  objectId: string | number;
  label: string;
  pageNumber: number;
  bbox: BoundingBox | null;
  sourceLine?: number | null;
}

function SearchMode({
  headings,
  tables,
  images,
  footnotes,
  lists,
  callouts,
  isSelected,
  onSelectObject,
}: {
  headings: ReturnType<typeof selectHeadings>;
  tables: ReturnType<typeof selectTables>;
  images: ReturnType<typeof selectImages>;
  footnotes: ReturnType<typeof selectFootnotes>;
  lists: ReturnType<typeof selectLists>;
  callouts: ReturnType<typeof selectCallouts>;
  isSelected: (type: SelectableObjectType, id: string | number) => boolean;
  onSelectObject: (
    type: SelectableObjectType,
    id: string | number,
    pageNumber: number,
    bbox: BoundingBox | null,
    sourceLine?: number | null
  ) => void;
}) {
  const [query, setQuery] = useState("");

  const results = useMemo<SearchableResult[]>(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    const out: SearchableResult[] = [];
    for (const h of headings) {
      if (h.text.toLowerCase().includes(q)) {
        out.push({ key: `h-${h.document_order}`, objectType: "heading", objectId: h.document_order, label: `Heading: ${h.text}`, pageNumber: h.page_number, bbox: h.bbox, sourceLine: h.source_line });
      }
    }
    for (const t of tables) {
      if (t.caption?.toLowerCase().includes(q)) {
        out.push({ key: `t-${t.table_id}`, objectType: "table", objectId: t.table_id, label: `Table: ${t.caption}`, pageNumber: t.page_number, bbox: t.bbox, sourceLine: t.source_line });
      }
    }
    for (const img of images) {
      const text = img.figure?.caption ?? img.figure?.alt_text ?? "";
      if (text.toLowerCase().includes(q)) {
        out.push({ key: `i-${img.image_id}`, objectType: "image", objectId: img.image_id, label: `Figure: ${text}`, pageNumber: img.page_number, bbox: img.bbox });
      }
    }
    for (const note of footnotes) {
      if (note.body.toLowerCase().includes(q)) {
        const key = note.footnote_id ?? `${note.note_type}-${note.number}-${note.anchor_page_number}`;
        out.push({ key: `f-${key}`, objectType: "footnote", objectId: key, label: `Note: ${note.body}`, pageNumber: note.anchor_page_number, bbox: null });
      }
    }
    for (const list of lists) {
      const text = list.items.map((i) => i.text).join(" ");
      if (text.toLowerCase().includes(q)) {
        const key = list.id ?? `list-${list.page_number}-${list.document_order}`;
        out.push({ key: `l-${key}`, objectType: "list", objectId: key, label: `List: ${text.slice(0, 60)}`, pageNumber: list.page_number, bbox: list.bbox, sourceLine: list.source_line });
      }
    }
    for (const c of callouts) {
      if (c.label.toLowerCase().includes(q)) {
        const key = c.id ?? `callout-${c.page_number}-${c.document_order}`;
        out.push({ key: `c-${key}`, objectType: "callout", objectId: key, label: `Callout: ${c.label}`, pageNumber: c.page_number ?? 1, bbox: c.bbox, sourceLine: c.source_line });
      }
    }
    return out.slice(0, 50);
  }, [query, headings, tables, images, footnotes, lists, callouts]);

  return (
    <div className="mt-2">
      <div className="px-2">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search document text…"
          className="w-full rounded border border-border bg-surface-canvas px-2 py-1 text-sm text-text-primary placeholder:text-text-secondary/60 focus:border-accent focus:outline-none"
        />
      </div>
      <ul className="mt-2">
        {query.trim() && results.length === 0 && <EmptyRow text="No matches." />}
        {results.map((r) => (
          <li key={r.key}>
            <NavRow
              label={r.label}
              isActive={isSelected(r.objectType, r.objectId)}
              onClick={() => onSelectObject(r.objectType, r.objectId, r.pageNumber, r.bbox, r.sourceLine)}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}
