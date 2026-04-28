"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardEyebrow } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api, type Note } from "@/lib/api";

export function Notes({
  candidateId,
  initial,
}: {
  candidateId: number;
  initial: Note[];
}) {
  const [notes, setNotes] = useState<Note[]>(initial);
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!body.trim()) return;
    setError(null);
    setSubmitting(true);
    try {
      const note = await api.createNote(candidateId, body.trim());
      setNotes((prev) => [note, ...prev]);
      setBody("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function remove(id: number) {
    try {
      await api.deleteNote(id);
      setNotes((prev) => prev.filter((n) => n.id !== id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed");
    }
  }

  return (
    <Card className="p-6">
      <CardEyebrow>Notes · {notes.length}</CardEyebrow>

      <form onSubmit={add} className="mt-3 space-y-2">
        <Textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="What did you learn from the call? Anything to remember?"
          rows={3}
          disabled={submitting}
        />
        {error ? <p className="text-sm text-[var(--destructive)]">{error}</p> : null}
        <div className="flex justify-end">
          <Button type="submit" size="sm" disabled={submitting || !body.trim()}>
            {submitting ? "Saving…" : "Add note"}
          </Button>
        </div>
      </form>

      <ul className="mt-5 space-y-3">
        {notes.length === 0 ? (
          <li className="rounded-md border border-dashed border-[var(--border)] p-4 text-center text-xs text-[var(--muted-foreground)]">
            No notes yet.
          </li>
        ) : null}
        {notes.map((n) => (
          <li
            key={n.id}
            className="rounded-md border border-[var(--border)] p-3"
          >
            <p className="whitespace-pre-wrap text-sm">{n.body}</p>
            <div className="mt-2 flex items-center justify-between text-[10px] text-[var(--muted-foreground)]">
              <span className="font-mono uppercase tracking-[0.18em]">
                {new Date(n.created_at).toLocaleString()}
              </span>
              <button
                type="button"
                onClick={() => remove(n.id)}
                className="rounded px-2 py-0.5 text-xs text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--destructive)]"
              >
                delete
              </button>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
