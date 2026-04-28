import { headers } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";
import { LogoutButton } from "@/components/logout-button";
import { Nav } from "@/components/nav";
import { api } from "@/lib/api";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const cookie = (await headers()).get("cookie") ?? undefined;

  let user;
  try {
    user = await api.me(cookie);
  } catch {
    redirect("/login");
  }

  const nav = [
    { href: "/dashboard", label: "Dashboard" },
    { href: "/clients", label: "Clients" },
    { href: "/candidates", label: "Candidates" },
    { href: "/ask", label: "Ask" },
    ...(user.role === "admin"
      ? [{ href: "/admin", label: "Admin" }]
      : []),
  ];

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-[var(--border)]">
        <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between gap-6 px-6">
          <Link
            href="/dashboard"
            className="font-mono text-xs uppercase tracking-[0.22em] text-[var(--foreground)]"
          >
            Hiremesh
          </Link>
          <Nav items={nav} />
          <div className="flex items-center gap-4 text-sm">
            <span className="hidden text-[var(--muted-foreground)] sm:inline">
              {user.name} · {user.role}
            </span>
            <LogoutButton />
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-10">{children}</main>
    </div>
  );
}
