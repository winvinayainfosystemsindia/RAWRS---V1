"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type LearningInsights, type LearningRule } from "@/lib/api";

// What RAWRS has learned from remediators (docs/LEARNING_LOOP.md): their
// verdicts on its proposals, the edits they made in the workspace, and the
// changes they made in Word after export. Everything is advice for a person;
// nothing on this page changes what the pipeline does.

const RECOMMENDATION_LABEL: Record<string, string> = {
  candidate_auto_apply: "Candidate to auto-apply",
  approaching_auto_apply: "Approaching auto-apply",
  candidate_retire: "Candidate to retire",
  improve_proposed_value: "Improve the proposed value",
  revisit_auto_apply: "Revisit auto-apply",
  auto_apply_holding: "Auto-apply holding",
  collect_more: "Collecting judgements",
  keep_asking: "Keep asking",
};

const SECTION = "rounded-xl border border-border bg-surface-panel p-6";
const H2 = "mb-3 text-sm font-bold text-text-primary";
const TH = "px-3 py-2 text-left text-xs font-semibold text-text-secondary";
const TD = "px-3 py-2 align-top text-sm text-text-primary";

function percent(share: number | null): string {
  return share === null ? "—" : `${Math.round(share * 100)}%`;
}

function Precision({ rule }: { rule: LearningRule }) {
  if (rule.precision === null) return <span className="text-text-secondary">—</span>;
  return (
    <span>
      {percent(rule.precision)}{" "}
      <span className="text-xs text-text-secondary">
        ({percent(rule.precision_low)}–{percent(rule.precision_high)})
      </span>
    </span>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-text-secondary">{children}</p>;
}

export default function InsightsPage() {
  const [insights, setInsights] = useState<LearningInsights | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getLearningInsights()
      .then((result) => {
        if (!cancelled) setInsights(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load insights.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const totals = insights?.decisions.totals;
  const after = insights?.after_export;

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-end justify-between gap-4 pt-2">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-text-primary">Insights</h1>
          <p className="mt-1.5 text-sm text-text-secondary">
            What remediators&apos; decisions and edits say RAWRS should do better. Advice only — nothing here changes
            the pipeline.
          </p>
        </div>
        <a
          href={api.learningDatasetUrl()}
          className="rounded-lg border border-border bg-surface-canvas px-4 py-2 text-sm font-semibold text-text-primary hover:bg-hover-row focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          Download learning dataset (JSONL)
        </a>
      </section>

      {error && (
        <p role="alert" className="rounded border border-danger/30 bg-danger/5 p-3 text-sm text-danger">
          {error}
        </p>
      )}
      {!insights && !error && (
        <p role="status" className="text-sm text-text-secondary">
          Reading every document&apos;s decisions…
        </p>
      )}

      {insights && totals && after && (
        <>
          <p className="text-sm text-text-secondary" aria-live="polite">
            {totals.documents} documents · {totals.proposals} RAWRS proposals · {totals.human_edits} reviewer edits ·{" "}
            {after.documents} finished DOCX compared
            {after.mean_kept_share !== null && ` (on average ${percent(after.mean_kept_share)} kept unchanged)`}
          </p>

          <section aria-labelledby="insights-priorities" className={SECTION}>
            <h2 id="insights-priorities" className={H2}>
              What to improve next
            </h2>
            {insights.priorities.length > 0 ? (
              <ol className="list-decimal space-y-2 pl-5 text-sm text-text-primary">
                {insights.priorities.map((priority, index) => (
                  <li key={index}>{priority.message}</li>
                ))}
              </ol>
            ) : (
              <Empty>Nothing yet. Review documents and upload finished DOCX files to teach RAWRS.</Empty>
            )}
          </section>

          <section aria-labelledby="insights-after-export" className={SECTION}>
            <h2 id="insights-after-export" className={H2}>
              Changes made in Word after export
            </h2>
            {after.categories.length > 0 ? (
              <table className="w-full">
                <caption className="sr-only">Changes made after export, by kind</caption>
                <thead>
                  <tr className="border-b border-border">
                    <th scope="col" className={TH}>Change</th>
                    <th scope="col" className={TH}>Times</th>
                    <th scope="col" className={TH}>Documents</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {after.categories.map((c) => (
                    <tr key={`${c.category}-${c.object_type}`}>
                      <td className={TD}>Remediators {c.phrase}</td>
                      <td className={TD}>{c.count}</td>
                      <td className={TD}>{c.documents}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <Empty>No finished DOCX files have been uploaded yet (Export Center → Finished in Word).</Empty>
            )}
            {after.word_substitutions.length > 0 && (
              <>
                <h3 className="mb-2 mt-4 text-xs font-semibold text-text-secondary">Repeated word fixes</h3>
                <ul className="flex flex-wrap gap-2">
                  {after.word_substitutions.map((s) => (
                    <li key={`${s.from}→${s.to}`} className="rounded bg-surface-elevated px-2 py-1 text-xs text-text-primary">
                      <del>{s.from}</del> → <ins className="no-underline">{s.to}</ins> × {s.count}
                    </li>
                  ))}
                </ul>
              </>
            )}
            {after.checklist_fixed_by_remediators.length > 0 && (
              <>
                <h3 className="mb-2 mt-4 text-xs font-semibold text-text-secondary">Checklist items fixed by hand</h3>
                <ul className="space-y-1 text-sm text-text-primary">
                  {after.checklist_fixed_by_remediators.map((item) => (
                    <li key={item.item_id}>
                      {item.requirement} <span className="text-xs text-text-secondary">({item.documents} documents)</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>

          <section aria-labelledby="insights-rules" className={SECTION}>
            <h2 id="insights-rules" className={H2}>
              How reviewers judged RAWRS&apos;s proposals
            </h2>
            {insights.decisions.rules.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <caption className="sr-only">Reviewer verdicts per proposal rule</caption>
                  <thead>
                    <tr className="border-b border-border">
                      <th scope="col" className={TH}>Rule</th>
                      <th scope="col" className={TH}>Judged</th>
                      <th scope="col" className={TH}>Accepted (95% range)</th>
                      <th scope="col" className={TH}>Value rewritten</th>
                      <th scope="col" className={TH}>Auto-applied / undone</th>
                      <th scope="col" className={TH}>Recommendation</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {insights.decisions.rules.map((rule) => (
                      <tr key={`${rule.object_type}-${rule.reason_code}`}>
                        <td className={TD}>
                          <span className="font-mono text-xs">{rule.reason_code}</span>
                          <span className="block text-xs text-text-secondary">{rule.object_type}</span>
                        </td>
                        <td className={TD}>{rule.decided}</td>
                        <td className={TD}>
                          <Precision rule={rule} />
                        </td>
                        <td className={TD}>{percent(rule.edit_share)}</td>
                        <td className={TD}>
                          {rule.auto_applied} / {rule.counts.auto_undone ?? 0}
                        </td>
                        <td className={TD}>
                          {RECOMMENDATION_LABEL[rule.recommendation] ?? rule.recommendation}
                          <span className="block text-xs text-text-secondary">{rule.rationale}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty>No proposals have been judged yet.</Empty>
            )}
          </section>

          <section aria-labelledby="insights-human-edits" className={SECTION}>
            <h2 id="insights-human-edits" className={H2}>
              Edits reviewers made that RAWRS never proposed
            </h2>
            {insights.decisions.human_edits.length > 0 ? (
              <ul className="space-y-3">
                {insights.decisions.human_edits.map((edit) => (
                  <li key={`${edit.object_type}-${edit.reason_code}`} className="text-sm text-text-primary">
                    <span className="font-mono text-xs">{edit.reason_code}</span> on {edit.object_type}: {edit.count} times
                    in {edit.documents} documents
                    {edit.top_changes.length > 0 && (
                      <span className="block text-xs text-text-secondary">
                        Most often: {edit.top_changes.map((c) => `${c.from} → ${c.to} (${c.count})`).join(", ")}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>No reviewer-originated edits yet.</Empty>
            )}
          </section>

          {insights.reviewed_documents.length > 0 && (
            <section aria-labelledby="insights-reviewed" className={SECTION}>
              <h2 id="insights-reviewed" className={H2}>
                Finished documents compared
              </h2>
              <ul className="divide-y divide-border">
                {insights.reviewed_documents.map((doc) => (
                  <li key={doc.job_id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                    <Link
                      href={`/documents/${doc.job_id}`}
                      className="rounded text-text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                    >
                      {doc.filename || doc.job_id}
                    </Link>
                    <span className="text-xs text-text-secondary">
                      {percent(doc.kept_share)} kept · {doc.edits} edits
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}
