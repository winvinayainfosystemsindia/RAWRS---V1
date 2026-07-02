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
    return <p className="text-sm text-gray-600">No pages found.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th scope="col" className="px-4 py-2 text-left font-medium text-gray-600">Page</th>
            <th scope="col" className="px-4 py-2 text-left font-medium text-gray-600">Routing</th>
            <th scope="col" className="px-4 py-2 text-left font-medium text-gray-600">Extraction method</th>
            <th scope="col" className="px-4 py-2 text-left font-medium text-gray-600">OCR confidence</th>
            <th scope="col" className="px-4 py-2 text-left font-medium text-gray-600">Has text</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 bg-white">
          {pages.map((page) => (
            <tr key={page.page_number} className={page.ocr_confidence === "low" ? "bg-amber-50" : undefined}>
              <td className="px-4 py-2 text-gray-700">{page.page_number}</td>
              <td className="px-4 py-2 text-gray-700">
                {page.page_type === "ocr_required" ? (
                  <Badge tone="warning">OCR required</Badge>
                ) : page.page_type === "direct_text" ? (
                  <Badge tone="success">Direct text</Badge>
                ) : (
                  <Badge tone="neutral">Unknown</Badge>
                )}
              </td>
              <td className="px-4 py-2 text-gray-700">
                {page.extraction_method ? EXTRACTION_LABELS[page.extraction_method] ?? page.extraction_method : "—"}
              </td>
              <td className="px-4 py-2">
                <ConfidenceBadge confidence={page.ocr_confidence} />
              </td>
              <td className="px-4 py-2 text-gray-700">{page.has_text ? "Yes" : "No"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
