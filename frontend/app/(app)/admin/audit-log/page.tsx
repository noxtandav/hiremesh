import { headers } from "next/headers";
import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";
import { AuditClient } from "./audit-client";

export const dynamic = "force-dynamic";

export default async function AuditLogPage() {
  const cookie = (await headers()).get("cookie") ?? undefined;
  const initial = await api.listAudit({ limit: 100 }, cookie);
  return (
    <div>
      <PageHeader
        eyebrow="Admin"
        title="Audit log"
        description="Recent operational events. Best-effort logging — failures here don't fail the underlying request."
      />
      <AuditClient initial={initial} />
    </div>
  );
}
