"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, api, type Stage } from "@/lib/api";

type Row = { id?: number; name: string };

export function StagesEditor({ initial }: { initial: Stage[] }) {
  const [rows, setRows] = useState<Row[]>(
    initial.map((s) => ({ id: s.id, name: s.name })),
  );
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  function update(i: number, name: string) {
    setRows((prev) => prev.map((r, j) => (i === j ? { ...r, name } : r)));
  }
  function move(i: number, dir: -1 | 1) {
    const j = i + dir;
    if (j < 0 || j >= rows.length) return;
    setRows((prev) => {
      const copy = [...prev];
      [copy[i], copy[j]] = [copy[j], copy[i]];
      return copy;
    });
  }
  function remove(i: number) {
    setRows((prev) => prev.filter((_, j) => i !== j));
  }
  function add() {
    setRows((prev) => [...prev, { name: "New stage" }]);
  }

  async function save() {
    setError(null);
    setSaving(true);
    try {
      const updated = await api.updateStageTemplate(
        rows.filter((r) => r.name.trim()).map((r) => ({ id: r.id, name: r.name.trim() })),
      );
      setRows(updated.map((s) => ({ id: s.id, name: s.name })));
      setSavedAt(new Date().toLocaleTimeString());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="p-6">
      <ol className="space-y-2">
        {rows.map((r, i) => (
          <li
            key={r.id ?? `new-${i}`}
            className="flex items-center gap-2"
          >
            <span className="w-8 font-mono text-[10px] text-[var(--muted-foreground)]">
              {String(i + 1).padStart(2, "0")}
            </span>
            <Input
              value={r.name}
              onChange={(e) => update(i, e.target.value)}
              className="flex-1"
            />
            <Button variant="ghost" size="sm" onClick={() => move(i, -1)} disabled={i === 0}>
              ↑
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => move(i, 1)}
              disabled={i === rows.length - 1}
            >
              ↓
            </Button>
            <Button variant="ghost" size="sm" onClick={() => remove(i)}>
              remove
            </Button>
          </li>
        ))}
      </ol>

      <div className="mt-5 flex items-center justify-between">
        <Button variant="outline" size="sm" onClick={add}>
          + Add stage
        </Button>
        <div className="flex items-center gap-3">
          {savedAt ? (
            <span className="text-xs text-[var(--muted-foreground)]">
              Saved at {savedAt}
            </span>
          ) : null}
          {error ? (
            <span className="text-xs text-[var(--destructive)]">{error}</span>
          ) : null}
          <Button onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save template"}
          </Button>
        </div>
      </div>
    </Card>
  );
}
