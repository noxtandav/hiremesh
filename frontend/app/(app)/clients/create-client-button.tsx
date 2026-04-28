"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";

export function CreateClientButton() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const c = await api.createClient({ name, notes: notes || undefined });
      setOpen(false);
      setName("");
      setNotes("");
      router.push(`/clients/${c.id}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed");
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) {
    return <Button onClick={() => setOpen(true)}>New client</Button>;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-6">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-md space-y-5 rounded-lg border border-[var(--border)] bg-[var(--card)] p-6"
      >
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--muted-foreground)]">
            New client
          </div>
          <h2 className="mt-2 text-xl font-semibold tracking-tight">
            Add a company
          </h2>
        </div>
        <div className="space-y-2">
          <Label htmlFor="name">Name</Label>
          <Input
            id="name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={submitting}
            autoFocus
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="notes">Notes</Label>
          <Textarea
            id="notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            disabled={submitting}
            rows={3}
            placeholder="How you met them, what they tend to hire for, any context worth keeping…"
          />
        </div>
        {error ? <p className="text-sm text-[var(--destructive)]">{error}</p> : null}
        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={() => setOpen(false)}
            disabled={submitting}
          >
            Cancel
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Saving…" : "Save"}
          </Button>
        </div>
      </form>
    </div>
  );
}
