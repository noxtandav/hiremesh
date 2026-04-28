"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

export function LogoutButton() {
  const router = useRouter();
  async function onClick() {
    await api.logout();
    router.push("/login");
    router.refresh();
  }
  return (
    <Button variant="ghost" size="sm" onClick={onClick}>
      Log out
    </Button>
  );
}
