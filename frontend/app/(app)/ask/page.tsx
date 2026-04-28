import { PageHeader } from "@/components/page-header";
import { PoolAsk } from "./pool-ask";

export const dynamic = "force-dynamic";

export default function AskPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Talent base"
        title="Ask"
        description="Ask anything about the pool. Routed to SQL aggregation, semantic retrieval, or both — automatically."
      />
      <PoolAsk />
    </div>
  );
}
