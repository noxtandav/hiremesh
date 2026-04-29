"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";

const ACCEPT = ".pdf,.docx,.doc,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/msword";

type Result = {
  filename: string;
  status: "ok" | "error";
  candidate_id?: number;
  resume_id?: number;
  placeholder_name?: string;
  error?: string;
};

export function BulkImportButton() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<Result[] | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  function reset() {
    setFiles([]);
    setError(null);
    setResults(null);
    setSubmitting(false);
  }

  function close() {
    if (results && results.some((r) => r.status === "ok")) router.refresh();
    setOpen(false);
    reset();
  }

  function addFiles(incoming: FileList | File[]) {
    const next = Array.from(incoming).filter((f) => {
      const lower = f.name.toLowerCase();
      return lower.endsWith(".pdf") || lower.endsWith(".docx") || lower.endsWith(".doc");
    });
    if (next.length === 0) {
      setError("Only PDF, DOC and DOCX files are accepted");
      return;
    }
    setError(null);
    setFiles((prev) => [...prev, ...next]);
  }

  function removeFile(idx: number) {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  }

  async function onSubmit() {
    if (files.length === 0) {
      setError("Add at least one file");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const resp = await api.bulkImportCandidates(files);
      setResults(resp.results);
      setFiles([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Import failed");
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) {
    return (
      <Button variant="outline" onClick={() => setOpen(true)}>
        Bulk import
      </Button>
    );
  }

  const okCount = results?.filter((r) => r.status === "ok").length ?? 0;
  const errCount = results?.filter((r) => r.status === "error").length ?? 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-6">
      <div className="w-full max-w-xl space-y-4 rounded-lg border border-[var(--border)] bg-[var(--card)] p-6">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--muted-foreground)]">
            Bulk import
          </div>
          <h2 className="mt-2 text-xl font-semibold tracking-tight">
            Upload many resumes
          </h2>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">
            Each PDF or DOCX becomes a candidate. Names and skills are filled in
            automatically as the parser runs.
          </p>
        </div>

        {!results ? (
          <>
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                addFiles(e.dataTransfer.files);
              }}
              onClick={() => inputRef.current?.click()}
              className={`flex cursor-pointer flex-col items-center justify-center rounded-md border-2 border-dashed px-4 py-8 text-center text-sm transition ${
                dragOver
                  ? "border-[var(--primary)] bg-[var(--accent)]/30"
                  : "border-[var(--border)] hover:bg-[var(--accent)]/20"
              }`}
            >
              <p className="font-medium">Drop files here or click to choose</p>
              <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                PDF, DOC, DOCX · 10 MB per file · 50 max per batch
              </p>
              <input
                ref={inputRef}
                type="file"
                multiple
                accept={ACCEPT}
                className="hidden"
                onChange={(e) => {
                  if (e.target.files) addFiles(e.target.files);
                  e.target.value = "";
                }}
              />
            </div>

            {files.length > 0 ? (
              <ul className="max-h-56 space-y-1 overflow-y-auto rounded-md border border-[var(--border)] p-2 text-sm">
                {files.map((f, i) => (
                  <li
                    key={`${f.name}-${i}`}
                    className="flex items-center justify-between rounded px-2 py-1 hover:bg-[var(--accent)]/30"
                  >
                    <span className="truncate font-mono text-xs">{f.name}</span>
                    <button
                      type="button"
                      className="ml-2 text-xs text-[var(--muted-foreground)] hover:text-[var(--destructive)]"
                      onClick={() => removeFile(i)}
                      disabled={submitting}
                    >
                      remove
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}

            {error ? (
              <p className="text-sm text-[var(--destructive)]">{error}</p>
            ) : null}

            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="ghost"
                onClick={close}
                disabled={submitting}
              >
                Cancel
              </Button>
              <Button onClick={onSubmit} disabled={submitting || files.length === 0}>
                {submitting
                  ? `Uploading ${files.length}…`
                  : `Import ${files.length || ""}`.trim()}
              </Button>
            </div>
          </>
        ) : (
          <>
            <div className="rounded-md border border-[var(--border)] bg-[var(--accent)]/20 px-3 py-2 text-sm">
              <span className="font-medium">{okCount} imported</span>
              {errCount > 0 ? (
                <span className="ml-2 text-[var(--destructive)]">
                  · {errCount} failed
                </span>
              ) : null}
              <span className="ml-2 text-[var(--muted-foreground)]">
                · parsing in the background
              </span>
            </div>
            <ul className="max-h-72 space-y-1 overflow-y-auto rounded-md border border-[var(--border)] p-2 text-sm">
              {results.map((r, i) => (
                <li
                  key={i}
                  className="flex items-center justify-between rounded px-2 py-1"
                >
                  <span className="truncate font-mono text-xs">{r.filename}</span>
                  {r.status === "ok" ? (
                    <a
                      href={`/candidates/${r.candidate_id}`}
                      className="text-xs text-[var(--primary)] hover:underline"
                    >
                      view →
                    </a>
                  ) : (
                    <span className="text-xs text-[var(--destructive)]" title={r.error}>
                      {r.error?.slice(0, 50) ?? "error"}
                    </span>
                  )}
                </li>
              ))}
            </ul>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => reset()}>
                Import more
              </Button>
              <Button onClick={close}>Done</Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
