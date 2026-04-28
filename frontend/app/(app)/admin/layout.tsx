import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { Nav } from "@/components/nav";
import { api } from "@/lib/api";

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const cookie = (await headers()).get("cookie") ?? undefined;
  const me = await api.me(cookie);
  if (me.role !== "admin") redirect("/dashboard");

  const subnav = [
    { href: "/admin/users", label: "Users" },
    { href: "/admin/stages", label: "Stages" },
    { href: "/admin/audit-log", label: "Audit log" },
    { href: "/admin/metrics", label: "Metrics" },
  ];

  return (
    <div className="space-y-6">
      <div className="border-b border-[var(--border)] pb-3">
        <Nav items={subnav} />
      </div>
      {children}
    </div>
  );
}
