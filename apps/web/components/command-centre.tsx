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
type PilotStage = { key: string; title: string; status: "ready" | "not_started"; next_action: string };
type PilotReadiness = {
  overall: "not_started" | "in_setup" | "ready_for_field_loop";
  progress: { completed: number; total: number };
  next_stage?: PilotStage | null;
  stages: PilotStage[];
  counts: { people: number; operating_units: number; active_allocations: number; open_work_items: number };
};
type WhatsAppReadiness = {
  status: "ready" | "blocked";
  live_inbound_eligible: boolean;
  live_outbound_eligible: boolean;
  gaps: string[];
};
type PasswordIdentitySummary = {
  id: string;
  person_id: string;
  person_name: string;
  login_id: string;
  access_role: "owner" | "admin" | "field_worker" | "farmer";
  identity_status: "active" | "suspended";
};

type State = {
  profile: OperatingProfile | null;
  portfolio: Portfolio | null;
  runtime: Runtime | null;
  lanes: DataLanes | null;
  session: ManagerSession | null;
  map: FeatureCollection | null;
  readiness: PilotReadiness | null;
  communications: WhatsAppReadiness | null;
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
  readiness: null,
  communications: null,
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
      readJson<PilotReadiness>("/api/v1/pilot/readiness"),
    ]);
    const runtimeIsAwaitingFirstFarm = results[2].status === "rejected" && results[2].reason?.status === 404;
    const rejected = results.find((result, index): result is PromiseRejectedResult => (
      result.status === "rejected" && !(index === 2 && runtimeIsAwaitingFirstFarm)
    ));
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
      readiness: results[5].status === "fulfilled" ? results[5].value.value : null,
      communications: null,
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

  useEffect(() => {
    if (!state.session?.authenticated) {
      setState((current) => ({ ...current, communications: null }));
      return;
    }
    let active = true;
    void readJson<WhatsAppReadiness>("/api/v1/communications/readiness")
      .then(({ value }) => { if (active) setState((current) => ({ ...current, communications: value })); })
      .catch(() => { if (active) setState((current) => ({ ...current, communications: null })); });
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
      {view === "farmers" ? <FarmersView farmers={farmers} team={team} readiness={state.readiness} /> : null}
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
  const readiness = state.readiness;
  const nextMove = portfolio?.risk_action_ledger.items[0];
  const firstTruth = readiness?.next_stage;
  const statusLine = nextMove
    ? `${count(portfolio?.risk_action_ledger.total_count)} open action${portfolio?.risk_action_ledger.total_count === 1 ? "" : "s"}`
    : readiness ? `${readiness.progress.completed} of ${readiness.progress.total} setup checks complete` : "Reading the operating record";
  return <section className="single-stage home-stage">
    <p className="eyebrow">{nextMove ? "One next move" : "Start here"}</p>
    <h2>{nextMove ? nextMove.title : firstTruth?.title || "Add the first reviewed farm."}</h2>
    <p>{nextMove ? actionLine(nextMove) : firstTruth?.next_action || "The command centre only begins when the actual operating unit is confirmed."}</p>
    {nextMove
      ? <Link href="/actions" className="primary-action">Open action <span aria-hidden="true">→</span></Link>
      : <Link href="/settings" className="primary-action">Set up the first farm <span aria-hidden="true">→</span></Link>}
    <footer>{statusLine} · {state.profile?.display_name || "Fortune Farms"}</footer>
  </section>;
}

function FieldsView({ t, state }: { t: Translation; state: State }) {
  const fields = state.runtime?.allocations || [];
  const verifiedFeatures = state.map?.features || [];
  const waitingForFarm = state.readiness?.counts.operating_units === 0;
  return <section className="single-surface fields-stage">
    <div className="surface-heading"><div><p className="eyebrow">{t.fieldMap}</p><h2>{fields.length ? "Reviewed fields" : "No field has been claimed yet."}</h2></div><span className="count-badge">{count(fields.length)}</span></div>
    {fields.length ? <div className="field-card-grid">{fields.map((field) => <article className="field-card" key={field.id}><span className="status-chip">{field.status}</span><h3>{field.operational_block_name || "Reviewed field"}</h3><p>{field.crop_name || "Crop not set"}{field.cultivar ? ` · ${field.cultivar}` : ""}</p><Link className="text-link" href={`/actions?field=${encodeURIComponent(field.id)}`}>View work <span aria-hidden="true">→</span></Link></article>)}</div> : <EmptyState title={waitingForFarm ? "Add one real field." : t.noData} detail={waitingForFarm ? "A village, public map, or purchase row is not enough. Confirm the operating unit and field pack first." : "Publish a reviewed farm record to make a field visible."} />}
    {state.session?.authenticated && verifiedFeatures.length ? <ReviewedGeometry features={verifiedFeatures} /> : null}
  </section>;
}

function ReviewedGeometry({ features }: { features: Array<{ properties?: Record<string, unknown> }> }) {
  if (!features.length) return <div className="map-empty"><strong>No reviewed field geometry yet.</strong><p>AGRO CEO will not draw an inferred boundary or put a programme location on this map.</p></div>;
  return <div className="geometry-list"><p>{features.length} reviewed feature{features.length === 1 ? "" : "s"} are available to the manager map.</p>{features.slice(0, 8).map((feature, index) => <span key={`${String(feature.properties?.plot_label || "field")}-${index}`}>{String(feature.properties?.plot_label || "Reviewed field")}</span>)}</div>;
}

function FarmersView({ farmers, team, readiness }: { farmers: Runtime["people"]; team: Runtime["people"]; readiness: PilotReadiness | null }) {
  const people = [...farmers, ...team];
  return <section className="single-surface people-stage">
    <div className="surface-heading"><div><p className="eyebrow">Reviewed people</p><h2>People on this operating record</h2></div><span className="count-badge">{count(people.length)}</span></div>
    {people.length ? <div className="people-list">{people.map((person) => <article className="person-row" key={person.id}><span className="person-initial">{person.name.slice(0, 1).toUpperCase()}</span><div><h3>{person.name}</h3><p>{roleName(person.role)}</p></div></article>)}</div> : <p className="empty-copy">{readiness?.counts.people ? "A team record exists, but it is not attached to an operating farm yet." : "People appear here only after a reviewed relationship is recorded."}</p>}
  </section>;
}

function ActionsView({ t, portfolio }: { t: Translation; portfolio: Portfolio | null }) {
  const actions = portfolio?.risk_action_ledger.items || [];
  return <section className="single-surface actions-surface"><div className="surface-heading"><div><p className="eyebrow">Decision queue</p><h2>Open actions</h2></div><span className="count-badge">{count(portfolio?.risk_action_ledger.total_count)}</span></div><ActionRows items={actions} empty={t.noActions} /></section>;
}

function ActionRows({ items, empty }: { items: LedgerItem[]; empty: string }) {
  if (!items.length) return <p className="empty-copy">{empty}</p>;
  return <ol className="action-list">{items.map((item) => <li key={`${item.entity.type}-${item.entity.id}`}><span className={`severity ${item.severity}`}>{item.severity}</span><div><h3>{item.title}</h3><p>{actionLine(item)}</p></div><Link className="text-link" href={item.allocation_id ? `/fields?field=${encodeURIComponent(item.allocation_id)}` : "/actions"}>Open <span aria-hidden="true">→</span></Link></li>)}</ol>;
}

function SettingsView({ t, state, managerSecret, setManagerSecret, managerBusy, managerError, submit, logout }: {
  t: Translation; state: State; managerSecret: string; setManagerSecret: (value: string) => void; managerBusy: boolean; managerError: string | null; submit: (event: FormEvent<HTMLFormElement>) => Promise<void>; logout: () => Promise<void>;
}) {
  const session = state.session;
  const communications = state.communications;
  return <section className="single-surface settings-stage">
    <div className="surface-heading"><div><p className="eyebrow">Private setup</p><h2>Access and connections</h2></div></div>
    <p className="surface-copy">{state.profile?.display_name || "Fortune Farms"} stays private until a named person is given the exact access they need.</p>
    <div className="settings-rows">
      <div><strong>People</strong><span>{session?.authenticated ? "Manage named ID access below." : "Use your admin ID to manage access."}</span></div>
      <div><strong>Data</strong><span>{state.readiness ? `${state.readiness.progress.completed} of ${state.readiness.progress.total} first records are confirmed.` : "Not available."}</span></div>
      <div><strong>Messaging</strong><span>{communications?.status === "ready" ? "Ready for reviewed requests." : "Paused until the dedicated WhatsApp gate is complete."}</span></div>
    </div>
    {session?.authenticated ? <><PasswordChanger /><AccountManager /><div className="settings-actions"><a className="text-link" href="/manager">Open Farm Truth <span aria-hidden="true">→</span></a><button className="quiet-button" type="button" disabled={managerBusy} onClick={() => void logout()}>{t.lock}</button></div></> : <details className="bootstrap-access"><summary>Use temporary admin setup access</summary><form className="manager-form" onSubmit={submit}><label htmlFor="manager-secret">Manager setup secret</label><input id="manager-secret" type="password" autoComplete="off" value={managerSecret} onChange={(event) => setManagerSecret(event.target.value)} required /><button className="primary-action" disabled={managerBusy}>{managerBusy ? "Opening…" : t.unlock}</button>{managerError ? <p className="form-error" role="alert">{managerError}</p> : null}</form></details>}
  </section>;
}

function PasswordChanger() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submitPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setStatus(null);
    try {
      const response = await fetch("/api/v1/identity/password", {
        method: "POST", credentials: "same-origin", headers: { "content-type": "application/json" },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
      if (!response.ok) throw new Error(payload?.detail || "Password could not be changed.");
      setCurrentPassword(""); setNewPassword(""); setStatus("Password changed.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Password could not be changed.");
    } finally { setBusy(false); }
  }

  return <details className="password-changer">
    <summary>Change my password</summary>
    <form className="account-form" onSubmit={submitPassword}>
      <label htmlFor="current-password">Current password<input id="current-password" type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required /></label>
      <label htmlFor="new-password">New password<input id="new-password" type="password" autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} minLength={12} required /></label>
      <button className="primary-action" disabled={busy}>{busy ? "Changing…" : "Change password"} <span aria-hidden="true">→</span></button>
    </form>
    {status ? <p className="form-error" role="status">{status}</p> : null}
  </details>;
}

