"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, type Candidate } from "@/lib/api";

export function LinkCandidateButton({
  onPick,
}: {
  onPick: (candidateId: number) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [all, setAll] = useState<Candidate[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.listCandidates({}).then(setAll);
  }, [open]);

  const filtered = query.trim()
    ? all.filter((c) =>
        `${c.full_name} ${c.email ?? ""} ${c.current_company ?? ""} ${c.skills.join(
          " ",
        )}`
          .toLowerCase()
          .includes(query.toLowerCase()),
      )
    : all;

  async function pick(id: number) {
    setBusy(true);
    try {
      await onPick(id);
      setOpen(false);
      setQuery("");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <Button size="sm" onClick={() => setOpen(true)}>
        Add candidate
      </Button>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 px-6 py-20">
      <div className="w-full max-w-md rounded-lg border border-[var(--border)] bg-[var(--card)] p-4">
        <div className="mb-3 flex items-center justify-between">
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--muted-foreground)]">
            Link a candidate
          </span>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
          >
            close
          </button>
        </div>
        <Input
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by name, company, skill…"
        />
        <ul className="mt-3 max-h-72 divide-y divide-[var(--border)] overflow-y-auto rounded-md border border-[var(--border)]">
          {filtered.length === 0 ? (
            <li className="p-3 text-center text-xs text-[var(--muted-foreground)]">
              No matches.
            </li>
          ) : null}
          {filtered.slice(0, 50).map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => pick(c.id)}
                disabled={busy}
                className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left transition-colors hover:bg-[var(--muted)] disabled:opacity-50"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm">{c.full_name}</span>
                  <span className="block truncate text-xs text-[var(--muted-foreground)]">
                    {[c.current_title, c.current_company, c.location]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </span>
                <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                  add
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
