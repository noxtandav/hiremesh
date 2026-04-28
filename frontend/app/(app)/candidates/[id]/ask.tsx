"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardEyebrow } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";

type Citation = { type: string; id: number | null; snippet: string };

const TYPE_LABEL: Record<string, string> = {
  profile: "profile",
  resume: "resume",
  note: "note",
};

export function AskCandidate({ candidateId }: { candidateId: number }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function ask(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setError(null);
    setBusy(true);
    try {
      const r = await api.askCandidate(candidateId, question.trim());
      setAnswer(r.answer);
      setCitations(r.citations);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-6">
      <CardEyebrow>Ask about this candidate</CardEyebrow>

      <form onSubmit={ask} className="mt-3 flex gap-2">
        <Input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="What's her notice period?  Has she worked with Kafka?"
          disabled={busy}
        />
        <Button type="submit" disabled={busy || !question.trim()}>
          {busy ? "Asking…" : "Ask"}
        </Button>
      </form>

      {error ? (
        <p className="mt-3 text-sm text-[var(--destructive)]">{error}</p>
      ) : null}

      {answer ? (
        <div className="mt-5 space-y-4">
          <div className="whitespace-pre-wrap rounded-md bg-[var(--muted)] p-4 text-sm leading-relaxed">
            {answer}
          </div>
          {citations.length ? (
            <div>
              <CardEyebrow>Sources</CardEyebrow>
              <ul className="mt-2 space-y-1.5">
                {citations.map((c, i) => (
                  <li
                    key={`${c.type}-${c.id}-${i}`}
                    className="text-xs text-[var(--muted-foreground)]"
                  >
                    <span className="font-mono uppercase tracking-[0.18em]">
                      {TYPE_LABEL[c.type] ?? c.type}
                      {c.id != null ? ` #${c.id}` : ""}
                    </span>
                    {" — "}
                    <span className="line-clamp-2">{c.snippet}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
