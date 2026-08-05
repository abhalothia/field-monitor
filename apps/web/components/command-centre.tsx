"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type View = "home" | "fields" | "farmers" | "actions" | "settings";
type Language = "en" | "hi";

type OperatingProfile = {
  display_name?: string;
  website_url?: string;
  coverage_label?: string;
  network_summary?: string;
  public_hub_label?: string;
  source_url?: string;
  map_embed_url?: string;
};

type LedgerItem = {
  severity: string;
  action: string;
  entity: { type: string; id: string };
  status: string;
  title: string;
  due_at?: string;
  observed_at?: string;
  allocation_id?: string;
  owner_id?: string;
  proof_required?: boolean;
};

type Portfolio = {
  as_of: string;
  scope: {
    active_farms: { count: number; items: Array<{ id: string; name: string; active_allocation_count: number }> };
    active_allocations: { count: number };
  };
  sources: { configured_count: number; attention: { total_count: number } };
  field_signals: { open: { total_count: number } };
  field_information_requests: { open: { total_count: number } };
  risk_action_ledger: { total_count: number; items: LedgerItem[] };
};

type Runtime = {
  operating_unit?: { id: string; name: string };
  people: Array<{ id: string; name: string; role: string }>;
  allocations: Array<{
    id: string;
    crop_name?: string;
    cultivar?: string | null;
    operational_block_name?: string;
    status: string;
  }>;
  work_items: Array<{ id: string; title: string; status: string; allocation_id?: string }>;
  exceptions: Array<{ id: string; title: string; severity?: string; status: string; allocation_id?: string }>;
  latest_field_update?: { operational_block_name?: string; crop_name?: string; submitted_by?: string; observed_at?: string } | null;
};

type DataLane = { key?: string; label?: string; status?: string; detail?: string; next_step?: string };
type DataLanes = { lanes?: DataLane[] };
type ManagerSession = { authenticated: boolean; expires_at?: string; auth_method?: string };
type FeatureCollection = { features?: Array<{ properties?: Record<string, unknown> }> };

type State = {
  profile: OperatingProfile | null;
  portfolio: Portfolio | null;
  runtime: Runtime | null;
  lanes: DataLanes | null;
  session: ManagerSession | null;
  map: FeatureCollection | null;
  loading: boolean;
  error: string | null;
  needsLaunchLogin: boolean;
};

const EMPTY_STATE: State = {
  profile: null,
  portfolio: null,
  runtime: null,
  lanes: null,
  session: null,
  map: null,
  loading: true,
  error: null,
  needsLaunchLogin: false,
};

type Translation = {
  home: string; fields: string; farmers: string; actions: string; settings: string;
  refresh: string; updated: string; loading: string; noData: string; open: string;
  fieldMap: string; programmeContext: string; notFieldMap: string; reviewedFields: string;
  people: string; nextMove: string; dataReadiness: string; unlock: string; lock: string;
  manager: string; signIn: string; signal: string; source: string; fieldUpdates: string;
  evidence: string; work: string; noActions: string; english: string; hindi: string;
  operator: string; farm: string; received: string;
  farmTruth: string;
};

const WORDS: Record<Language, Translation> = {
  en: {
    home: "Home", fields: "Fields", farmers: "Farmers", actions: "Actions", settings: "Settings",
    refresh: "Refresh", updated: "Updated", loading: "Reading the operating record…",
    noData: "Nothing has been verified here yet.", open: "Open", fieldMap: "Field map",
    programmeContext: "Programme context", notFieldMap: "This is public programme context, not a farm boundary.",
    reviewedFields: "Reviewed fields", people: "People", nextMove: "The next move", dataReadiness: "Data readiness",
    unlock: "Unlock manager actions", lock: "Lock manager actions", manager: "Manager access",
    signIn: "Sign in", signal: "signals", source: "sources", fieldUpdates: "field updates",
    evidence: "Proof required", work: "work", noActions: "No open actions need attention.",
    english: "EN", hindi: "हि", operator: "Field team", farm: "Farm", received: "Observed",
    farmTruth: "Farm Truth",
  },
  hi: {
    home: "होम", fields: "खेत", farmers: "किसान", actions: "काम", settings: "सेटिंग्स",
    refresh: "ताज़ा करें", updated: "अपडेट", loading: "रिकॉर्ड पढ़ा जा रहा है…",
    noData: "अभी यहां कोई सत्यापित जानकारी नहीं है।", open: "खुला", fieldMap: "खेत का नक्शा",
    programmeContext: "कार्यक्रम संदर्भ", notFieldMap: "यह सार्वजनिक कार्यक्रम संदर्भ है, खेत की सीमा नहीं।",
    reviewedFields: "सत्यापित खेत", people: "लोग", nextMove: "अगला कदम", dataReadiness: "डेटा की तैयारी",
    unlock: "मैनेजर कार्रवाइयां खोलें", lock: "मैनेजर कार्रवाइयां बंद करें", manager: "मैनेजर पहुंच",
    signIn: "साइन इन", signal: "संकेत", source: "स्रोत", fieldUpdates: "खेत अपडेट",
    evidence: "प्रमाण ज़रूरी", work: "काम", noActions: "ध्यान देने वाला कोई खुला काम नहीं है।",
    english: "EN", hindi: "हि", operator: "फील्ड टीम", farm: "फार्म", received: "देखा गया",
    farmTruth: "खेत सत्य",
  },
};

