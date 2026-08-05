"use client";

import Link from "next/link";
import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export default function LoginPage() {
  return <Suspense fallback={<main className="auth-shell" />}><LoginForm /></Suspense>;
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setStatus(null);
    try {
      const next = searchParams.get("next");
      const response = await fetch("/api/v1/launch/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ password, next_path: next?.startsWith("/") ? next : "/home" }),
      });
      if (!response.ok) throw new Error("That password did not open this workspace.");
      router.replace(next?.startsWith("/") ? next : "/home");
      router.refresh();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "We could not open this workspace.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card" aria-labelledby="login-title">
        <Link href="/" className="brand-mark"><i aria-hidden="true" /> Fortune Farms</Link>
        <p className="eyebrow">AGRO CEO · private farm command</p>
        <h1 id="login-title">Come back to the field.</h1>
        <p className="muted">Enter the Fortune pilot password to continue.</p>
        <form onSubmit={submit} className="auth-form">
          <label htmlFor="password">Pilot password</label>
          <input id="password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required autoFocus />
          {status ? <p className="form-error" role="alert">{status}</p> : null}
          <button className="primary-action" disabled={submitting}>{submitting ? "Opening…" : "Open AGRO CEO"} <span aria-hidden="true">→</span></button>
        </form>
        <p className="hindi" lang="hi">फॉर्च्यून फार्म्स के निजी संचालन केंद्र में प्रवेश करें</p>
      </section>
    </main>
  );
}
