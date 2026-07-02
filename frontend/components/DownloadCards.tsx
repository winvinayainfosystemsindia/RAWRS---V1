import { api, type JobSummary } from "@/lib/api";

interface DownloadCardProps {
  href: string | undefined;
  label: string;
  description: string;
  available: boolean;
}

function DownloadCard({ href, label, description, available }: DownloadCardProps) {
  return (
    <div
      className={`flex flex-col justify-between gap-3 rounded-lg border p-4 ${
        available ? "border-gray-200 bg-white" : "border-gray-100 bg-gray-50"
      }`}
    >
      <div>
        <p className={`text-sm font-semibold ${available ? "text-gray-900" : "text-gray-400"}`}>
          {label}
        </p>
        <p className={`mt-0.5 text-xs ${available ? "text-gray-500" : "text-gray-400"}`}>
          {description}
        </p>
      </div>
      {available && href ? (
        <a
          href={href}
          download
          className="inline-flex items-center gap-1.5 rounded-md bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 w-fit"
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
          </svg>
          Download
        </a>
      ) : (
        <span className="text-xs text-gray-400 italic">Not available</span>
      )}
    </div>
  );
}

export function DownloadCards({ job }: { job: JobSummary }) {
  const cards: DownloadCardProps[] = [
    {
      label: "Accessible DOCX",
      description: "Native OOXML with footnotes, headings, and accessibility metadata",
      available: job.docx_available,
      href: job.docx_available ? api.downloadUrl(job.job_id, "docx") : undefined,
    },
    {
      label: "Accessible Markdown (.md)",
      description: "Structured Markdown with verified headings and footnote references",
      available: job.markdown_available,
      href: job.markdown_available ? api.downloadUrl(job.job_id, "markdown") : undefined,
    },
    {
      label: "Accessibility Report (.md)",
      description: "Full report: verification summary, repairs, warnings, and manual review items",
      available: false,
      href: undefined,
    },
    {
      label: "Validation Report (.json)",
      description: "Machine-readable validation issues with severity, rule ID, and suggested actions",
      available: job.report_available,
      href: job.report_available ? api.downloadUrl(job.job_id, "report") : undefined,
    },
  ];

  return (
    <section aria-labelledby="downloads-heading">
      <h2 id="downloads-heading" className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
        Downloads
      </h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => (
          <DownloadCard key={card.label} {...card} />
        ))}
      </div>
    </section>
  );
}
