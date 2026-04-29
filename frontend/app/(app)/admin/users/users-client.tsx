"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardEyebrow } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, api, type User } from "@/lib/api";

export function UsersClient({
  initial,
  meId,
}: {
  initial: User[];
  meId: number;
}) {
  const [users, setUsers] = useState<User[]>(initial);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);

  async function setRole(u: User, role: "admin" | "recruiter") {
    setBusyId(u.id);
    setError(null);
    try {
      const updated = await api.updateUser(u.id, { role });
      setUsers((prev) => prev.map((x) => (x.id === u.id ? updated : x)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed");
    } finally {
      setBusyId(null);
    }
  }

  async function setActive(u: User, is_active: boolean) {
    setBusyId(u.id);
    setError(null);
    try {
      const updated = await api.updateUser(u.id, { is_active });
      setUsers((prev) => prev.map((x) => (x.id === u.id ? updated : x)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed");
    } finally {
      setBusyId(null);
    }
  }

  async function resetPwd(u: User) {
    const newPwd = window.prompt(
      `Reset password for ${u.email}?\nEnter new temporary password (≥8 chars):`,
    );
    if (!newPwd || newPwd.length < 8) return;
    setBusyId(u.id);
    setError(null);
    try {
      const updated = await api.resetUserPassword(u.id, newPwd);
      setUsers((prev) => prev.map((x) => (x.id === u.id ? updated : x)));
      alert(`Password reset. ${u.email} must change it on next login.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <CardEyebrow>{users.length} users</CardEyebrow>
        <Button onClick={() => setCreating(true)}>New user</Button>
      </div>

      {error ? (
        <p className="text-sm text-[var(--destructive)]">{error}</p>
      ) : null}

      {creating ? (
        <CreateUserModal
          onClose={() => setCreating(false)}
          onCreated={(u) => {
            setUsers((prev) => [u, ...prev]);
            setCreating(false);
          }}
        />
      ) : null}

      <div className="divide-y divide-[var(--border)] rounded-lg border border-[var(--border)] bg-[var(--card)]">
        {users.map((u) => {
          const isMe = u.id === meId;
          const busy = busyId === u.id;
          return (
            <div
              key={u.id}
              className="flex flex-wrap items-center gap-4 px-5 py-4"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium tracking-tight">{u.name}</span>
                  {isMe ? (
                    <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                      you
                    </span>
                  ) : null}
                  {!u.is_active ? (
                    <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--destructive)]">
                      inactive
                    </span>
                  ) : null}
                  {u.must_change_password ? (
                    <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-amber-600">
                      pw·change
                    </span>
                  ) : null}
                </div>
                <div className="mt-0.5 text-xs text-[var(--muted-foreground)]">
                  {u.email}
                </div>
              </div>

              <select
                value={u.role}
                onChange={(e) => setRole(u, e.target.value as "admin" | "recruiter")}
                disabled={busy}
                className="h-8 rounded-md border border-[var(--input)] bg-transparent px-2 text-xs"
              >
                <option value="recruiter">recruiter</option>
                <option value="admin">admin</option>
              </select>

              <Button
                size="sm"
                variant="ghost"
                onClick={() => setActive(u, !u.is_active)}
                disabled={busy || isMe}
              >
                {u.is_active ? "deactivate" : "reactivate"}
              </Button>

              <Button
                size="sm"
                variant="ghost"
                onClick={() => resetPwd(u)}
                disabled={busy}
              >
                reset password
              </Button>
            </div>
          );
        })}
      </div>
    </div>
  );
}


function CreateUserModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (u: User) => void;
}) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"admin" | "recruiter" | "client">("recruiter");
  const [clientId, setClientId] = useState<number | "">("");
  const [clients, setClients] = useState<{ id: number; name: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Lazy-load the client list the first time the user picks role=client.
  useEffect(() => {
    if (role === "client" && clients.length === 0) {
      api.listClients().then(setClients).catch(() => {});
    }
  }, [role, clients.length]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (role === "client" && clientId === "") {
      setError("Pick a client to tag this user to.");
      return;
    }
    setSubmitting(true);
    try {
      const u = await api.createUser({
        email,
        name,
        password,
        role,
        ...(role === "client" && clientId !== ""
          ? { client_id: Number(clientId) }
          : {}),
      });
      onCreated(u);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-6">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-md space-y-4 rounded-lg border border-[var(--border)] bg-[var(--card)] p-6"
      >
        <div>
          <CardEyebrow>New user</CardEyebrow>
          <h2 className="mt-2 text-xl font-semibold tracking-tight">Add a teammate</h2>
        </div>
        <div className="space-y-2">
          <Label htmlFor="cu-email">Email</Label>
          <Input
            id="cu-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={submitting}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="cu-name">Name</Label>
          <Input
            id="cu-name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={submitting}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="cu-pw">Temporary password (≥8 chars)</Label>
          <Input
            id="cu-pw"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={submitting}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="cu-role">Role</Label>
          <select
            id="cu-role"
            value={role}
            onChange={(e) =>
              setRole(e.target.value as "admin" | "recruiter" | "client")
            }
            disabled={submitting}
            className="h-10 w-full rounded-md border border-[var(--input)] bg-transparent px-3 text-sm"
          >
            <option value="recruiter">recruiter</option>
            <option value="admin">admin</option>
            <option value="client">client</option>
          </select>
        </div>
        {role === "client" ? (
          <div className="space-y-2">
            <Label htmlFor="cu-client">Tagged client</Label>
            <select
              id="cu-client"
              required
              value={clientId}
              onChange={(e) =>
                setClientId(e.target.value === "" ? "" : Number(e.target.value))
              }
              disabled={submitting}
              className="h-10 w-full rounded-md border border-[var(--input)] bg-transparent px-3 text-sm"
            >
              <option value="">Select a client…</option>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <p className="text-xs text-[var(--muted-foreground)]">
              Client users see only this client&apos;s jobs and the candidates
              linked to them.
            </p>
          </div>
        ) : null}
        {error ? <p className="text-sm text-[var(--destructive)]">{error}</p> : null}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Creating…" : "Create"}
          </Button>
        </div>
      </form>
    </div>
  );
}
