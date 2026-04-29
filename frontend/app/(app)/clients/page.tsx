import { headers } from "next/headers";
import Link from "next/link";
import { Card, CardEyebrow } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";
import { CreateClientButton } from "./create-client-button";

export const dynamic = "force-dynamic";

export default async function ClientsPage() {
  const cookie = (await headers()).get("cookie") ?? undefined;
  const clients = await api.listClients(cookie);

  return (
    <div>
      <PageHeader
        eyebrow="Talent base"
        title="Clients"
        description="Companies you recruit for. Add a client first, then create jobs under it."
        actions={<CreateClientButton />}
      />

      {clients.length === 0 ? (
        <Card className="p-10 text-center">
          <CardEyebrow>No clients yet</CardEyebrow>
          <p className="mt-3 text-sm text-[var(--muted-foreground)]">
            Add your first client to start logging open positions.
          </p>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {clients.map((c) => (
            <Link key={c.id} href={`/clients/${c.id}`}>
              <Card className="flex h-full flex-col p-5 transition-colors hover:bg-[var(--muted)]">
                <CardEyebrow>Client</CardEyebrow>
                <div className="mt-2 text-lg font-semibold tracking-tight">
                  {c.name}
                </div>
                {c.notes ? (
                  <p className="mt-2 line-clamp-2 text-sm text-[var(--muted-foreground)]">
                    {c.notes}
                  </p>
                ) : null}

                <div className="mt-auto grid grid-cols-3 gap-3 border-t border-[var(--border)] pt-4">
                  <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                      Jobs
                    </div>
                    <div className="mt-1 text-sm tabular-nums">
                      <span className="font-semibold">{c.jobs_open}</span>
                      <span className="text-[var(--muted-foreground)]">
                        {" "}/ {c.jobs_total}
                      </span>
                    </div>
                  </div>
                  <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                      Candidates
                    </div>
                    <div className="mt-1 text-sm font-semibold tabular-nums">
                      {c.candidates_total}
                    </div>
                  </div>
                  <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                      Last 7d
                    </div>
                    <div className="mt-1 text-sm tabular-nums">
                      {c.candidates_recent > 0 ? (
                        <span className="font-semibold text-emerald-600">
                          +{c.candidates_recent}
                        </span>
                      ) : (
                        <span className="text-[var(--muted-foreground)]">—</span>
                      )}
                    </div>
                  </div>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
