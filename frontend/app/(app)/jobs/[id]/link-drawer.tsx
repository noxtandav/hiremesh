"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiError,
  api,
  type Candidate,
  type CandidateJob,
  type Note,
  type Stage,
  type StageTransition,
} from "@/lib/api";

type LinkRow = CandidateJob & { candidate: Candidate };

export function LinkDrawer({
  link,
  stages,
  onClose,
  onUnlink,
}: {
  link: LinkRow;
  stages: Stage[];
  onClose: () => void;
  onUnlink: () => void;
}) {
  const [transitions, setTransitions] = useState<StageTransition[] | null>(null);
  const [notes, setNotes] = useState<Note[] | null>(null);
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const stageName = (id: number | null) =>
    id == null
      ? <span className="text-[var(--muted-foreground)]">—</span>
      : stages.find((s) => s.id === id)?.name ?? `#${id}`;

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.listTransitions(link.id), api.listLinkNotes(link.id)])
      .then(([t, n]) => {
        if (cancelled) return;
        setTransitions(t);
        setNotes(n);
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Failed to load history"),
      );
    return () => {
      cancelled = true;
    };
  }, [link.id]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!body.trim()) return;
    setAdding(true);
    try {
      const note = await api.createLinkNote(link.id, body.trim());
      setNotes((prev) => [note, ...(prev ?? [])]);
      setBody("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed");
    } finally {
      setAdding(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/40"
      onClick={onClose}
    >
      <aside
        onClick={(e) => e.stopPropagation()}
        className="flex h-full w-full max-w-md flex-col gap-6 overflow-y-auto border-l border-[var(--border)] bg-[var(--card)] p-6"
      >
        <header className="flex items-start justify-between gap-3">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--muted-foreground)]">
              Pipeline activity
            </div>
            <Link
              href={`/candidates/${link.candidate.id}`}
              className="mt-1 block text-xl font-semibold tracking-tight hover:underline"
            >
              {link.candidate.full_name}
            </Link>
            <div className="mt-1 text-xs text-[var(--muted-foreground)]">
              currently in <span className="font-medium">{stageName(link.current_stage_id)}</span>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
          >
            close
          </button>
        </header>

        {error ? (
          <p className="text-sm text-[var(--destructive)]">{error}</p>
        ) : null}

        <section>
          <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--muted-foreground)]">
            History
          </div>
          {transitions === null ? (
            <p className="text-xs text-[var(--muted-foreground)]">Loading…</p>
          ) : (
            <ol className="space-y-1.5">
              {transitions.map((t) => (
                <li key={t.id} className="flex items-baseline gap-3 text-sm">
                  <span
                    className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]"
                    suppressHydrationWarning
                  >
                    {new Date(t.at).toLocaleString()}
                  </span>
                  <span>
                    {t.from_stage_id == null ? "linked at " : ""}
                    {stageName(t.to_stage_id)}
                    {t.from_stage_id != null && t.to_stage_id != null ? (
                      <span className="text-[var(--muted-foreground)]">
                        {" "}from {stageName(t.from_stage_id)}
                      </span>
                    ) : null}
                    {t.to_stage_id == null ? (
                      <span className="text-[var(--muted-foreground)]"> · unlinked</span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section>
          <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--muted-foreground)]">
            Notes on this job · {notes?.length ?? 0}
          </div>
          <form onSubmit={add} className="space-y-2">
            <Textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={3}
              placeholder="What changed? Anything to flag for the next move?"
              disabled={adding}
            />
            <div className="flex justify-end">
              <Button
                type="submit"
                size="sm"
                disabled={adding || !body.trim()}
              >
                {adding ? "Saving…" : "Add note"}
              </Button>
            </div>
          </form>
          <ul className="mt-3 space-y-2">
            {(notes ?? []).map((n) => (
              <li
                key={n.id}
                className="rounded-md border border-[var(--border)] p-2.5 text-sm"
              >
                <p className="whitespace-pre-wrap">{n.body}</p>
                <div
                  className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]"
                  suppressHydrationWarning
                >
                  {new Date(n.created_at).toLocaleString()}
                </div>
              </li>
            ))}
            {notes !== null && notes.length === 0 ? (
              <li className="rounded-md border border-dashed border-[var(--border)] p-3 text-center text-xs text-[var(--muted-foreground)]">
                No notes for this candidate on this job yet.
              </li>
            ) : null}
          </ul>
        </section>

        <footer className="mt-auto flex justify-between border-t border-[var(--border)] pt-4">
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
          <Button variant="destructive" size="sm" onClick={onUnlink}>
            Unlink from this job
          </Button>
        </footer>
      </aside>
    </div>
  );
}
