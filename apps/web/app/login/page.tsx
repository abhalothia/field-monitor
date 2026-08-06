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
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setStatus(null);
    try {
      const requestedNext = searchParams.get("next");
      const response = await fetch("/api/v1/identity/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ login_id: loginId, password }),
      });
      const payload = (await response.json().catch(() => null)) as { detail?: string; next_path?: string } | null;
      if (!response.ok) throw new Error(payload?.detail || "That ID or password did not open this workspace.");
      router.replace(payload?.next_path || (requestedNext?.startsWith("/") ? requestedNext : "/home"));
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
        <h1 id="login-title">Your work, ready.</h1>
        <p className="muted">Sign in with the AGRO CEO ID your farm admin gave you.</p>
        <form onSubmit={submit} className="auth-form">
          <label htmlFor="login-id">AGRO CEO ID</label><input id="login-id" autoComplete="username" autoCapitalize="none" value={loginId} onChange={(event) => setLoginId(event.target.value)} required autoFocus />
          <label htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          {status ? <p className="form-error" role="alert">{status}</p> : null}
          <button className="primary-action" disabled={submitting}>{submitting ? "Opening…" : "Sign in"} <span aria-hidden="true">→</span></button>
        </form>
        <p className="hindi" lang="hi">अपना एग्रो सीईओ आईडी और पासवर्ड डालें</p>
      </section>
    </main>
  );
}
