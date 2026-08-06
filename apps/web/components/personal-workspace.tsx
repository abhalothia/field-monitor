"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type Role = "field_worker" | "farmer";
type Session = { authenticated: boolean; person_name: string; access_role: Role; next_path: string };
type Overview = {
  person: { name: string; role: Role };
  work: Array<{ id: string; title: string; status: string; due_at: string; field_name: string; crop_name: string }>;
  requests: Array<{ id: string; request_kind: string; evidence_required: boolean; status: string; due_at: string; field_name: string; crop_name: string }>;
};

function dateLine(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "Due date to be confirmed" : new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" }).format(date);
}

export function PersonalWorkspace({ expectedRole }: { expectedRole: Role }) {
  const router = useRouter();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [status, setStatus] = useState("Loading your work…");

  useEffect(() => {
    let active = true;
    void Promise.all([
      fetch("/api/v1/identity/session", { credentials: "same-origin", cache: "no-store" }),
      fetch("/api/v1/my/overview", { credentials: "same-origin", cache: "no-store" }),
    ]).then(async ([sessionResponse, overviewResponse]) => {
      if (!active) return;
      if (!sessionResponse.ok || !overviewResponse.ok) {
        router.replace("/login");
        return;
      }
      const session = (await sessionResponse.json()) as Session;
      if (session.access_role !== expectedRole) {
        router.replace(session.next_path);
        return;
      }
      setOverview((await overviewResponse.json()) as Overview);
      setStatus("");
    }).catch(() => { if (active) setStatus("Your work is unavailable right now. Please try again shortly."); });
    return () => { active = false; };
  }, [expectedRole, router]);

  const title = expectedRole === "field_worker" ? "Today’s field work" : "Your farm updates";
  const primary = overview?.requests[0];
  const ownedWork = overview?.work[0];
  const item = primary || ownedWork;

  return <main className="personal-shell">
    <header className="personal-header"><Link href="/" className="brand-mark"><i aria-hidden="true" /> AGRO CEO</Link><span>{expectedRole === "field_worker" ? "Field team" : "Farmer"}</span></header>
    <section className="personal-stage">
      <p className="eyebrow">{overview?.person.name || "Your AGRO CEO"}</p>
      <h1>{title}</h1>
      {status ? <p className="muted">{status}</p> : null}
      {!status && !item ? <><p className="personal-empty">Nothing is assigned right now.</p><p className="muted">When your farm team needs a specific update, it will appear here with the field and due time.</p></> : null}
      {!status && item ? <article className="personal-item"><p className="eyebrow">{primary ? primary.request_kind.replaceAll("_", " ") : "Assigned work"}</p><h2>{primary ? `${primary.field_name} · ${primary.crop_name}` : ownedWork?.title}</h2><p>{primary?.evidence_required ? "Photo or proof will be requested through the approved field flow." : "Open the approved field flow to record this update."}</p><footer>Due {dateLine(item.due_at)}</footer></article> : null}
    </section>
  </main>;
}
