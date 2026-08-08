"use client";

import Link from "next/link";
import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

const REMEMBERED_NAME_COOKIE = "agroceo_welcome_name";
const REMEMBERED_ID_COOKIE = "agroceo_login_id";
const REMEMBERED_MAX_AGE_SECONDS = 30 * 24 * 60 * 60;

function readBrowserCookie(name: string) {
  if (typeof document === "undefined") return "";
  const value = document.cookie.split("; ").find((item) => item.startsWith(`${name}=`))?.slice(name.length + 1);
  try { return value ? decodeURIComponent(value).slice(0, 128) : ""; } catch { return ""; }
}

function setBrowserCookie(name: string, value: string, maxAge = REMEMBERED_MAX_AGE_SECONDS) {
  const secure = typeof window !== "undefined" && window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${name}=${encodeURIComponent(value)}; Path=/; Max-Age=${maxAge}; SameSite=Lax${secure}`;
}

function firstName(name: string) {
  return name.trim().split(/\s+/)[0]?.slice(0, 48) || "";
}

function requestedDestination(value: string | null) {
  return value && /^\/(?!\/)/.test(value) ? value : "/home";
}

export default function LoginPage() {
  return <Suspense fallback={<main className="auth-shell" />}><LoginForm /></Suspense>;
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [rememberedName, setRememberedName] = useState(() => readBrowserCookie(REMEMBERED_NAME_COOKIE));
  const [loginId, setLoginId] = useState(() => readBrowserCookie(REMEMBERED_ID_COOKIE));
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setStatus(null);
    try {
      const response = await fetch("/api/v1/identity/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ login_id: loginId, password }),
      });
      const payload = (await response.json().catch(() => null)) as { detail?: string; person_name?: string; next_path?: string } | null;
      if (!response.ok) throw new Error(payload?.detail || "That ID or password did not open this workspace.");
      const name = payload?.person_name?.trim();
      if (name) setBrowserCookie(REMEMBERED_NAME_COOKIE, name);
      setBrowserCookie(REMEMBERED_ID_COOKIE, loginId.trim().toLowerCase());
      router.replace(payload?.next_path || requestedDestination(searchParams.get("next")));
      router.refresh();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "We could not open this workspace.");
    } finally {
      setSubmitting(false);
    }
  }

  function useAnotherId() {
    setBrowserCookie(REMEMBERED_NAME_COOKIE, "", 0);
    setBrowserCookie(REMEMBERED_ID_COOKIE, "", 0);
    setRememberedName("");
    setLoginId("");
    setPassword("");
    window.requestAnimationFrame(() => document.getElementById("login-id")?.focus());
  }

  const returningName = firstName(rememberedName);
  const sessionExpired = searchParams.get("reason") === "session-expired";

  return (
    <main className="auth-shell">
      <section className="auth-card" aria-labelledby="login-title">
        <Link href="/" className="brand-mark"><i aria-hidden="true" /> Fortune Farms</Link>
        <p className="eyebrow">AGRO CEO · private farm command</p>
        <h1 id="login-title">{returningName ? `Welcome back, ${returningName}.` : "Your work, ready."}</h1>
        <p className="muted">{sessionExpired ? "Your session ended for your security. Sign in again to continue where you left off." : returningName ? "Enter your password to continue." : "Sign in with the AGRO CEO ID your farm admin gave you."}</p>
        <form onSubmit={submit} className="auth-form">
          <label htmlFor="login-id">AGRO CEO ID</label><input id="login-id" autoComplete="username" autoCapitalize="none" value={loginId} onChange={(event) => setLoginId(event.target.value)} required autoFocus={!loginId} />
          <label htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required autoFocus={Boolean(loginId)} />
          {status ? <p className="form-error" role="alert">{status}</p> : null}
          <button className="primary-action" disabled={submitting}>{submitting ? "Opening…" : "Sign in"} <span aria-hidden="true">→</span></button>
        </form>
        {returningName ? <button type="button" className="text-link auth-switch" onClick={useAnotherId}>Not {returningName}? Use another ID</button> : null}
        <p className="hindi" lang="hi">अपना एग्रो सीईओ आईडी और पासवर्ड डालें</p>
      </section>
    </main>
  );
}
