import { headers } from "next/headers";
import { Card, CardEyebrow } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";
import { ResetEmbeddingsButton } from "./reset-embeddings-button";

export const dynamic = "force-dynamic";

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
}) {
  return (
    <Card className="p-5">
      <CardEyebrow>{label}</CardEyebrow>
      <div className="mt-2 text-3xl font-semibold tabular-nums">{value}</div>
      {hint ? (
        <p className="mt-1 text-xs text-[var(--muted-foreground)]">{hint}</p>
      ) : null}
    </Card>
  );
}

export default async function MetricsPage() {
  const cookie = (await headers()).get("cookie") ?? undefined;
  const m = await api.getMetrics(cookie);

  return (
    <div>
      <PageHeader
        eyebrow="Admin"
        title="Metrics"
        description="System counts and queue health. Refreshes on page load — no live polling."
      />

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Active candidates"
          value={m.candidates.active}
          hint={`${m.candidates.soft_deleted} soft-deleted`}
        />
        <Stat
          label="Embeddings"
          value={m.candidates.embedded}
          hint={`${(m.candidates.embedding_coverage * 100).toFixed(0)}% coverage`}
        />
        <Stat label="Clients" value={m.clients.total} />
        <Stat
          label="Jobs (open)"
          value={m.jobs.open}
          hint={`${m.jobs.on_hold} on-hold · ${m.jobs.closed} closed`}
        />

        <Stat label="Resumes parsed" value={m.resumes.done} />
        <Stat
          label="Resumes pending"
          value={m.resumes.pending + m.resumes.parsing}
          hint={`${m.resumes.failed} failed`}
        />
        <Stat
          label="Active users"
          value={m.users.active}
          hint={`${m.users.total} total`}
        />
        <Stat
          label="Celery queue"
          value={m.queue.celery_pending ?? "—"}
          hint="pending tasks"
        />
      </section>

      <section className="mt-8">
        <CardEyebrow>Configured models</CardEyebrow>
        <Card className="mt-3 p-5">
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                Parse
              </dt>
              <dd className="mt-1 font-mono text-xs">{m.models.parse}</dd>
            </div>
            <div>
              <dt className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                Embed
              </dt>
              <dd className="mt-1 font-mono text-xs">
                {m.models.embed}{" "}
                <span className="text-[var(--muted-foreground)]">
                  ({m.models.embed_dim}d)
                </span>
              </dd>
            </div>
            <div>
              <dt className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                Q&A
              </dt>
              <dd className="mt-1 font-mono text-xs">{m.models.qa}</dd>
            </div>
          </dl>
          <div className="mt-5 flex items-center gap-3">
            <ResetEmbeddingsButton />
          </div>
        </Card>
      </section>
    </div>
  );
}
