import { headers } from "next/headers";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Card, CardEyebrow } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { ApiError, api } from "@/lib/api";
import { CreateJobButton } from "./create-job-button";

export const dynamic = "force-dynamic";

const STATUS_TONE: Record<string, string> = {
  open: "text-emerald-600",
  "on-hold": "text-amber-600",
  closed: "text-[var(--muted-foreground)]",
};

export default async function ClientDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const cookie = (await headers()).get("cookie") ?? undefined;
  const cid = Number(id);

  let client, me;
  try {
    [client, me] = await Promise.all([
      api.getClient(cid, cookie),
      api.me(cookie),
    ]);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }
  const jobs = await api.listJobs({ client_id: cid }, cookie);
  const canManage = me.role === "admin" || me.role === "recruiter";

  return (
    <div>
      <PageHeader
        eyebrow="Client"
        title={client.name}
        description={client.notes ?? undefined}
        actions={canManage ? <CreateJobButton clientId={cid} /> : null}
      />

      <section>
        <h2 className="mb-3 font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--muted-foreground)]">
          Jobs · {jobs.length}
        </h2>
        {jobs.length === 0 ? (
          <Card className="p-10 text-center">
            <p className="text-sm text-[var(--muted-foreground)]">
              No jobs yet for {client.name}. Add one to get started.
            </p>
          </Card>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {jobs.map((j) => (
              <Link key={j.id} href={`/jobs/${j.id}`}>
                <Card className="flex h-full flex-col p-5 transition-colors hover:bg-[var(--muted)]">
                  <div className="flex items-start justify-between gap-3">
                    <CardEyebrow>Job</CardEyebrow>
                    <span
                      className={`font-mono text-[10px] uppercase tracking-[0.18em] ${
                        STATUS_TONE[j.status] ?? ""
                      }`}
                    >
                      {j.status}
                    </span>
                  </div>
                  <div className="mt-2 text-base font-semibold tracking-tight">
                    {j.title}
                  </div>
                  {(j.location || j.exp_min) ? (
                    <p className="mt-1 line-clamp-2 text-xs text-[var(--muted-foreground)]">
                      {[
                        j.location,
                        j.exp_min && `${j.exp_min}–${j.exp_max} yrs`,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  ) : null}

                  <div className="mt-auto grid grid-cols-3 gap-3 border-t border-[var(--border)] pt-4">
                    <div>
                      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                        Candidates
                      </div>
                      <div className="mt-1 text-sm font-semibold tabular-nums">
                        {j.candidates_total}
                      </div>
                    </div>
                    <div>
                      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                        New 7d
                      </div>
                      <div className="mt-1 text-sm tabular-nums">
                        {j.candidates_recent > 0 ? (
                          <span className="font-semibold text-emerald-600">
                            +{j.candidates_recent}
                          </span>
                        ) : (
                          <span className="text-[var(--muted-foreground)]">
                            —
                          </span>
                        )}
                      </div>
                    </div>
                    <div>
                      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                        Moves 7d
                      </div>
                      <div className="mt-1 text-sm tabular-nums">
                        {j.moves_recent > 0 ? (
                          <span className="font-semibold">{j.moves_recent}</span>
                        ) : (
                          <span className="text-[var(--muted-foreground)]">
                            —
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
