"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardEyebrow } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";

const ROUTE_TONE: Record<string, string> = {
  structured: "text-emerald-600",
  semantic: "text-sky-600",
  hybrid: "text-violet-600",
};

const SAMPLES = [
  "How many Python developers in Pune are there?",
  "Backend engineer with fintech experience",
  "Candidates with 5+ years experience in payments",
  "Number of candidates in each stage",
];

type Result = Awaited<ReturnType<typeof api.askPool>>;

export function PoolAsk() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function ask(q: string) {
    if (!q.trim()) return;
    setError(null);
    setBusy(true);
    try {
      const r = await api.askPool(q.trim());
      setResult(r);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask(question);
          }}
          className="flex gap-2"
        >
          <Input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask anything…"
            disabled={busy}
            className="text-base"
            autoFocus
          />
          <Button type="submit" disabled={busy || !question.trim()}>
            {busy ? "Asking…" : "Ask"}
          </Button>
        </form>

        <div className="mt-3 flex flex-wrap gap-2">
          {SAMPLES.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => {
                setQuestion(s);
                ask(s);
              }}
              className="rounded-full border border-[var(--border)] bg-[var(--muted)] px-3 py-1 text-xs hover:bg-[var(--background)]"
            >
              {s}
            </button>
          ))}
        </div>
      </Card>

      {error ? (
        <p className="text-sm text-[var(--destructive)]">{error}</p>
      ) : null}

      {result ? (
        <Card className="p-6">
          <div className="flex items-baseline justify-between">
            <CardEyebrow>Answer</CardEyebrow>
            <span
              className={`font-mono text-[10px] uppercase tracking-[0.22em] ${
                ROUTE_TONE[result.route] ?? ""
              }`}
            >
              {result.route}
              {result.matched_count != null
                ? ` · ${result.matched_count} match${result.matched_count === 1 ? "" : "es"}`
                : ""}
            </span>
          </div>

          <div className="mt-3 whitespace-pre-wrap rounded-md bg-[var(--muted)] p-4 text-sm leading-relaxed">
            {result.answer}
          </div>

          {result.rows && result.rows.length > 0 ? (
            <div className="mt-5">
              <CardEyebrow>Rows</CardEyebrow>
              <div className="mt-2 overflow-x-auto rounded-md border border-[var(--border)]">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-[var(--border)] bg-[var(--muted)]">
                      {Object.keys(result.rows[0]).map((k) => (
                        <th
                          key={k}
                          className="px-3 py-2 text-left font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]"
                        >
                          {k}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.map((row, i) => (
                      <tr
                        key={i}
                        className="border-t border-[var(--border)]"
                      >
                        {Object.values(row).map((v, j) => (
                          <td key={j} className="px-3 py-2">
                            {String(v ?? "—")}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}

          {result.citations.length ? (
            <div className="mt-5">
              <CardEyebrow>Candidates</CardEyebrow>
              <ul className="mt-2 space-y-1.5">
                {result.citations.map((c, i) => (
                  <li key={i} className="text-sm">
                    {c.id != null ? (
                      <Link
                        href={`/candidates/${c.id}`}
                        className="hover:underline"
                      >
                        {c.snippet}
                      </Link>
                    ) : (
                      <span>{c.snippet}</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </Card>
      ) : null}
    </div>
  );
}