const NAV: Array<{ view: View; href: string }> = [
  { view: "home", href: "/home" },
  { view: "fields", href: "/fields" },
  { view: "farmers", href: "/farmers" },
  { view: "actions", href: "/actions" },
  { view: "settings", href: "/settings" },
];

async function readJson<T>(url: string): Promise<{ value: T; response: Response }> {
  const response = await fetch(url, { credentials: "same-origin", cache: "no-store" });
  if (!response.ok) {
    const error = new Error("The operating record is unavailable.") as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return { value: (await response.json()) as T, response };
}

function count(value?: number) {
  return new Intl.NumberFormat("en-IN").format(value || 0);
}

function dateTime(value?: string) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "—" : new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" }).format(date);
}

function roleName(role: string) {
  return role.replaceAll("_", " ");
}

function isFarmer(role: string) {
  return /farmer|grower/i.test(role);
}

export function CommandCentre({ view }: { view: View }) {
  const [language, setLanguage] = useState<Language>("en");
  const [state, setState] = useState<State>(EMPTY_STATE);
  const [managerSecret, setManagerSecret] = useState("");
  const [managerBusy, setManagerBusy] = useState(false);
  const [managerError, setManagerError] = useState<string | null>(null);
  const t = WORDS[language];

  const load = useCallback(async () => {
    setState((current) => ({ ...current, loading: true, error: null }));
    const results = await Promise.allSettled([
      readJson<OperatingProfile>("/api/v1/operating-profile"),
      readJson<Portfolio>("/api/v1/portfolio"),
      readJson<Runtime>("/api/v1/runtime"),
      readJson<DataLanes>("/api/v1/data-lanes"),
      readJson<ManagerSession>("/api/v1/manager-session/status"),
    ]);
    const rejected = results.find((result): result is PromiseRejectedResult => result.status === "rejected");
    const status = rejected?.reason?.status;
    if (status === 401 || status === 503) {
      setState((current) => ({ ...current, loading: false, needsLaunchLogin: true }));
      return;
    }
    setState({
      profile: results[0].status === "fulfilled" ? results[0].value.value : null,
      portfolio: results[1].status === "fulfilled" ? results[1].value.value : null,
      runtime: results[2].status === "fulfilled" ? results[2].value.value : null,
      lanes: results[3].status === "fulfilled" ? results[3].value.value : null,
      session: results[4].status === "fulfilled" ? results[4].value.value : null,
      map: null,
      loading: false,
      needsLaunchLogin: false,
      error: rejected ? "Some current operating data could not be read. Nothing has been estimated." : null,
    });
  }, []);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!state.session?.authenticated) return;
    let active = true;
    void readJson<FeatureCollection>("/api/v1/fortune-map")
      .then(({ value }) => { if (active) setState((current) => ({ ...current, map: value })); })
      .catch(() => { if (active) setState((current) => ({ ...current, map: null })); });
    return () => { active = false; };
  }, [state.session?.authenticated]);

  const farmers = useMemo(() => state.runtime?.people.filter((person) => isFarmer(person.role)) || [], [state.runtime]);
  const team = useMemo(() => state.runtime?.people.filter((person) => !isFarmer(person.role)) || [], [state.runtime]);

  async function submitManagerSession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setManagerBusy(true);
    setManagerError(null);
    try {
      const response = await fetch("/api/v1/manager-session/login", {
        method: "POST", credentials: "same-origin", headers: { "content-type": "application/json" },
        body: JSON.stringify({ secret: managerSecret }),
      });
      if (!response.ok) throw new Error("That manager secret was not accepted.");
      setManagerSecret("");
      await load();
    } catch (error) {
      setManagerError(error instanceof Error ? error.message : "Manager access could not be opened.");
    } finally {
      setManagerBusy(false);
    }
  }

  async function endManagerSession() {
    setManagerBusy(true);
    try {
      await fetch("/api/v1/manager-session/logout", { method: "POST", credentials: "same-origin" });
      await load();
    } finally {
      setManagerBusy(false);
    }
  }

  if (state.needsLaunchLogin) {
    return (
      <main className="session-wall">
        <section className="session-wall-card"><p className="eyebrow">AGRO CEO</p><h1>This workspace is private.</h1><p>Sign in with the pilot password to read the live operating record.</p><Link href={`/login?next=/${view}`} className="primary-action">{t.signIn} <span aria-hidden="true">→</span></Link></section>
      </main>
    );
  }

  return (
    <main className="command-shell">
      <header className="command-header">
        <Link className="brand-mark" href="/home"><i aria-hidden="true" /> AGRO CEO</Link>
        <nav className="command-nav" aria-label="AGRO CEO views">
          {NAV.map((item) => <Link key={item.view} href={item.href} aria-current={item.view === view ? "page" : undefined} className={item.view === view ? "nav-link active" : "nav-link"}>{t[item.view]}</Link>)}
        </nav>
        <div className="command-tools">
          {state.session?.authenticated ? <a href="/manager" className="quiet-button">{t.farmTruth}</a> : null}
          <button type="button" className="language-toggle" onClick={() => setLanguage((current) => current === "en" ? "hi" : "en")} aria-label="Switch interface language">{language === "en" ? t.hindi : t.english}</button>
          <button type="button" className="quiet-button" onClick={() => void load()} disabled={state.loading}>{state.loading ? t.loading : t.refresh}</button>
        </div>
      </header>

      <section className="command-intro">
        <div>
          <p className="eyebrow">{state.profile?.coverage_label || "Fortune Farms"}</p>
          <h1>{headingFor(view, t)}</h1>
        </div>
        <p>{state.loading ? t.loading : state.portfolio?.as_of ? `${t.updated} ${dateTime(state.portfolio.as_of)} IST` : ""}</p>
      </section>

      {state.error ? <p className="honest-notice" role="status">{state.error}</p> : null}
      {view === "home" ? <HomeView t={t} state={state} /> : null}
      {view === "fields" ? <FieldsView t={t} state={state} /> : null}
      {view === "farmers" ? <FarmersView t={t} farmers={farmers} team={team} /> : null}
      {view === "actions" ? <ActionsView t={t} portfolio={state.portfolio} /> : null}
      {view === "settings" ? <SettingsView t={t} state={state} managerSecret={managerSecret} setManagerSecret={setManagerSecret} managerBusy={managerBusy} managerError={managerError} submit={submitManagerSession} logout={endManagerSession} /> : null}
    </main>
  );
}

