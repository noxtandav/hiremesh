import { Suspense } from "react";
import { LoginForm } from "@/components/login-form";

export default function LoginPage() {
  return (
    <main className="flex min-h-screen flex-1 items-center justify-center px-6 py-16">
      <div className="w-full max-w-sm">
        <div className="mb-10">
          <h1 className="font-mono text-xs uppercase tracking-[0.2em] text-[var(--muted-foreground)]">
            Hiremesh
          </h1>
          <p className="mt-3 text-3xl font-semibold tracking-tight">Sign in</p>
          <p className="mt-2 text-sm text-[var(--muted-foreground)]">
            Use the credentials your admin sent you.
          </p>
        </div>

        <Suspense>
          <LoginForm />
        </Suspense>
      </div>
    </main>
  );
}
