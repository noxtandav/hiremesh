"use client";

import { useMemo, useState } from "react";
import { Card, CardEyebrow } from "@/components/ui/card";
import { api, type Resume } from "@/lib/api";

const PDF_MIME = "application/pdf";

function pickInitial(resumes: Resume[]): Resume | null {
  if (resumes.length === 0) return null;
  return (
    resumes.find((r) => r.is_primary) ??
    resumes.find((r) => r.parse_status === "done") ??
    resumes[0]
  );
}

function shortLabel(name: string) {
  if (name.length <= 22) return name;
  const dot = name.lastIndexOf(".");
  const ext = dot > 0 ? name.slice(dot) : "";
  const stem = dot > 0 ? name.slice(0, dot) : name;
  return `${stem.slice(0, 18)}…${ext}`;
}

export function ResumePreview({ resumes }: { resumes: Resume[] }) {
  const initial = useMemo(() => pickInitial(resumes), [resumes]);
  const [activeId, setActiveId] = useState<number | null>(initial?.id ?? null);

  const active =
    resumes.find((r) => r.id === activeId) ?? initial ?? null;
  // `#view=FitH` tells the browser's PDF viewer to fit-to-width instead of
  // fit-to-page (which renders thumbnail-sized pages in a tall iframe).
  const previewUrl = active
    ? `${api.resumeFilePath(active.id)}#view=FitH`
    : null;

  if (resumes.length === 0) {
    return (
      <Card className="p-6">
        <CardEyebrow>Resume preview</CardEyebrow>
        <div className="mt-4 rounded-md border border-dashed border-[var(--border)] p-8 text-center text-sm text-[var(--muted-foreground)]">
          No resume uploaded yet. Use the panel on the right to add one.
        </div>
      </Card>
    );
  }

  const isPdf = active?.mime === PDF_MIME;

  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <CardEyebrow>Resume preview</CardEyebrow>
        {resumes.length > 1 ? (
          <div className="flex flex-wrap gap-1">
            {resumes.map((r) => (
              <button
                key={r.id}
                type="button"
                title={r.filename}
                onClick={() => setActiveId(r.id)}
                className={`rounded-md border px-2 py-1 font-mono text-[10px] uppercase tracking-[0.18em] transition ${
                  active?.id === r.id
                    ? "border-[var(--foreground)]/30 bg-[var(--accent)]"
                    : "border-[var(--border)] hover:bg-[var(--accent)]/40"
                }`}
              >
                {shortLabel(r.filename)}
                {r.is_primary ? <span className="ml-1 opacity-60">★</span> : null}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {!active || !previewUrl ? null : !isPdf ? (
        <div className="mt-4 rounded-md border border-dashed border-[var(--border)] p-8 text-center text-sm">
          <p className="text-[var(--muted-foreground)]">
            Inline preview is available for PDFs only. This file is{" "}
            <span className="font-mono text-xs">{active.filename}</span>.
          </p>
          <a
            href={api.resumeFilePath(active.id, { download: true })}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-3 inline-block text-[var(--primary)] hover:underline"
          >
            Download →
          </a>
        </div>
      ) : (
        <iframe
          key={previewUrl}
          src={previewUrl}
          className="mt-4 h-[85vh] min-h-[800px] w-full rounded-md border border-[var(--border)]"
          title={active.filename}
        />
      )}
    </Card>
  );
}
