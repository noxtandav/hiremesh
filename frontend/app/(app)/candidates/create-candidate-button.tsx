"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";

const ACCEPT =
  ".pdf,.docx,.doc,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/msword";

function isAcceptedFile(file: File): boolean {
  const lower = file.name.toLowerCase();
  return (
    lower.endsWith(".pdf") || lower.endsWith(".docx") || lower.endsWith(".doc")
  );
}

export function CreateCandidateButton() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function reset() {
    setFile(null);
    setError(null);
    setSubmitting(false);
    setDragOver(false);
  }

  function close() {
    setOpen(false);
    reset();
  }

  function pickFile(f: File | undefined) {
    if (!f) return;
    if (!isAcceptedFile(f)) {
      setError("Only PDF, DOC and DOCX are accepted");
      return;
    }
    setError(null);
    setFile(f);
  }

  async function onSubmit() {
    if (!file) {
      setError("Add a resume file");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const resp = await api.bulkImportCandidates([file]);
      const result = resp.results[0];
      if (!result || result.status !== "ok" || !result.candidate_id) {
        setError(result?.error ?? "Import failed");
        setSubmitting(false);
        return;
      }
      router.push(`/candidates/${result.candidate_id}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
      setSubmitting(false);
    }
  }

  if (!open) {
    return <Button onClick={() => setOpen(true)}>New candidate</Button>;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-6">
      <div className="w-full max-w-md space-y-4 rounded-lg border border-[var(--border)] bg-[var(--card)] p-6">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--muted-foreground)]">
            New candidate
          </div>
          <h2 className="mt-2 text-xl font-semibold tracking-tight">
            Add from resume
          </h2>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">
            Drop a PDF or DOCX. Name, skills and contact details are filled in
            automatically by the parser.
          </p>
        </div>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            pickFile(e.dataTransfer.files?.[0]);
          }}
          onClick={() => inputRef.current?.click()}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-md border-2 border-dashed px-4 py-10 text-center text-sm transition ${
            dragOver
              ? "border-[var(--primary)] bg-[var(--accent)]/30"
              : "border-[var(--border)] hover:bg-[var(--accent)]/20"
          }`}
        >
          {file ? (
            <>
              <p className="font-mono text-xs">{file.name}</p>
              <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                click to choose a different file
              </p>
            </>
          ) : (
            <>
              <p className="font-medium">Drop resume here or click to choose</p>
              <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                PDF, DOC, DOCX · 10 MB max
              </p>
            </>
          )}
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            className="hidden"
            onChange={(e) => {
              pickFile(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
        </div>

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
          <Button onClick={onSubmit} disabled={submitting || !file}>
            {submitting ? "Uploading…" : "Add candidate"}
          </Button>
        </div>
      </div>
    </div>
  );
}
