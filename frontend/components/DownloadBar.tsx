import { api, type JobSummary } from "@/lib/api";

export function DownloadBar({ job }: { job: JobSummary }) {
  const items: { kind: "markdown" | "docx" | "report"; label: string; available: boolean }[] = [
    { kind: "markdown", label: "Markdown (.md)", available: job.markdown_available },
    { kind: "docx", label: "Accessible DOCX (.docx)", available: job.docx_available },
    { kind: "report", label: "Validation report (.json)", available: job.report_available },
  ];

  return (
    <div className="flex flex-wrap gap-2 rounded-lg border border-gray-200 bg-gray-50 p-3">
      <span className="self-center pr-2 text-sm font-medium text-gray-700">Download:</span>
      {items.map((item) => (
        <a
          key={item.kind}
          href={item.available ? api.downloadUrl(job.job_id, item.kind) : undefined}
          aria-disabled={!item.available}
          className={`rounded-md px-3 py-1.5 text-sm font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
            item.available
              ? "bg-white text-blue-700 ring-1 ring-inset ring-blue-300 hover:bg-blue-50"
              : "cursor-not-allowed bg-gray-100 text-gray-400 ring-1 ring-inset ring-gray-200"
          }`}
        >
          {item.label}
        </a>
      ))}
    </div>
  );
}
