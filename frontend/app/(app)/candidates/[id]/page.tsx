import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { Card, CardEyebrow } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { ApiError, api } from "@/lib/api";
import { AskCandidate } from "./ask";
import { Notes } from "./notes";
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

  let candidate, notes, resumes;
  try {
    [candidate, notes, resumes] = await Promise.all([
      api.getCandidate(cid, cookie),
      api.listNotes(cid, cookie),
      api.listResumes(cid, cookie),
    ]);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  const detail = (label: string, value: React.ReactNode) => (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--muted-foreground)]">
        {label}
      </div>
      <div className="mt-1 text-sm">{value ?? "—"}</div>
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

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <Card className="p-6">
          <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
            {detail("Email", candidate.email)}
            {detail("Phone", candidate.phone)}
            {detail("Location", candidate.location)}
            {detail("Total exp", candidate.total_exp_years && `${candidate.total_exp_years} yrs`)}
            {detail("Current CTC", candidate.current_ctc && Number(candidate.current_ctc).toLocaleString())}
            {detail("Expected CTC", candidate.expected_ctc && Number(candidate.expected_ctc).toLocaleString())}
            {detail(
              "Notice",
              candidate.notice_period_days != null
                ? `${candidate.notice_period_days} days`
                : null,
            )}
            {detail("Added", new Date(candidate.created_at).toLocaleDateString())}
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
              <p className="mt-2 whitespace-pre-wrap text-sm">{candidate.summary}</p>
            </div>
          ) : null}
        </Card>

        <div className="space-y-6">
          <AskCandidate candidateId={cid} />
          <Resumes candidateId={cid} initial={resumes} />
          <Notes candidateId={cid} initial={notes} />
        </div>
      </div>
    </div>
  );
}
