"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";

type Row = Awaited<ReturnType<typeof api.listAudit>>[number];

export function AuditClient({ initial }: { initial: Row[] }) {
  const [rows, setRows] = useState<Row[]>(initial);
  const [entity, setEntity] = useState("");
  const [action, setAction] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const t = setTimeout(async () => {
      setBusy(true);
      setError(null);
      try {
        const r = await api.listAudit({
          entity: entity || undefined,
          action: action || undefined,
          limit: 200,
        });
        setRows(r);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed");
      } finally {
        setBusy(false);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [entity, action]);

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Input
            value={entity}
            onChange={(e) => setEntity(e.target.value)}
            placeholder="Filter entity (user / candidate / client / job / system)"
          />
          <Input
            value={action}
            onChange={(e) => setAction(e.target.value)}
            placeholder="Filter action (login / candidate.create / …)"
          />
        </div>
        <p className="mt-2 text-xs text-[var(--muted-foreground)]">
          {busy ? "Loading…" : `${rows.length} rows`}
        </p>
      </Card>

      {error ? (
        <p className="text-sm text-[var(--destructive)]">{error}</p>
      ) : null}

      <Card className="overflow-x-auto p-0">
        <table className="w-full text-xs">
          <thead className="border-b border-[var(--border)] bg-[var(--muted)]">
            <tr>
              {["When", "Actor", "Action", "Entity", "ID", "Payload"].map((h) => (
                <th
                  key={h}
                  className="px-3 py-2 text-left font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-[var(--border)]">
                <td
                  className="px-3 py-2 font-mono text-[10px] uppercase tracking-[0.16em] text-[var(--muted-foreground)]"
                  suppressHydrationWarning
                >
                  {new Date(r.at).toLocaleString()}
                </td>
                <td className="px-3 py-2">{r.actor_name ?? "—"}</td>
                <td className="px-3 py-2 font-mono text-[11px]">{r.action}</td>
                <td className="px-3 py-2">{r.entity}</td>
                <td className="px-3 py-2">{r.entity_id ?? "—"}</td>
                <td className="px-3 py-2 max-w-md truncate text-[11px] text-[var(--muted-foreground)]">
                  {r.payload ? JSON.stringify(r.payload) : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
