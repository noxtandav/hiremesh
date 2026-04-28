import { headers } from "next/headers";
import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";
import { UsersClient } from "./users-client";

export const dynamic = "force-dynamic";

export default async function UsersPage() {
  const cookie = (await headers()).get("cookie") ?? undefined;
  const [me, users] = await Promise.all([api.me(cookie), api.listUsers(cookie)]);

  return (
    <div>
      <PageHeader
        eyebrow="Admin"
        title="Users"
        description="Create accounts, change roles, deactivate, or reset a password."
      />
      <UsersClient initial={users} meId={me.id} />
    </div>
  );
}
