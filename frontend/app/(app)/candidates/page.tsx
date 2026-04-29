import { headers } from "next/headers";
import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";
import { BulkImportButton } from "./bulk-import-button";
import { CandidateSearch } from "./search-client";
import { CreateCandidateButton } from "./create-candidate-button";

export const dynamic = "force-dynamic";

export default async function CandidatesPage() {
  const cookie = (await headers()).get("cookie") ?? undefined;
  const [me, initial, stages] = await Promise.all([
    api.me(cookie),
    api.searchCandidates({ limit: 50 }, cookie),
    api.getStageTemplate(cookie),
  ]);

  return (
    <div>
      <PageHeader
        eyebrow="Talent base"
        title="Candidates"
        description="Search the pool in plain English. Filters layer on top."
        actions={
          <div className="flex gap-2">
            <BulkImportButton />
            <CreateCandidateButton />
          </div>
        }
      />
      <CandidateSearch
        initial={initial}
        stages={stages.map((s) => s.name)}
        canReindex={me.role === "admin"}
      />
    </div>
  );
}