function headingFor(view: View, t: Translation) {
  return ({ home: "Today, in the field.", fields: t.reviewedFields, farmers: t.people, actions: t.nextMove, settings: t.settings })[view];
}

function HomeView({ t, state }: { t: Translation; state: State }) {
  const portfolio = state.portfolio;
  const runtime = state.runtime;
  const nextMove = portfolio?.risk_action_ledger.items[0];
  return <>
    <section className="hero-grid">
      <article className="today-card">
        <p className="eyebrow">{runtime?.operating_unit?.name || state.profile?.display_name || "Fortune Farms"}</p>
        <h2>{nextMove ? nextMove.title : "Start with the operating record."}</h2>
        <p>{nextMove ? actionLine(nextMove) : "Add reviewed fields, people, and work. AGRO CEO will keep the next move visible."}</p>
        {nextMove ? <Link href="/actions" className="primary-action">Open next move <span aria-hidden="true">→</span></Link> : <Link href="/settings" className="primary-action">Open setup <span aria-hidden="true">→</span></Link>}
      </article>
      <article className="programme-card">
        <p className="eyebrow">{t.programmeContext}</p>
        <strong>{state.profile?.network_summary || "The operating network will appear here once the private setup is accepted."}</strong>
        <p>{state.profile?.public_hub_label || "No public location context is configured."}</p>
        {state.profile?.source_url ? <a href={state.profile.source_url} target="_blank" rel="noreferrer" className="text-link">Source context <span aria-hidden="true">↗</span></a> : null}
      </article>
    </section>
    <section className="metric-grid" aria-label="Operating truths">
      <Metric label={t.farm} value={count(portfolio?.scope.active_farms.count)} note="reviewed operating farms" />
      <Metric label={t.reviewedFields} value={count(portfolio?.scope.active_allocations.count)} note="active crop allocations" />
      <Metric label={t.open} value={count(portfolio?.risk_action_ledger.total_count)} note="owned actions" tone="attention" />
      <Metric label={t.fieldUpdates} value={count(portfolio?.field_signals.open.total_count)} note="awaiting review" />
    </section>
    <section className="home-lower-grid">
      <PublicContextMap profile={state.profile} t={t} />
      <article className="surface action-preview">
        <div className="surface-heading"><div><p className="eyebrow">{t.nextMove}</p><h2>Keep ownership visible.</h2></div><Link className="text-link" href="/actions">All actions <span aria-hidden="true">→</span></Link></div>
        <ActionRows items={portfolio?.risk_action_ledger.items.slice(0, 4) || []} empty={t.noActions} />
      </article>
    </section>
  </>;
}

