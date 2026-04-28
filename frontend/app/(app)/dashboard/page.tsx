import { headers } from "next/headers";
import Link from "next/link";
import { Card, CardEyebrow } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const cookie = (await headers()).get("cookie") ?? undefined;
  const [clients, candidates, jobs] = await Promise.all([
    api.listClients(cookie),
    api.listCandidates({}, cookie),
    api.listJobs({}, cookie),
  ]);
  const openJobs = jobs.filter((j) => j.status === "open").length;

  const stats: { label: string; value: string; href: string }[] = [
    { label: "Clients", value: String(clients.length), href: "/clients" },
    { label: "Open jobs", value: String(openJobs), href: "/clients" },
    {
      label: "Candidates in pool",
      value: String(candidates.length),
      href: "/candidates",
    },
  ];

  return (
    <div>
      <PageHeader
        eyebrow="Overview"
        title="Dashboard"
        description="A read-only summary for now. Search, kanban and AI Q&A arrive in later milestones."
      />

      <section className="grid gap-4 sm:grid-cols-3">
        {stats.map((s) => (
          <Link key={s.label} href={s.href}>
            <Card className="h-full p-5 transition-colors hover:bg-[var(--muted)]">
              <CardEyebrow>{s.label}</CardEyebrow>
              <div className="mt-2 text-3xl font-semibold tabular-nums">
                {s.value}
              </div>
            </Card>
          </Link>
        ))}
      </section>
    </div>
  );
}
