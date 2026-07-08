import { useDocumentData, selectCorrections } from "./DocumentDataContext";

interface ObjectInspectorContext {
  corrections: ReturnType<typeof selectCorrections>;
  validationIssues: ReturnType<typeof useDocumentData>["validationIssues"];
  documentVersion: number | null;
}

// Every per-type detail panel calls this instead of receiving corrections/
// validation/version as threaded props — one source of truth, no
// duplicated state, per the approved store architecture.
export function useObjectInspectorContext(
  objectType: string,
  objectId: string | number | null,
  pageNumber?: number | null
): ObjectInspectorContext {
  const state = useDocumentData();
  const corrections = selectCorrections(state).filter(
    (c) => c.object_type === objectType && (objectId === null || c.object_id === String(objectId))
  );
  const validationIssues =
    pageNumber != null ? state.validationIssues.filter((v) => v.page_number === pageNumber) : [];
  return {
    corrections,
    validationIssues,
    documentVersion: state.job?.document_version ?? null,
  };
}
