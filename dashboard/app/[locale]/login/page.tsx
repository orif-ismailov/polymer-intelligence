"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

interface LoginResponse {
  access_token: string;
  token_type: string;
}

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const { login } = useAuth();

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const data = await apiFetch<LoginResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      login(data.access_token);
      router.push("/");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Login failed. Check your credentials.",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold text-foreground">Polymer Intelligence</h1>
          <p className="mt-1 text-sm text-foreground-muted">Sign in to the dashboard</p>
        </div>
        <form
          onSubmit={handleSubmit}
          className="rounded-lg border border-border bg-background-secondary p-6 shadow-lg"
        >
          {/* Error banner */}
          {error && (
            <div
              role="alert"
              className="mb-4 rounded-md border border-status-cancelled/30 bg-status-cancelled/10 px-3 py-2 text-sm text-status-cancelled"
            >
              {error}
            </div>
          )}
          <div className="mb-4">
            <label
              htmlFor="email"
              className="mb-1 block text-sm font-medium text-foreground-muted"
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder-foreground-subtle focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              placeholder="analyst@company.com"
            />
          </div>
          <div className="mb-6">
            <label
              htmlFor="password"
              className="mb-1 block text-sm font-medium text-foreground-muted"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder-foreground-subtle focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              placeholder="••••••••"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-md bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-dark focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background-secondary disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </main>
  );
}
