import { headers } from "next/headers";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Card, CardEyebrow } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { ApiError, api } from "@/lib/api";
import { Board } from "./board";

export const dynamic = "force-dynamic";

const STATUS_TONE: Record<string, string> = {
  open: "text-emerald-600",
  "on-hold": "text-amber-600",
  closed: "text-[var(--muted-foreground)]",
};

export default async function JobDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const cookie = (await headers()).get("cookie") ?? undefined;
  const jid = Number(id);

  let job;
  try {
    job = await api.getJob(jid, cookie);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }
  const [client, board] = await Promise.all([
    api.getClient(job.client_id, cookie),
    api.getBoard(jid, cookie),
  ]);

  const detail = (label: string, value: React.ReactNode) => (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--muted-foreground)]">
        {label}
      </div>
      <div className="mt-1 text-sm">{value ?? "—"}</div>
    </div>
  );

  const range = (a: string | null, b: string | null, suffix = "") => {
    if (!a && !b) return null;
    const sa = a ? Number(a).toLocaleString() : "?";
    const sb = b ? Number(b).toLocaleString() : "?";
    return `${sa}–${sb}${suffix}`;
  };

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow={
          <span>
            <Link href={`/clients/${client.id}`} className="hover:underline">
              {client.name}
            </Link>
            {" · Job"}
          </span>
        }
        title={job.title}
        actions={
          <span
            className={`font-mono text-[11px] uppercase tracking-[0.18em] ${
              STATUS_TONE[job.status] ?? ""
            }`}
          >
            {job.status}
          </span>
        }
      />

      <Card className="p-6">
        <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
          {detail("Location", job.location)}
          {detail("Experience", range(job.exp_min, job.exp_max, " yrs"))}
          {detail("CTC", range(job.ctc_min, job.ctc_max))}
          {detail("Created", new Date(job.created_at).toLocaleDateString())}
        </div>
        {job.jd_text ? (
          <div className="mt-8">
            <CardEyebrow>Job description</CardEyebrow>
            <div className="prose prose-sm mt-2 max-w-none whitespace-pre-wrap text-sm text-[var(--foreground)]">
              {job.jd_text}
            </div>
          </div>
        ) : null}
      </Card>

      <Board jobId={jid} initial={board} />
    </div>
  );
}
