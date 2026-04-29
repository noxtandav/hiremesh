"use client";

import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  DragStartEvent,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Card, CardEyebrow } from "@/components/ui/card";
import {
  ApiError,
  api,
  type Candidate,
  type CandidateJob,
  type LastTransition,
  type Stage,
} from "@/lib/api";
import { LinkCandidateButton } from "./link-candidate-button";
import { LinkDrawer } from "./link-drawer";

type LinkRow = CandidateJob & {
  candidate: Candidate;
  last_transition: LastTransition | null;
};
type Column = { stage: Stage; links: LinkRow[] };

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diffMs / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d}d ago`;
  if (d < 30) return `${Math.floor(d / 7)}w ago`;
  return iso.slice(0, 10);
}

export function Board({
  jobId,
  initial,
}: {
  jobId: number;
  initial: Column[];
}) {
  const router = useRouter();
  const [columns, setColumns] = useState<Column[]>(initial);
  const [error, setError] = useState<string | null>(null);
  const [activeLink, setActiveLink] = useState<LinkRow | null>(null);
  const [drawerLink, setDrawerLink] = useState<LinkRow | null>(null);
  const allStages = columns.map((c) => c.stage);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
  );

  function findLink(linkId: number) {
    for (const col of columns) {
      const found = col.links.find((l) => l.id === linkId);
      if (found) return { col, link: found };
    }
    return null;
  }

  function onDragStart(e: DragStartEvent) {
    const found = findLink(Number(e.active.id));
    setActiveLink(found?.link ?? null);
  }

  async function onDragEnd(e: DragEndEvent) {
    setActiveLink(null);
    const { active, over } = e;
    if (!over) return;
    const linkId = Number(active.id);
    const targetStageId = Number(over.id);

    const found = findLink(linkId);
    if (!found) return;
    if (found.link.current_stage_id === targetStageId) return;

    // Optimistic: move the row in local state immediately, then rollback on error.
    const previous = columns;
    const moved: LinkRow = { ...found.link, current_stage_id: targetStageId };
    setColumns((prev) =>
      prev.map((col) => {
        if (col.stage.id === found.link.current_stage_id) {
          return { ...col, links: col.links.filter((l) => l.id !== linkId) };
        }
        if (col.stage.id === targetStageId) {
          return { ...col, links: [...col.links, moved] };
        }
        return col;
      }),
    );

    try {
      await api.moveLink(linkId, targetStageId);
      router.refresh();
    } catch (err) {
      setColumns(previous);
      setError(err instanceof ApiError ? err.message : "Move failed");
    }
  }

  async function onUnlink(linkId: number) {
    const previous = columns;
    setColumns((prev) =>
      prev.map((col) => ({
        ...col,
        links: col.links.filter((l) => l.id !== linkId),
      })),
    );
    try {
      await api.unlink(linkId);
    } catch (err) {
      setColumns(previous);
      setError(err instanceof ApiError ? err.message : "Unlink failed");
    }
  }

  async function onLinkAdded(candidateId: number) {
    try {
      await api.linkCandidateToJob(jobId, candidateId);
      const fresh = await api.getBoard(jobId);
      setColumns(fresh);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Link failed");
    }
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <CardEyebrow>Pipeline</CardEyebrow>
        <LinkCandidateButton onPick={onLinkAdded} />
      </div>

      {error ? (
        <p className="mb-3 text-sm text-[var(--destructive)]">{error}</p>
      ) : null}

      <DndContext
        sensors={sensors}
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
      >
        <div className="flex gap-3 overflow-x-auto pb-4">
          {columns.map((col) => (
            <KanbanColumn
              key={col.stage.id}
              column={col}
              onOpen={(l) => setDrawerLink(l)}
            />
          ))}
        </div>
        <DragOverlay>
          {activeLink ? (
            <CandidateCard link={activeLink} dragging />
          ) : null}
        </DragOverlay>
      </DndContext>

      {drawerLink ? (
        <LinkDrawer
          link={drawerLink}
          stages={allStages}
          onClose={() => setDrawerLink(null)}
          onUnlink={async () => {
            await onUnlink(drawerLink.id);
            setDrawerLink(null);
          }}
        />
      ) : null}
    </div>
  );
}

function KanbanColumn({
  column,
  onOpen,
}: {
  column: Column;
  onOpen: (link: LinkRow) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: column.stage.id });
  return (
    <div
      ref={setNodeRef}
      className={`flex w-72 shrink-0 flex-col gap-2 rounded-lg border p-3 transition-colors ${
        isOver
          ? "border-[var(--ring)] bg-[var(--muted)]"
          : "border-[var(--border)] bg-[var(--card)]"
      }`}
    >
      <header className="flex items-center justify-between px-1 pt-1">
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--muted-foreground)]">
          {column.stage.name}
        </span>
        <span className="font-mono text-[10px] tabular-nums text-[var(--muted-foreground)]">
          {column.links.length}
        </span>
      </header>
      <div className="flex flex-col gap-2">
        {column.links.length === 0 ? (
          <div className="rounded-md border border-dashed border-[var(--border)] p-4 text-center text-[10px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
            empty
          </div>
        ) : null}
        {column.links.map((link) => (
          <DraggableCard key={link.id} link={link} onOpen={() => onOpen(link)} />
        ))}
      </div>
    </div>
  );
}

function DraggableCard({
  link,
  onOpen,
}: {
  link: LinkRow;
  onOpen: () => void;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: link.id,
  });
  return (
    <div
      ref={setNodeRef}
      style={{ opacity: isDragging ? 0 : 1 }}
      {...attributes}
      {...listeners}
    >
      <CandidateCard link={link} onOpen={onOpen} />
    </div>
  );
}

function CandidateCard({
  link,
  dragging,
  onOpen,
}: {
  link: LinkRow;
  dragging?: boolean;
  onOpen?: () => void;
}) {
  const c = link.candidate;
  return (
    <Card
      className={`group cursor-grab select-none p-3 ${
        dragging ? "shadow-lg ring-2 ring-[var(--ring)]" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <Link
          href={`/candidates/${c.id}`}
          onClick={(e) => e.stopPropagation()}
          onPointerDown={(e) => e.stopPropagation()}
          className="text-sm font-medium tracking-tight hover:underline"
        >
          {c.full_name}
        </Link>
        {onOpen ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onOpen();
            }}
            onPointerDown={(e) => e.stopPropagation()}
            className="opacity-0 transition-opacity group-hover:opacity-100 text-[10px] uppercase tracking-[0.18em] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            title="Open activity"
          >
            details
          </button>
        ) : null}
      </div>
      <div className="mt-1 truncate text-xs text-[var(--muted-foreground)]">
        {[c.current_title, c.current_company, c.location]
          .filter(Boolean)
          .join(" · ") || <span>&nbsp;</span>}
      </div>
      {c.email ? (
        <div className="mt-1 truncate text-xs text-[var(--muted-foreground)]">
          {c.email}
        </div>
      ) : null}
      {c.phone ? (
        <div className="mt-0.5 truncate text-xs text-[var(--muted-foreground)]">
          {c.phone}
        </div>
      ) : null}
      {link.last_transition ? (
        <div
          className="mt-2 truncate border-t border-[var(--border)] pt-2 font-mono text-[10px] uppercase tracking-[0.16em] text-[var(--muted-foreground)]"
          title={`${new Date(link.last_transition.at).toLocaleString()}${
            link.last_transition.by_user_name
              ? ` · by ${link.last_transition.by_user_name}`
              : ""
          }`}
          suppressHydrationWarning
        >
          Moved {relativeTime(link.last_transition.at)}
          {link.last_transition.by_user_name
            ? ` · ${link.last_transition.by_user_name}`
            : ""}
        </div>
      ) : null}
    </Card>
  );
}
