"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const returnTo = searchParams.get("returnTo") || "/";
  const { signIn, signUp, loading: authLoading, authConfigured } = useAuth();

  const [mode, setMode] = useState<"sign_in" | "sign_up">("sign_in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [signupNote, setSignupNote] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSignupNote(null);
    setPending(true);
    try {
      if (mode === "sign_in") {
        const { error: err } = await signIn(email, password);
        if (err) {
          setError(err.message);
          return;
        }
        const safe = returnTo.startsWith("/") ? returnTo : "/";
        router.replace(safe);
        router.refresh();
        return;
      }
      const { error: err } = await signUp(email, password);
      if (err) {
        setError(err.message);
        return;
      }
      setSignupNote(
        "Check your email to confirm your account if required, then sign in.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="w-full max-w-sm space-y-8">
      <div className="text-center">
        <h1 className="text-xl font-medium tracking-tight">Sign in</h1>
        <p className="mt-2 text-sm text-white/50">
          Use your Supabase account to unlock full PM voice and saving.
        </p>
      </div>

      {!authConfigured ? (
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-center text-xs text-amber-200/90">
          Add{" "}
          <code className="text-amber-100/90">NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
          <code className="text-amber-100/90">NEXT_PUBLIC_SUPABASE_ANON_KEY</code>{" "}
          to <code className="text-amber-100/90">.env.local</code>, then restart
          Next.js.
        </p>
      ) : null}

      <div className="flex justify-center gap-2 rounded-full border border-white/10 bg-white/[0.03] p-1 text-sm">
        <button
          type="button"
          onClick={() => {
            setMode("sign_in");
            setError(null);
            setSignupNote(null);
          }}
          className={`rounded-full px-4 py-2 transition ${
            mode === "sign_in"
              ? "bg-white/10 text-white"
              : "text-white/45 hover:text-white/70"
          }`}
        >
          Sign in
        </button>
        <button
          type="button"
          onClick={() => {
            setMode("sign_up");
            setError(null);
            setSignupNote(null);
          }}
          className={`rounded-full px-4 py-2 transition ${
            mode === "sign_up"
              ? "bg-white/10 text-white"
              : "text-white/45 hover:text-white/70"
          }`}
        >
          Create account
        </button>
      </div>

      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label htmlFor="email" className="mb-1 block text-xs text-white/45">
            Email
          </label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-lg border border-white/12 bg-white/[0.04] px-3 py-2.5 text-sm outline-none ring-orange-400/30 focus:border-orange-400/40 focus:ring-1"
          />
        </div>
        <div>
          <label
            htmlFor="password"
            className="mb-1 block text-xs text-white/45"
          >
            Password
          </label>
          <input
            id="password"
            type="password"
            autoComplete={
              mode === "sign_in" ? "current-password" : "new-password"
            }
            required
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-lg border border-white/12 bg-white/[0.04] px-3 py-2.5 text-sm outline-none ring-orange-400/30 focus:border-orange-400/40 focus:ring-1"
          />
        </div>

        {error ? (
          <p className="text-center text-xs text-red-400/90">{error}</p>
        ) : null}
        {signupNote ? (
          <p className="text-center text-xs text-emerald-400/90">{signupNote}</p>
        ) : null}

        <button
          type="submit"
          disabled={pending || authLoading || !authConfigured}
          className="w-full rounded-lg bg-orange-500/90 py-2.5 text-sm font-medium text-black transition hover:bg-orange-400 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {pending
            ? "Please wait…"
            : mode === "sign_in"
              ? "Sign in"
              : "Sign up"}
        </button>
      </form>

      <p className="text-center text-xs text-white/35">
        <Link href="/" className="text-orange-300/80 hover:text-orange-200">
          ← Back to app
        </Link>
      </p>
    </div>
  );
}

export default function LoginPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-black px-6 text-white">
      <Suspense
        fallback={
          <div className="h-32 w-full max-w-sm animate-pulse rounded-lg bg-white/[0.04]" />
        }
      >
        <LoginForm />
      </Suspense>
    </main>
  );
}
