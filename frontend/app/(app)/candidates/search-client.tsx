"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardEyebrow } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, api, type Candidate } from "@/lib/api";

type Hit = { candidate: Candidate; score: number | null };

export function CandidateSearch({
  initial,
  stages,
  canReindex,
}: {
  initial: Hit[];
  stages: string[];
  canReindex: boolean;
}) {
  const [q, setQ] = useState("");
  const [location, setLocation] = useState("");
  const [skills, setSkills] = useState<string[]>([]);
  const [skillDraft, setSkillDraft] = useState("");
  const [expMin, setExpMin] = useState<string>("");
  const [expMax, setExpMax] = useState<string>("");
  const [stageName, setStageName] = useState<string>("");

  const [results, setResults] = useState<Hit[]>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reindexMsg, setReindexMsg] = useState<string | null>(null);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const params = useMemo(
    () => ({
      q: q.trim() || undefined,
      location: location.trim() || undefined,
      skills: skills.length ? skills : undefined,
      exp_min: expMin ? Number(expMin) : undefined,
      exp_max: expMax ? Number(expMax) : undefined,
      stage_name: stageName || undefined,
      limit: 50,
    }),
    [q, location, skills, expMin, expMax, stageName],
  );

  // Debounced refetch on any param change.
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setBusy(true);
      setError(null);
      try {
        const r = await api.searchCandidates(params);
        setResults(r);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Search failed");
      } finally {
        setBusy(false);
      }
    }, 250);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(params)]);

  function addSkill(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key !== "Enter" && e.key !== ",") return;
    e.preventDefault();
    const s = skillDraft.trim();
    if (s && !skills.includes(s)) setSkills((prev) => [...prev, s]);
    setSkillDraft("");
  }
  function removeSkill(s: string) {
    setSkills((prev) => prev.filter((x) => x !== s));
  }

  async function reindex() {
    setReindexMsg("Enqueueing…");
    try {
      const r = await api.reindexCandidates();
      setReindexMsg(`Enqueued ${r.enqueued} candidates`);
    } catch (err) {
      setReindexMsg(err instanceof ApiError ? err.message : "Failed");
    }
  }

  const hasFilters =
    q || location || skills.length || expMin || expMax || stageName;

  return (
    <div className="space-y-6">
      <Card className="p-5">
        <div className="space-y-4">
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Backend engineer with fintech experience in Pune…"
            className="text-base"
          />

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Input
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="Location"
            />
            <div>
              <Input
                value={skillDraft}
                onChange={(e) => setSkillDraft(e.target.value)}
                onKeyDown={addSkill}
                placeholder="Skills · Enter to add"
              />
              {skills.length ? (
                <div className="mt-2 flex flex-wrap gap-1">
                  {skills.map((s) => (
                    <button
                      type="button"
                      key={s}
                      onClick={() => removeSkill(s)}
                      className="rounded-full border border-[var(--border)] bg-[var(--muted)] px-2 py-0.5 text-xs hover:border-[var(--destructive)]"
                    >
                      {s} ×
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Input
                type="number"
                step="0.5"
                min="0"
                value={expMin}
                onChange={(e) => setExpMin(e.target.value)}
                placeholder="Exp min"
              />
              <Input
                type="number"
                step="0.5"
                min="0"
                value={expMax}
                onChange={(e) => setExpMax(e.target.value)}
                placeholder="Exp max"
              />
            </div>
            <select
              value={stageName}
              onChange={(e) => setStageName(e.target.value)}
              className="h-10 rounded-md border border-[var(--input)] bg-transparent px-3 text-sm"
            >
              <option value="">Any stage</option>
              {stages.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center justify-between text-xs text-[var(--muted-foreground)]">
            <span>
              {busy ? "Searching…" : `${results.length} match${results.length === 1 ? "" : "es"}`}
              {hasFilters ? "" : " · all candidates"}
            </span>
            {canReindex ? (
              <div className="flex items-center gap-2">
                {reindexMsg ? <span>{reindexMsg}</span> : null}
                <Button variant="ghost" size="sm" onClick={reindex}>
                  Reindex pool
                </Button>
              </div>
            ) : null}
          </div>
        </div>
      </Card>

      {error ? (
        <p className="text-sm text-[var(--destructive)]">{error}</p>
      ) : null}

      {results.length === 0 ? (
        <Card className="p-10 text-center">
          <CardEyebrow>No matches</CardEyebrow>
          <p className="mt-3 text-sm text-[var(--muted-foreground)]">
            {hasFilters
              ? "Try loosening filters or removing the search query."
              : "The pool is empty. Add a candidate to get started."}
          </p>
        </Card>
      ) : (
        <div className="divide-y divide-[var(--border)] rounded-lg border border-[var(--border)] bg-[var(--card)]">
          {results.map(({ candidate: c, score }) => (
            <Link
              key={c.id}
              href={`/candidates/${c.id}`}
              className="flex items-center justify-between gap-6 px-5 py-4 transition-colors hover:bg-[var(--muted)]"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium tracking-tight">{c.full_name}</span>
                  {score != null ? (
                    <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                      {(score * 100).toFixed(0)}%
                    </span>
                  ) : null}
                </div>
                <div className="mt-1 truncate text-xs text-[var(--muted-foreground)]">
                  {[c.current_title, c.current_company, c.location]
                    .filter(Boolean)
                    .join(" · ")}
                </div>
                {c.skills.length ? (
                  <div className="mt-1 truncate text-xs text-[var(--muted-foreground)]">
                    {c.skills.slice(0, 6).join(", ")}
                    {c.skills.length > 6 ? ` +${c.skills.length - 6}` : ""}
                  </div>
                ) : null}
              </div>
              {c.total_exp_years ? (
                <div className="font-mono text-xs tabular-nums text-[var(--muted-foreground)]">
                  {c.total_exp_years} yrs
                </div>
              ) : null}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
