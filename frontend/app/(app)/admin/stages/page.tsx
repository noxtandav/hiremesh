import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";
import { StagesEditor } from "./editor";

export const dynamic = "force-dynamic";

export default async function AdminStagesPage() {
  const cookie = (await headers()).get("cookie") ?? undefined;
  const me = await api.me(cookie);
  if (me.role !== "admin") redirect("/dashboard");

  const stages = await api.getStageTemplate(cookie);

  return (
    <div>
      <PageHeader
        eyebrow="Admin"
        title="Stage template"
        description="The system-wide pipeline. New jobs copy this list at creation. Edits do not retroactively change existing jobs."
      />
      <StagesEditor initial={stages} />
    </div>
  );
}