function AccountManager() {
  const [accounts, setAccounts] = useState<PasswordIdentitySummary[] | null>(null);
  const [name, setName] = useState("");
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<PasswordIdentitySummary["access_role"]>("field_worker");
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadAccounts = useCallback(async () => {
    const response = await fetch("/api/v1/identities", { credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error("Accounts could not be read.");
    const payload = (await response.json()) as { items: PasswordIdentitySummary[] };
    setAccounts(payload.items);
  }, []);

  useEffect(() => { void loadAccounts().catch((error: unknown) => setStatus(error instanceof Error ? error.message : "Accounts could not be read.")); }, [loadAccounts]);

  async function submitAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setStatus(null);
    try {
      const response = await fetch("/api/v1/identities", {
        method: "POST", credentials: "same-origin", headers: { "content-type": "application/json" },
        body: JSON.stringify({
          access_role: role, login_id: loginId, temporary_password: password, person_name: name,
          operational_role: role === "farmer" ? "grower" : role === "field_worker" ? "field_operator" : "operations_lead",
        }),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail || "That account could not be created.");
      }
      setName(""); setLoginId(""); setPassword("");
      setStatus("Account created. Share the temporary password directly; it will not be shown again.");
      await loadAccounts();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "That account could not be created.");
    } finally {
      setBusy(false);
    }
  }

  return <details className="account-manager">
    <summary>Manage named sign-ins</summary>
    <p className="surface-copy">Create access only for a person you have deliberately confirmed. A source contact, village, or purchase row never creates a login.</p>
    <form className="account-form" onSubmit={submitAccount}>
      <label htmlFor="account-name">Name<input id="account-name" value={name} onChange={(event) => setName(event.target.value)} required /></label>
      <label htmlFor="account-id">Login ID<input id="account-id" value={loginId} onChange={(event) => setLoginId(event.target.value)} placeholder="e.g. ravi.grower" autoCapitalize="none" required /></label>
      <label htmlFor="account-role">Access<select id="account-role" value={role} onChange={(event) => setRole(event.target.value as PasswordIdentitySummary["access_role"])}><option value="field_worker">Field worker</option><option value="farmer">Farmer</option><option value="admin">Admin</option><option value="owner">Owner</option></select></label>
      <label htmlFor="account-password">Temporary password<input id="account-password" type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={12} required /></label>
      <button className="primary-action" disabled={busy}>{busy ? "Creating…" : "Create sign-in"} <span aria-hidden="true">→</span></button>
    </form>
    {status ? <p className="form-error" role="status">{status}</p> : null}
    {accounts ? <ul className="account-list">{accounts.map((account) => <li key={account.id}><span>{account.person_name}</span><span>{account.login_id}</span><span>{account.access_role.replaceAll("_", " ")}</span></li>)}</ul> : <p className="empty-copy">Reading named accounts…</p>}
  </details>;
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return <section className="empty-state"><strong>{title}</strong><p>{detail}</p></section>;
}

function actionLine(item: LedgerItem) {
  const when = item.due_at || item.observed_at;
  const timing = when ? ` · ${dateTime(when)} IST` : "";
  return `${item.status.replaceAll("_", " ")}${item.proof_required ? " · proof required" : ""}${timing}`;
}
