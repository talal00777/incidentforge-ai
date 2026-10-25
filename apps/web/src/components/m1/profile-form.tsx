"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { Account, apiWrite, describeApiFailure } from "@/lib/api-client";
import { useAccount } from "@/components/m1/use-account";

function EditProfile({ user }: { user: Account }) {
  const [firstName, setFirstName] = useState(user.first_name);
  const [lastName, setLastName] = useState(user.last_name);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await apiWrite<Account>("auth/me", "PATCH", {
        first_name: firstName,
        last_name: lastName,
      });
      setMessage("Profile updated.");
    } catch (failure) {
      setError(describeApiFailure(failure));
    } finally {
      setBusy(false);
    }
  }

  return <section className="panel m1-form-panel" aria-labelledby="profile-heading">
    <h2 id="profile-heading">Account details</h2>
    <p className="m1-hint">{user.email}</p>
    <form className="m1-form" onSubmit={save}>
      <label htmlFor="profile-first">First name</label>
      <input id="profile-first" maxLength={150} value={firstName} autoComplete="given-name" onChange={(event) => setFirstName(event.target.value)} />
      <label htmlFor="profile-last">Last name</label>
      <input id="profile-last" maxLength={150} value={lastName} autoComplete="family-name" onChange={(event) => setLastName(event.target.value)} />
      {error && <p className="m1-error" role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      <div className="m1-actions"><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save profile"}</button><Link className="button button-outline" href="/incidents">Back</Link></div>
    </form>
  </section>;
}

export function ProfileForm() {
  const account = useAccount();
  if (account.state === "loading") return <p role="status">Checking your session…</p>;
  if (account.state === "error") return <p role="alert">{account.message}</p>;
  if (account.state === "signed-out") return <p>Please <Link href="/login">sign in</Link> to view your profile.</p>;
  return <EditProfile user={account.user} />;
}
