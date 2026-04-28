"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";

export function DeleteCandidateButton({ id }: { id: number }) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function onDelete() {
    setSubmitting(true);
    try {
      await api.deleteCandidate(id);
      router.push("/candidates");
      router.refresh();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Failed");
      setSubmitting(false);
    }
  }

  if (!confirming) {
    return (
      <Button variant="outline" size="sm" onClick={() => setConfirming(true)}>
        Soft-delete
      </Button>
    );
  }
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-[var(--muted-foreground)]">Are you sure?</span>
      <Button variant="ghost" size="sm" onClick={() => setConfirming(false)}>
        Cancel
      </Button>
      <Button
        variant="destructive"
        size="sm"
        onClick={onDelete}
        disabled={submitting}
      >
        {submitting ? "…" : "Delete"}
      </Button>
    </div>
  );
}
