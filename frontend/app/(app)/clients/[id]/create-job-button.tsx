"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";

export function CreateJobButton({ clientId }: { clientId: number }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [location, setLocation] = useState("");
  const [expMin, setExpMin] = useState("");
  const [expMax, setExpMax] = useState("");
  const [ctcMin, setCtcMin] = useState("");
  const [ctcMax, setCtcMax] = useState("");
  const [jdText, setJdText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const num = (v: string) => (v.trim() === "" ? undefined : Number(v));

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const j = await api.createJob({
        client_id: clientId,
        title,
        location: location || undefined,
        exp_min: num(expMin),
        exp_max: num(expMax),
        ctc_min: num(ctcMin),
        ctc_max: num(ctcMax),
        jd_text: jdText || undefined,
      });
      setOpen(false);
      router.push(`/jobs/${j.id}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed");
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) return <Button onClick={() => setOpen(true)}>New job</Button>;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-6">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-lg space-y-5 rounded-lg border border-[var(--border)] bg-[var(--card)] p-6"
      >
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--muted-foreground)]">
            New job
          </div>
          <h2 className="mt-2 text-xl font-semibold tracking-tight">Open a position</h2>
        </div>

        <div className="space-y-2">
          <Label htmlFor="title">Title</Label>
          <Input
            id="title"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={submitting}
            autoFocus
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-2">
            <Label htmlFor="loc">Location</Label>
            <Input
              id="loc"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              disabled={submitting}
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-2">
              <Label htmlFor="emin">Exp min</Label>
              <Input
                id="emin"
                type="number"
                step="0.5"
                min="0"
                value={expMin}
                onChange={(e) => setExpMin(e.target.value)}
                disabled={submitting}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="emax">Exp max</Label>
              <Input
                id="emax"
                type="number"
                step="0.5"
                min="0"
                value={expMax}
                onChange={(e) => setExpMax(e.target.value)}
                disabled={submitting}
              />
            </div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-2">
            <Label htmlFor="cmin">CTC min</Label>
            <Input
              id="cmin"
              type="number"
              min="0"
              value={ctcMin}
              onChange={(e) => setCtcMin(e.target.value)}
              disabled={submitting}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="cmax">CTC max</Label>
            <Input
              id="cmax"
              type="number"
              min="0"
              value={ctcMax}
              onChange={(e) => setCtcMax(e.target.value)}
              disabled={submitting}
            />
          </div>
        </div>
        <div className="space-y-2">
          <Label htmlFor="jd">JD</Label>
          <Textarea
            id="jd"
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            rows={5}
            disabled={submitting}
          />
        </div>
        {error ? <p className="text-sm text-[var(--destructive)]">{error}</p> : null}
        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={() => setOpen(false)}
            disabled={submitting}
          >
            Cancel
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Saving…" : "Save"}
          </Button>
        </div>
      </form>
    </div>
  );
}
