"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";

export function CreateCandidateButton() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [location, setLocation] = useState("");
  const [currentTitle, setCurrentTitle] = useState("");
  const [currentCompany, setCurrentCompany] = useState("");
  const [skills, setSkills] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const c = await api.createCandidate({
        full_name: fullName,
        email: email || undefined,
        phone: phone || undefined,
        location: location || undefined,
        current_title: currentTitle || undefined,
        current_company: currentCompany || undefined,
        skills: skills
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      } as never);
      setOpen(false);
      router.push(`/candidates/${c.id}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed");
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) return <Button onClick={() => setOpen(true)}>New candidate</Button>;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-6">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-lg space-y-4 rounded-lg border border-[var(--border)] bg-[var(--card)] p-6"
      >
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--muted-foreground)]">
            New candidate
          </div>
          <h2 className="mt-2 text-xl font-semibold tracking-tight">Add manually</h2>
        </div>

        <div className="space-y-2">
          <Label htmlFor="fn">Full name</Label>
          <Input
            id="fn"
            required
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            disabled={submitting}
            autoFocus
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-2">
            <Label htmlFor="em">Email</Label>
            <Input
              id="em"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={submitting}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="ph">Phone</Label>
            <Input
              id="ph"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              disabled={submitting}
            />
          </div>
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
          <div className="space-y-2">
            <Label htmlFor="ti">Current title</Label>
            <Input
              id="ti"
              value={currentTitle}
              onChange={(e) => setCurrentTitle(e.target.value)}
              disabled={submitting}
            />
          </div>
        </div>
        <div className="space-y-2">
          <Label htmlFor="co">Current company</Label>
          <Input
            id="co"
            value={currentCompany}
            onChange={(e) => setCurrentCompany(e.target.value)}
            disabled={submitting}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="sk">Skills (comma-separated)</Label>
          <Textarea
            id="sk"
            rows={2}
            value={skills}
            onChange={(e) => setSkills(e.target.value)}
            disabled={submitting}
            placeholder="Python, FastAPI, Postgres, Kafka"
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
