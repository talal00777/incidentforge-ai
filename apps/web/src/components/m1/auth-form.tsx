"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Account, apiWrite, describeApiFailure } from "@/lib/api-client";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const registration = mode === "register";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await apiWrite<Account>(`auth/${mode}`, "POST", { email, password });
      router.replace("/incidents");
      router.refresh();
    } catch (failure) {
      setError(describeApiFailure(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="m1-auth-screen">
      <section className="m1-auth-card" aria-labelledby="auth-heading">
        <Link href="/" className="m1-auth-brand">IncidentForge</Link>
        <h1 id="auth-heading">{registration ? "Create an account" : "Sign in"}</h1>
        <p className="m1-subtitle">Access your incident workspace.</p>
        <form onSubmit={submit} className="m1-form">
          <label htmlFor="auth-email">Email</label>
          <input id="auth-email" type="email" name="email" autoComplete="email" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} />
          <label htmlFor="auth-password">Password</label>
          <input id="auth-password" type="password" name="password" required minLength={registration ? 12 : undefined} autoComplete={registration ? "new-password" : "current-password"} value={password} onChange={(event) => setPassword(event.target.value)} />
          {registration && <p className="m1-hint">Use a unique password of at least 12 characters.</p>}
          {error && <p className="m1-error" role="alert">{error}</p>}
          <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Submitting…" : registration ? "Create account" : "Sign in"}</button>
        </form>
        <p className="m1-footnote">{registration ? "Already have an account?" : "New to IncidentForge?"} <Link href={registration ? "/login" : "/register"}>{registration ? "Sign in" : "Create account"}</Link></p>
      </section>
    </main>
  );
}
