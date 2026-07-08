import type { PageOcrInfo } from "@/lib/api";
import { ConfidenceBadge, Badge } from "./Badge";

const EXTRACTION_LABELS: Record<string, string> = {
  direct_text_extraction: "Direct extraction",
  ocr_pending: "Not yet OCR'd",
  docling: "Docling OCR",
  surya: "Surya OCR (fallback)",
};

export function OcrPageTable({ pages }: { pages: PageOcrInfo[] }) {
  if (pages.length === 0) {
    return <p className="text-sm text-text-secondary">No pages found.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="min-w-full divide-y divide-border text-sm">
        <thead className="bg-surface-panel">
          <tr>
            <th scope="col" className="px-4 py-2 text-left font-medium text-text-secondary">Page</th>
            <th scope="col" className="px-4 py-2 text-left font-medium text-text-secondary">Routing</th>
            <th scope="col" className="px-4 py-2 text-left font-medium text-text-secondary">Extraction method</th>
            <th scope="col" className="px-4 py-2 text-left font-medium text-text-secondary">OCR confidence</th>
            <th scope="col" className="px-4 py-2 text-left font-medium text-text-secondary">Has text</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border bg-surface-elevated">
          {pages.map((page) => (
            <tr key={page.page_number} className={page.ocr_confidence === "low" ? "bg-warning/10" : undefined}>
              <td className="px-4 py-2 text-text-primary">{page.page_number}</td>
              <td className="px-4 py-2 text-text-primary">
                {page.page_type === "ocr_required" ? (
                  <Badge tone="warning">OCR required</Badge>
                ) : page.page_type === "direct_text" ? (
                  <Badge tone="success">Direct text</Badge>
                ) : (
                  <Badge tone="neutral">Unknown</Badge>
                )}
              </td>
              <td className="px-4 py-2 text-text-primary">
                {page.extraction_method ? EXTRACTION_LABELS[page.extraction_method] ?? page.extraction_method : "—"}
              </td>
              <td className="px-4 py-2">
                <ConfidenceBadge confidence={page.ocr_confidence} />
              </td>
              <td className="px-4 py-2 text-text-primary">{page.has_text ? "Yes" : "No"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
