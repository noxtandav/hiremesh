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

  let client;
  try {
    client = await api.getClient(cid, cookie);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }
  const jobs = await api.listJobs({ client_id: cid }, cookie);

  return (
    <div>
      <PageHeader
        eyebrow="Client"
        title={client.name}
        description={client.notes ?? undefined}
        actions={<CreateJobButton clientId={cid} />}
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
          <div className="divide-y divide-[var(--border)] rounded-lg border border-[var(--border)] bg-[var(--card)]">
            {jobs.map((j) => (
              <Link
                key={j.id}
                href={`/jobs/${j.id}`}
                className="flex items-center justify-between gap-6 px-5 py-4 transition-colors hover:bg-[var(--muted)]"
              >
                <div className="min-w-0">
                  <div className="font-medium tracking-tight">{j.title}</div>
                  <div className="mt-1 text-xs text-[var(--muted-foreground)]">
                    {[j.location, j.exp_min && `${j.exp_min}–${j.exp_max} yrs`]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                </div>
                <span
                  className={`font-mono text-[10px] uppercase tracking-[0.18em] ${
                    STATUS_TONE[j.status] ?? ""
                  }`}
                >
                  {j.status}
                </span>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
