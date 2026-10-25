"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiWrite, describeApiFailure } from "@/lib/api-client";
import { useAccount } from "@/components/m1/use-account";

export function AccountSection() {
  const account = useAccount();
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (account.state === "loading") return <p role="status">Checking your session…</p>;
  if (account.state === "error") return <p role="alert">{account.message}</p>;
  if (account.state === "signed-out") {
    return <div className="m1-account"><p>Sign in to manage incidents.</p><Link className="button button-primary" href="/login">Sign in</Link><Link href="/register">Create account</Link></div>;
  }

  async function signOut() {
    setBusy(true);
    setError("");
    try {
      await apiWrite<void>("auth/logout", "POST");
      router.replace("/login");
      router.refresh();
    } catch (failure) {
      setError(describeApiFailure(failure));
    } finally {
      setBusy(false);
    }
  }

  return <div className="m1-account">
    <span className="m1-account-email">{account.user.email}</span>
    <Link href="/profile">Profile</Link>
    <button className="button button-outline" type="button" onClick={signOut} disabled={busy}>Sign out</button>
    {error && <p role="alert">{error}</p>}
  </div>;
}
