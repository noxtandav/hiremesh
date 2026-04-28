"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";

export function ResetEmbeddingsButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function reindex() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.reindexCandidates();
      setMsg(`Reindex enqueued: ${r.enqueued} candidates`);
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  async function reset(skipProbe = false) {
    if (
      !window.confirm(
        "This drops the embeddings table and rebuilds it at the configured dim. " +
          "All existing embeddings will be wiped (a reindex is enqueued). Continue?",
      )
    ) {
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.resetEmbeddings(skipProbe);
      setMsg(`Reset to ${r.dim} dims · ${r.enqueued} candidates re-enqueued`);
      router.refresh();
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button size="sm" variant="outline" onClick={reindex} disabled={busy}>
        Reindex pool
      </Button>
      <Button size="sm" variant="outline" onClick={() => reset(false)} disabled={busy}>
        Reset embeddings
      </Button>
      <Button
        size="sm"
        variant="ghost"
        onClick={() => reset(true)}
        disabled={busy}
        title="Skip the probe step — only useful when temporarily on fake mode"
      >
        Reset (skip probe)
      </Button>
      {msg ? <span className="text-xs text-[var(--muted-foreground)]">{msg}</span> : null}
    </div>
  );
}
