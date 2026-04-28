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
              <Card className="h-full p-5 transition-colors hover:bg-[var(--muted)]">
                <CardEyebrow>Client</CardEyebrow>
                <div className="mt-2 text-lg font-semibold tracking-tight">
                  {c.name}
                </div>
                {c.notes ? (
                  <p className="mt-2 line-clamp-2 text-sm text-[var(--muted-foreground)]">
                    {c.notes}
                  </p>
                ) : null}
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