function Metric({ label, value, note, tone }: { label: string; value: string; note: string; tone?: "attention" }) {
  return <article className={`metric-card${tone ? ` ${tone}` : ""}`}><p>{label}</p><strong>{value}</strong><span>{note}</span></article>;
}

function FieldsView({ t, state }: { t: Translation; state: State }) {
  const fields = state.runtime?.allocations || [];
  const verifiedFeatures = state.map?.features || [];
  return <>
    <section className="surface field-map-surface">
      <div className="surface-heading"><div><p className="eyebrow">{t.fieldMap}</p><h2>Only reviewed geometry belongs here.</h2></div><span className="count-badge">{count(verifiedFeatures.length)} mapped</span></div>
      {state.session?.authenticated ? <ReviewedGeometry features={verifiedFeatures} /> : <div className="map-locked"><p>Unlock manager actions in Settings to view reviewed field geometry.</p><Link href="/settings" className="text-link">Open settings <span aria-hidden="true">→</span></Link></div>}
    </section>
    <section className="section-heading"><div><p className="eyebrow">{t.reviewedFields}</p><h2>Current crop allocations</h2></div><p>{fields.length ? "Each card comes from the operating record." : "A source village or coverage count never becomes a field record."}</p></section>
    {fields.length ? <div className="field-card-grid">{fields.map((field) => <article className="field-card" key={field.id}><span className="status-chip">{field.status}</span><h3>{field.operational_block_name || "Reviewed field"}</h3><p>{field.crop_name || "Crop not set"}{field.cultivar ? ` · ${field.cultivar}` : ""}</p><Link className="text-link" href={`/actions?field=${encodeURIComponent(field.id)}`}>View related actions <span aria-hidden="true">→</span></Link></article>)}</div> : <EmptyState title={t.noData} detail="Accept a reviewed farm candidate or publish a farm manifest to make a real field visible." />}
  </>;
}

function ReviewedGeometry({ features }: { features: Array<{ properties?: Record<string, unknown> }> }) {
  if (!features.length) return <div className="map-empty"><strong>No reviewed field geometry yet.</strong><p>AGRO CEO will not draw an inferred boundary or put a programme location on this map.</p></div>;
  return <div className="geometry-list"><p>{features.length} reviewed feature{features.length === 1 ? "" : "s"} are available to the manager map.</p>{features.slice(0, 8).map((feature, index) => <span key={`${String(feature.properties?.plot_label || "field")}-${index}`}>{String(feature.properties?.plot_label || "Reviewed field")}</span>)}</div>;
}

function FarmersView({ t, farmers, team }: { t: Translation; farmers: Runtime["people"]; team: Runtime["people"] }) {
  return <div className="people-layout">
    <PeopleSection title={t.farmers} eyebrow="Reviewed people" people={farmers} empty="No reviewed farmer relationships are available yet." />
    <PeopleSection title={t.operator} eyebrow="Reviewed people" people={team} empty="No field-team relationships are available yet." />
  </div>;
}

function PeopleSection({ title, eyebrow, people, empty }: { title: string; eyebrow: string; people: Runtime["people"]; empty: string }) {
  return <section className="surface"><div className="surface-heading"><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2></div><span className="count-badge">{count(people.length)}</span></div>{people.length ? <div className="people-list">{people.map((person) => <article className="person-row" key={person.id}><span className="person-initial">{person.name.slice(0, 1).toUpperCase()}</span><div><h3>{person.name}</h3><p>{roleName(person.role)}</p></div></article>)}</div> : <p className="empty-copy">{empty}</p>}</section>;
}

