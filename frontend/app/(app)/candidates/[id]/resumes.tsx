"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardEyebrow } from "@/components/ui/card";
import { ApiError, api, type Resume, type ResumeStatus } from "@/lib/api";

const STATUS_TONE: Record<ResumeStatus, string> = {
  pending: "bg-[var(--muted)] text-[var(--muted-foreground)]",
  parsing: "bg-amber-500/10 text-amber-600",
  done: "bg-emerald-500/10 text-emerald-600",
  failed: "bg-[var(--destructive)]/10 text-[var(--destructive)]",
};

function StatusBadge({ status }: { status: ResumeStatus }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.18em] ${STATUS_TONE[status]}`}
    >
      {status}
    </span>
  );
}

export function Resumes({
  candidateId,
  initial,
}: {
  candidateId: number;
  initial: Resume[];
}) {
  const router = useRouter();
  const [resumes, setResumes] = useState<Resume[]>(initial);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const hasParsing = resumes.some(
    (r) => r.parse_status === "pending" || r.parse_status === "parsing",
  );

  // Poll while anything is still parsing.
  useEffect(() => {
    if (!hasParsing) return;
    const t = setInterval(async () => {
      const fresh = await api.listResumes(candidateId);
      setResumes(fresh);
      const stillParsing = fresh.some(
        (r) => r.parse_status === "pending" || r.parse_status === "parsing",
      );
      if (!stillParsing) {
        clearInterval(t);
        // Refresh the candidate panel so newly-applied parsed fields show up.
        router.refresh();
      }
    }, 1500);
    return () => clearInterval(t);
  }, [hasParsing, candidateId, router]);

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    setError(null);
    setBusy(true);
    try {
      const r = await api.uploadResume(candidateId, file);
      setResumes((prev) => [r, ...prev]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function setPrimary(id: number) {
    try {
      await api.setPrimaryResume(id);
      setResumes((prev) =>
        prev.map((r) => ({ ...r, is_primary: r.id === id })),
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed");
    }
  }

  async function reparse(id: number) {
    try {
      const r = await api.reparseResume(id);
      setResumes((prev) => prev.map((x) => (x.id === id ? r : x)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed");
    }
  }

  async function remove(id: number) {
    try {
      await api.deleteResume(id);
      setResumes((prev) => prev.filter((r) => r.id !== id));
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed");
    }
  }

  async function download(id: number) {
    try {
      const { url } = await api.getResumeUrl(id);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed");
    }
  }

  return (
    <Card className="p-6">
      <div className="flex items-center justify-between">
        <CardEyebrow>Resumes · {resumes.length}</CardEyebrow>
        <div>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.doc,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/msword"
            onChange={onUpload}
            className="hidden"
          />
          <Button
            size="sm"
            variant="outline"
            onClick={() => fileRef.current?.click()}
            disabled={busy}
          >
            {busy ? "Uploading…" : "Upload resume"}
          </Button>
        </div>
      </div>

      {error ? (
        <p className="mt-3 text-sm text-[var(--destructive)]">{error}</p>
      ) : null}

      <ul className="mt-5 space-y-2">
        {resumes.length === 0 ? (
          <li className="rounded-md border border-dashed border-[var(--border)] p-4 text-center text-xs text-[var(--muted-foreground)]">
            No resumes yet. Upload a PDF or DOCX — the parser will fill in
            structured fields automatically.
          </li>
        ) : null}
        {resumes.map((r) => (
          <li
            key={r.id}
            className="rounded-md border border-[var(--border)] p-3"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium">
                    {r.filename}
                  </span>
                  {r.is_primary ? (
                    <span className="rounded-full bg-[var(--primary)]/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--foreground)]">
                      primary
                    </span>
                  ) : null}
                  <StatusBadge status={r.parse_status} />
                </div>
                <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                  {new Date(r.created_at).toLocaleString()}
                </div>
                {r.parse_status === "failed" && r.parse_error ? (
                  <p className="mt-2 text-xs text-[var(--destructive)]">
                    {r.parse_error.split("\n")[0]}
                  </p>
                ) : null}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Button size="sm" variant="ghost" onClick={() => download(r.id)}>
                  download
                </Button>
                {!r.is_primary ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setPrimary(r.id)}
                  >
                    make primary
                  </Button>
                ) : null}
                <Button size="sm" variant="ghost" onClick={() => reparse(r.id)}>
                  re-parse
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => remove(r.id)}
                >
                  delete
                </Button>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
