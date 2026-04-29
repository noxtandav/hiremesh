import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { Card, CardEyebrow } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { ApiError, api } from "@/lib/api";
import { AskCandidate } from "./ask";
import { Notes } from "./notes";
import { ResumePreview } from "./resume-preview";
import { Resumes } from "./resumes";
import { DeleteCandidateButton } from "./delete-candidate-button";

export const dynamic = "force-dynamic";

export default async function CandidateDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const cookie = (await headers()).get("cookie") ?? undefined;
  const cid = Number(id);

  let candidate, notes, resumes, duplicates;
  try {
    [candidate, notes, resumes, duplicates] = await Promise.all([
      api.getCandidate(cid, cookie),
      api.listNotes(cid, cookie),
      api.listResumes(cid, cookie),
      api.listCandidateDuplicates(cid, cookie),
    ]);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  const detail = (label: string, value: React.ReactNode) => (
    <div className="min-w-0">
      <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--muted-foreground)]">
        {label}
      </div>
      <div className="mt-1 text-sm [overflow-wrap:anywhere]">
        {value ?? "—"}
      </div>
    </div>
  );

  return (
    <div>
      <PageHeader
        eyebrow="Candidate"
        title={candidate.full_name}
        description={
          [candidate.current_title, candidate.current_company]
            .filter(Boolean)
            .join(" at ") || undefined
        }
        actions={<DeleteCandidateButton id={cid} />}
      />

      {duplicates.length > 0 ? (
        <div className="mb-6 rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm">
          <div className="font-medium">
            Possible duplicate of {duplicates.length} other{" "}
            {duplicates.length === 1 ? "candidate" : "candidates"}
          </div>
          <div className="mt-1 text-[var(--muted-foreground)]">
            Matched by email or phone — check before keeping both.
          </div>
          <ul className="mt-2 flex flex-wrap gap-2">
            {duplicates.map((d) => (
              <li key={d.id}>
                <a
                  href={`/candidates/${d.id}`}
                  className="rounded-md border border-amber-500/40 bg-[var(--card)] px-2 py-1 text-xs hover:bg-[var(--accent)]"
                >
                  {d.full_name}
                  {d.email ? (
                    <span className="ml-1 font-mono text-[10px] text-[var(--muted-foreground)]">
                      {d.email}
                    </span>
                  ) : null}
                </a>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="mb-6">
        <AskCandidate candidateId={cid} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div className="space-y-6 min-w-0">
        <Card className="p-6">
          <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
            {detail("Email", candidate.email)}
            {detail("Phone", candidate.phone)}
            {detail("Location", candidate.location)}
            {detail("Total exp", candidate.total_exp_years && `${candidate.total_exp_years} yrs`)}
            {detail("Current CTC", candidate.current_ctc && Number(candidate.current_ctc).toLocaleString("en-US"))}
            {detail("Expected CTC", candidate.expected_ctc && Number(candidate.expected_ctc).toLocaleString("en-US"))}
            {detail(
              "Notice",
              candidate.notice_period_days != null
                ? `${candidate.notice_period_days} days`
                : null,
            )}
            {detail(
              "Added",
              <>
                {candidate.created_at.slice(0, 10)}
                {candidate.created_by_name ? (
                  <span className="text-[var(--muted-foreground)]">
                    {" · by "}
                    {candidate.created_by_name}
                  </span>
                ) : null}
              </>,
            )}
          </div>

          {candidate.skills.length ? (
            <div className="mt-8">
              <CardEyebrow>Skills</CardEyebrow>
              <div className="mt-3 flex flex-wrap gap-2">
                {candidate.skills.map((s) => (
                  <span
                    key={s}
                    className="rounded-full border border-[var(--border)] px-3 py-1 text-xs"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          {candidate.summary ? (
            <div className="mt-8">
              <CardEyebrow>Summary</CardEyebrow>
              <p className="mt-2 whitespace-pre-wrap text-sm [overflow-wrap:anywhere]">
                {candidate.summary}
              </p>
            </div>
          ) : null}
        </Card>

        <ResumePreview resumes={resumes} />
        </div>

        <div className="space-y-6 min-w-0">
          <Resumes candidateId={cid} initial={resumes} />
          <Notes candidateId={cid} initial={notes} />
        </div>
      </div>
    </div>
  );
}
