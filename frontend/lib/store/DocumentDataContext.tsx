"use client";

import { createContext, useContext, useMemo, useReducer, type ReactNode } from "react";
import type {
  AiStatus,
  CalloutItem,
  CorrectionItem,
  FootnoteItem,
  HeadingItem,
  ImageItem,
  JobSummary,
  ListItem,
  MetadataItem,
  PageLabel,
  PageLabelSection,
  PageOcrInfo,
  PageReadingOrder,
  ReadinessReport,
  TableItem,
  ValidationIssue,
} from "@/lib/api";

// Synthetic keys for objects whose id can be null (pre-FEATURE_016D documents).
export function footnoteKey(note: FootnoteItem): string {
  return note.footnote_id ?? `${note.note_type}-${note.number}-${note.anchor_page_number}`;
}
export function listKey(list: ListItem): string {
  return list.id ?? `list-${list.page_number}-${list.document_order}`;
}
export function calloutKey(callout: CalloutItem): string {
  return callout.id ?? `callout-${callout.page_number}-${callout.document_order}`;
}

export interface DocumentEntities {
  job: JobSummary | null;
  notFound: boolean;
  aiStatus: AiStatus | null;
  headingsById: Record<number, HeadingItem>;
  tablesById: Record<string, TableItem>;
  imagesById: Record<string, ImageItem>;
  footnotesById: Record<string, FootnoteItem>;
  listsById: Record<string, ListItem>;
  calloutsById: Record<string, CalloutItem>;
  correctionsById: Record<string, CorrectionItem>;
  pageLabelsByPage: Record<number, PageLabel>;
  pageLabelSections: PageLabelSection[];
  readingOrderByPage: Record<number, PageReadingOrder>;
  validationIssues: ValidationIssue[];
  metadata: MetadataItem | null;
  pages: PageOcrInfo[];
  readiness: ReadinessReport | null;
  markdown: string;
}

const initialState: DocumentEntities = {
  job: null,
  notFound: false,
  aiStatus: null,
  headingsById: {},
  tablesById: {},
  imagesById: {},
  footnotesById: {},
  listsById: {},
  calloutsById: {},
  correctionsById: {},
  pageLabelsByPage: {},
  pageLabelSections: [],
  readingOrderByPage: {},
  validationIssues: [],
  metadata: null,
  pages: [],
  readiness: null,
  markdown: "",
};

export type DocumentAction =
  | { type: "SET_JOB"; job: JobSummary }
  | { type: "SET_NOT_FOUND" }
  | { type: "SET_AI_STATUS"; aiStatus: AiStatus | null }
  | {
      type: "LOAD_RESULTS";
      payload: {
        headings: HeadingItem[];
        tables: TableItem[];
        images: ImageItem[];
        footnotes: FootnoteItem[];
        lists: ListItem[];
        callouts: CalloutItem[];
        corrections: CorrectionItem[];
        pageLabels: PageLabel[];
        pageLabelSections: PageLabelSection[];
        readingOrder: PageReadingOrder[];
        validationIssues: ValidationIssue[];
        metadata: MetadataItem | null;
        pages: PageOcrInfo[];
        readiness: ReadinessReport | null;
        markdown: string;
      };
    }
  | { type: "UPDATE_HEADING"; heading: HeadingItem }
  | { type: "REPLACE_HEADINGS"; headings: HeadingItem[] }
  | { type: "UPDATE_TABLE"; table: TableItem }
  | { type: "REPLACE_TABLES"; tables: TableItem[] }
  | { type: "REMOVE_TABLE"; tableId: string }
  | { type: "UPDATE_IMAGE"; image: ImageItem }
  | { type: "REPLACE_IMAGES"; images: ImageItem[] }
  | { type: "UPDATE_FOOTNOTE"; footnote: FootnoteItem }
  | { type: "REPLACE_FOOTNOTES"; footnotes: FootnoteItem[] }
  | { type: "UPDATE_CORRECTION"; correction: CorrectionItem }
  | { type: "REPLACE_CORRECTIONS"; corrections: CorrectionItem[] }
  | { type: "UPDATE_METADATA"; metadata: MetadataItem }
  | { type: "UPDATE_READING_ORDER_PAGE"; page: PageReadingOrder }
  | { type: "REPLACE_READING_ORDER"; pages: PageReadingOrder[] }
  | { type: "UPDATE_PAGE_LABELS"; pages: PageLabel[]; sections: PageLabelSection[] }
  | { type: "UPDATE_MARKDOWN"; markdown: string }
  | { type: "UPDATE_VALIDATION_ISSUE"; issue: ValidationIssue };

function keyBy<T>(items: T[], keyFn: (item: T) => string | number): Record<string | number, T> {
  const result: Record<string | number, T> = {};
  for (const item of items) result[keyFn(item)] = item;
  return result;
}