function ActionsView({ t, portfolio }: { t: Translation; portfolio: Portfolio | null }) {
  const actions = portfolio?.risk_action_ledger.items || [];
  return <section className="surface actions-surface"><div className="surface-heading"><div><p className="eyebrow">Decision queue</p><h2>One clear list. No hidden work.</h2></div><span className="count-badge">{count(portfolio?.risk_action_ledger.total_count)}</span></div><ActionRows items={actions} empty={t.noActions} /></section>;
}

function ActionRows({ items, empty }: { items: LedgerItem[]; empty: string }) {
  if (!items.length) return <p className="empty-copy">{empty}</p>;
  return <ol className="action-list">{items.map((item) => <li key={`${item.entity.type}-${item.entity.id}`}><span className={`severity ${item.severity}`}>{item.severity}</span><div><h3>{item.title}</h3><p>{actionLine(item)}</p></div><Link className="text-link" href={item.allocation_id ? `/fields?field=${encodeURIComponent(item.allocation_id)}` : "/actions"}>Open <span aria-hidden="true">→</span></Link></li>)}</ol>;
}

function SettingsView({ t, state, managerSecret, setManagerSecret, managerBusy, managerError, submit, logout }: {
  t: Translation; state: State; managerSecret: string; setManagerSecret: (value: string) => void; managerBusy: boolean; managerError: string | null; submit: (event: FormEvent<HTMLFormElement>) => Promise<void>; logout: () => Promise<void>;
}) {
  const session = state.session;
  const lanes = state.lanes?.lanes || [];
  return <div className="settings-grid">
    <section className="surface"><p className="eyebrow">{t.manager}</p><h2>{session?.authenticated ? "Manager actions are available." : "Manager actions are locked."}</h2><p className="surface-copy">The manager secret is submitted only to the operating kernel. It is never saved in this browser.</p>{session?.authenticated ? <><p className="session-note">Expires {dateTime(session.expires_at)} IST</p><button className="quiet-button" type="button" disabled={managerBusy} onClick={() => void logout()}>{t.lock}</button></> : <form className="manager-form" onSubmit={submit}><label htmlFor="manager-secret">Manager secret</label><input id="manager-secret" type="password" autoComplete="off" value={managerSecret} onChange={(event) => setManagerSecret(event.target.value)} required /><button className="primary-action" disabled={managerBusy}>{managerBusy ? "Opening…" : t.unlock}</button>{managerError ? <p className="form-error" role="alert">{managerError}</p> : null}</form>}</section>
    <section className="surface"><p className="eyebrow">Fortune Farms</p><h2>{state.profile?.display_name || "Operating profile"}</h2><p className="surface-copy">{state.profile?.coverage_label || "No operating profile has been published."}</p>{state.profile?.website_url ? <a className="text-link" href={state.profile.website_url} target="_blank" rel="noreferrer">Fortune Rice website <span aria-hidden="true">↗</span></a> : null}</section>
    <section className="surface full-span"><div className="surface-heading"><div><p className="eyebrow">{t.dataReadiness}</p><h2>Connections are explicit.</h2></div></div>{lanes.length ? <ul className="lane-list">{lanes.map((lane, index) => <li key={lane.key || index}><span className={`status-dot ${lane.status || "unknown"}`} /><div><strong>{lane.label || lane.key || "Data lane"}</strong><p>{lane.detail || lane.next_step || "No additional detail is available."}</p></div><span>{lane.status || "unknown"}</span></li>)}</ul> : <p className="empty-copy">No data connections are configured yet. This is intentional until a source is reviewed and enabled.</p>}</section>
  </div>;
}

function PublicContextMap({ profile, t }: { profile: OperatingProfile | null; t: Translation }) {
  return <article className="surface map-context-card"><div className="surface-heading"><div><p className="eyebrow">{t.programmeContext}</p><h2>Where the programme operates.</h2></div></div>{profile?.map_embed_url ? <iframe src={profile.map_embed_url} title="Public programme location context" loading="lazy" referrerPolicy="no-referrer" /> : <div className="map-empty"><strong>No public programme map is configured.</strong></div>}<p className="map-caption">{t.notFieldMap}</p></article>;
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return <section className="empty-state"><strong>{title}</strong><p>{detail}</p></section>;
}

function actionLine(item: LedgerItem) {
  const when = item.due_at || item.observed_at;
  const timing = when ? ` · ${dateTime(when)} IST` : "";
  return `${item.status.replaceAll("_", " ")}${item.proof_required ? " · proof required" : ""}${timing}`;
}