function reducer(state: DocumentEntities, action: DocumentAction): DocumentEntities {
  switch (action.type) {
    case "SET_JOB":
      return { ...state, job: action.job };
    case "SET_NOT_FOUND":
      return { ...state, notFound: true };
    case "SET_AI_STATUS":
      return { ...state, aiStatus: action.aiStatus };
    case "LOAD_RESULTS":
      return {
        ...state,
        headingsById: keyBy(action.payload.headings, (h) => h.document_order),
        tablesById: keyBy(action.payload.tables, (t) => t.table_id),
        imagesById: keyBy(action.payload.images, (i) => i.image_id),
        footnotesById: keyBy(action.payload.footnotes, footnoteKey),
        listsById: keyBy(action.payload.lists, listKey),
        calloutsById: keyBy(action.payload.callouts, calloutKey),
        correctionsById: keyBy(action.payload.corrections, (c) => c.correction_id),
        pageLabelsByPage: keyBy(action.payload.pageLabels, (p) => p.page_number),
        pageLabelSections: action.payload.pageLabelSections,
        readingOrderByPage: keyBy(action.payload.readingOrder, (p) => p.page_number),
        validationIssues: action.payload.validationIssues,
        metadata: action.payload.metadata,
        pages: action.payload.pages,
        readiness: action.payload.readiness,
        markdown: action.payload.markdown,
      };
    case "UPDATE_HEADING":
      return {
        ...state,
        headingsById: { ...state.headingsById, [action.heading.document_order]: action.heading },
      };
    case "REPLACE_HEADINGS":
      return { ...state, headingsById: keyBy(action.headings, (h) => h.document_order) };
    case "UPDATE_TABLE":
      return {
        ...state,
        tablesById: { ...state.tablesById, [action.table.table_id]: action.table },
      };
    case "REPLACE_TABLES":
      return { ...state, tablesById: keyBy(action.tables, (t) => t.table_id) };
    case "REMOVE_TABLE": {
      const { [action.tableId]: _removed, ...rest } = state.tablesById;
      return { ...state, tablesById: rest };
    }
    case "UPDATE_IMAGE":
      return {
        ...state,
        imagesById: { ...state.imagesById, [action.image.image_id]: action.image },
      };
    case "REPLACE_IMAGES":
      return { ...state, imagesById: keyBy(action.images, (i) => i.image_id) };
    case "UPDATE_FOOTNOTE":
      return {
        ...state,
        footnotesById: { ...state.footnotesById, [footnoteKey(action.footnote)]: action.footnote },
      };
    case "REPLACE_FOOTNOTES":
      return { ...state, footnotesById: keyBy(action.footnotes, footnoteKey) };
    case "UPDATE_CORRECTION":
      return {
        ...state,
        correctionsById: {
          ...state.correctionsById,
          [action.correction.correction_id]: action.correction,
        },
      };
    case "REPLACE_CORRECTIONS":
      return { ...state, correctionsById: keyBy(action.corrections, (c) => c.correction_id) };
    case "UPDATE_METADATA":
      return { ...state, metadata: action.metadata };
    case "UPDATE_READING_ORDER_PAGE":
      return {
        ...state,
        readingOrderByPage: { ...state.readingOrderByPage, [action.page.page_number]: action.page },
      };
    case "REPLACE_READING_ORDER":
      return { ...state, readingOrderByPage: keyBy(action.pages, (p) => p.page_number) };
    case "UPDATE_PAGE_LABELS":
      return {
        ...state,
        pageLabelsByPage: keyBy(action.pages, (p) => p.page_number),
        pageLabelSections: action.sections,
      };
    case "UPDATE_MARKDOWN":
      return { ...state, markdown: action.markdown };
    case "UPDATE_VALIDATION_ISSUE":
      return {
        ...state,
        validationIssues: state.validationIssues.map((i) =>
          i.issue_id === action.issue.issue_id ? action.issue : i
        ),
      };
    default:
      return state;
  }
}

interface DocumentDataContextValue {
  state: DocumentEntities;
  dispatch: React.Dispatch<DocumentAction>;
}

const DocumentDataContext = createContext<DocumentDataContextValue | null>(null);

export function DocumentDataProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const value = useMemo(() => ({ state, dispatch }), [state]);
  return <DocumentDataContext.Provider value={value}>{children}</DocumentDataContext.Provider>;
}

export function useDocumentData(): DocumentEntities {
  const ctx = useContext(DocumentDataContext);
  if (!ctx) throw new Error("useDocumentData must be used within DocumentDataProvider");
  return ctx.state;
}

export function useDocumentDispatch(): React.Dispatch<DocumentAction> {
  const ctx = useContext(DocumentDataContext);
  if (!ctx) throw new Error("useDocumentDispatch must be used within DocumentDataProvider");
  return ctx.dispatch;
}

// Array views over the normalized store, for components that still take a
// plain array prop (every existing Grid/Table/Panel component). Object.values
// on a numeric-keyed record returns ascending key order per the JS spec, so
// headingsById (keyed by document_order) comes back pre-sorted for free.
export const selectHeadings = (s: DocumentEntities): HeadingItem[] => Object.values(s.headingsById);
export const selectTables = (s: DocumentEntities): TableItem[] => Object.values(s.tablesById);
export const selectImages = (s: DocumentEntities): ImageItem[] => Object.values(s.imagesById);
export const selectFootnotes = (s: DocumentEntities): FootnoteItem[] => Object.values(s.footnotesById);
export const selectLists = (s: DocumentEntities): ListItem[] => Object.values(s.listsById);
export const selectCallouts = (s: DocumentEntities): CalloutItem[] => Object.values(s.calloutsById);
export const selectCorrections = (s: DocumentEntities): CorrectionItem[] => Object.values(s.correctionsById);
export const selectPageLabels = (s: DocumentEntities): PageLabel[] => Object.values(s.pageLabelsByPage);
export const selectReadingOrder = (s: DocumentEntities): PageReadingOrder[] =>
  Object.values(s.readingOrderByPage);
