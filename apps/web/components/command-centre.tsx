"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

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
    operational_block_id: string;
    crop_name?: string;
    cultivar?: string | null;
    operational_block_name?: string;
    status: string;
  }>;
  reviewed_farms: Array<{ id: string; name: string }>;
  work_items: Array<{ id: string; title: string; status: string; allocation_id?: string }>;
  exceptions: Array<{ id: string; title: string; severity?: string; status: string; allocation_id?: string }>;
  person_operating_relationships?: {
    availability: string;
    items: Array<{ person_id: string; role: string; scope_type: string; starts_on: string; scope_name?: string | null }>;
  };
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
type TrackwickFarm = {
  id: string;
  farmer_name: string;
  place: string;
  reported_area_acres?: number | null;
  reported_plot_count?: number | null;
  open_work: number;
  latest_activity_at?: string | null;
  crop_photo_references: number;
  plot_photo_references: number;
};
type TrackwickFarmer = {
  id: string;
  name: string;
  tag?: string | null;
  farm_candidates: number;
  reported_area_acres?: number | null;
  open_work: number;
  latest_activity_at?: string | null;
  crop_photo_references: number;
};
type TrackwickWork = {
  id: string;
  task_type: string;
  status: string;
  farmer_name?: string | null;
  follow_up_at?: string | null;
  opened_at?: string | null;
};
type TrackwickBoard = {
  source: { state: string; last_synced_at?: string | null };
  counts: {
    farmers: number;
    farm_candidates: number;
    open_work: number;
    crop_photo_references: number;
    plot_photo_references: number;
  };
  farms: TrackwickFarm[];
  farmers: TrackwickFarmer[];
  inbox: TrackwickWork[];
};
type ReviewedFarmCard = {
  id: string;
  name: string;
  status: string;
  crops: string[];
};
type ReviewedFarmerCard = {
  id: string;
  name: string;
  relationshipRoles: string[];
};
type ProcurementHistory = {
  state: "not_loaded" | "published";
  summary?: {
    counters: { cohorts: number; input_source_rows: number; accepted_source_rows: number };
    coverage: { months: string[]; villages: number; varieties: number; quantity_qtl: number; weighted_rate_per_qtl?: number | null };
  };
};
type PasswordIdentitySummary = {
  id: string;
  person_id: string;
  person_name: string;
  login_id: string;
  access_role: "owner" | "admin" | "field_worker" | "farmer";
  identity_status: "active" | "suspended";
};

type FarmProfile = {
  state: "reviewed" | "reported";
  kind: "farm";
  id: string;
  name: string;
  current?: { crop_name: string; cultivar?: string | null } | null;
  people?: Array<{ id: string; name: string; role: string; starts_on: string }>;
  work?: Array<{ id: string; title: string; due_at?: string | null; status: string }>;
  open_work_count?: number;
  location?: { state: string };
  record?: { latest_observed_at?: string | null; limitation: string };
  reported?: {
    farmer_name?: string;
    place?: string;
    registration_status?: string | null;
    reported_area_acres?: number | null;
    reported_plot_count?: number | null;
    open_work?: number;
    latest_activity_at?: string | null;
    plot_photo_references?: number;
    crop_photo_references?: number;
  };
  limitations?: string[];
};

type FarmerProfile = {
  state: "reviewed" | "reported";
  kind: "farmer";
  id: string;
  name: string;
  relationships?: Array<{ scope_type: string; scope_name: string; role: string; starts_on: string }>;
  farms?: Array<{
    id: string;
    name: string;
    current?: { crop_name: string; cultivar?: string | null } | null;
    open_work_count: number;
  }>;
  reported?: {
    farm_candidates?: number;
    reported_area_acres?: number | null;
    open_work?: number;
    latest_activity_at?: string | null;
    crop_photo_references?: number;
  };
  account?: { state: "not_created" };
  limitations?: string[];
};

type ProfileSelection = {
  kind: FarmProfile["kind"] | FarmerProfile["kind"];
  loading: boolean;
  error: string | null;
  profile: FarmProfile | FarmerProfile | null;
  reauth?: boolean;
};

type State = {
  profile: OperatingProfile | null;
  portfolio: Portfolio | null;
  runtime: Runtime | null;
  lanes: DataLanes | null;
  session: ManagerSession | null;
  map: FeatureCollection | null;
  readiness: PilotReadiness | null;
  trackwick: TrackwickBoard | null;
  procurementHistory: ProcurementHistory | null;
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
  trackwick: null,
  procurementHistory: null,
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

function dateTime(value?: string | null) {
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

function reviewedFarmsFromRuntime(runtime: Runtime | null) {
  const farms = new Map<string, ReviewedFarmCard>();
  for (const farm of runtime?.reviewed_farms || []) {
    farms.set(farm.id, { id: farm.id, name: farm.name, status: "reviewed", crops: [] });
  }
  for (const allocation of runtime?.allocations || []) {
    const id = allocation.operational_block_id;
    if (!id) continue;
    const crop = `${allocation.crop_name || "Crop not set"}${allocation.cultivar ? ` · ${allocation.cultivar}` : ""}`;
    const existing = farms.get(id);
    if (existing) {
      if (!existing.crops.includes(crop)) existing.crops.push(crop);
      continue;
    }
    farms.set(id, {
      id,
      name: allocation.operational_block_name || "Reviewed farm",
      status: "reviewed",
      crops: [crop],
    });
  }
  return Array.from(farms.values());
}

export function CommandCentre({ view }: { view: View }) {
  const [language, setLanguage] = useState<Language>("en");
  const [state, setState] = useState<State>(EMPTY_STATE);
  const [managerBusy, setManagerBusy] = useState(false);
  const [profileSelection, setProfileSelection] = useState<ProfileSelection | null>(null);
  const profileRequest = useRef(0);
  const profileOpener = useRef<string | null>(null);
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
      readJson<ProcurementHistory>("/api/v1/procurement-history/latest"),
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
    const session = results[4].status === "fulfilled" ? results[4].value.value : null;
    const trackwick = session?.authenticated
      ? await readJson<TrackwickBoard>("/api/v1/trackwick/command-centre-board").then(({ value }) => value).catch(() => null)
      : null;
    setState({
      profile: results[0].status === "fulfilled" ? results[0].value.value : null,
      portfolio: results[1].status === "fulfilled" ? results[1].value.value : null,
      runtime: results[2].status === "fulfilled" ? results[2].value.value : null,
      lanes: results[3].status === "fulfilled" ? results[3].value.value : null,
      session,
      readiness: results[5].status === "fulfilled" ? results[5].value.value : null,
      trackwick,
      procurementHistory: results[6].status === "fulfilled" ? results[6].value.value : null,
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

  const farmers = useMemo(() => {
    const peopleById = new Map((state.runtime?.people || []).map((person) => [person.id, person]));
    const rolesByPerson = new Map<string, Set<string>>();
    for (const relationship of state.runtime?.person_operating_relationships?.items || []) {
      if (relationship.role !== "grower") continue;
      const roles = rolesByPerson.get(relationship.person_id) || new Set<string>();
      roles.add(relationship.role);
      rolesByPerson.set(relationship.person_id, roles);
    }
    const cards: ReviewedFarmerCard[] = [];
    for (const [personId, roles] of rolesByPerson) {
      const person = peopleById.get(personId);
      if (person) cards.push({ id: person.id, name: person.name, relationshipRoles: Array.from(roles) });
    }
    return cards;
  }, [state.runtime]);

  async function openFarmProfile(id: string, recordState: FarmProfile["state"], openerId: string) {
    if (!state.session?.authenticated) return;
    profileOpener.current = openerId;
    const request = ++profileRequest.current;
    setProfileSelection({ kind: "farm", loading: true, error: null, profile: null });
    try {
      const { value } = recordState === "reviewed"
        ? await readJson<FarmProfile>("/api/v1/farm-profiles/" + id)
        : await readJson<FarmProfile>("/api/v1/reported-farm-profiles/" + id);
      if (request === profileRequest.current) {
        setProfileSelection({ kind: "farm", loading: false, error: null, profile: value });
      }
    } catch (error) {
      if (request === profileRequest.current) {
        const reauth = profileReadError(error) === "Manager access expired.";
        if (reauth) setState((current) => ({ ...current, session: { authenticated: false } }));
        setProfileSelection({ kind: "farm", loading: false, error: profileReadError(error), profile: null, reauth });
      }
    }
  }

  async function openFarmerProfile(id: string, recordState: FarmerProfile["state"], openerId: string) {
    if (!state.session?.authenticated) return;
    profileOpener.current = openerId;
    const request = ++profileRequest.current;
    setProfileSelection({ kind: "farmer", loading: true, error: null, profile: null });
    try {
      const { value } = recordState === "reviewed"
        ? await readJson<FarmerProfile>("/api/v1/farmer-profiles/" + id)
        : await readJson<FarmerProfile>("/api/v1/reported-farmer-profiles/" + id);
      if (request === profileRequest.current) {
        setProfileSelection({ kind: "farmer", loading: false, error: null, profile: value });
      }
    } catch (error) {
      if (request === profileRequest.current) {
        const reauth = profileReadError(error) === "Manager access expired.";
        if (reauth) setState((current) => ({ ...current, session: { authenticated: false } }));
        setProfileSelection({ kind: "farmer", loading: false, error: profileReadError(error), profile: null, reauth });
      }
    }
  }

  function closeProfile() {
    const openerId = profileOpener.current;
    profileRequest.current += 1;
    profileOpener.current = null;
    setProfileSelection(null);
    window.requestAnimationFrame(() => {
      if (openerId) document.getElementById(openerId)?.focus();
    });
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
      {view === "fields" ? <FieldsView t={t} state={state} canOpenProfiles={Boolean(state.session?.authenticated)} selection={profileSelection?.kind === "farm" ? profileSelection : null} openProfile={openFarmProfile} closeProfile={closeProfile} /> : null}
      {view === "farmers" ? <FarmersView farmers={farmers} readiness={state.readiness} trackwick={state.trackwick} canOpenProfiles={Boolean(state.session?.authenticated)} selection={profileSelection?.kind === "farmer" ? profileSelection : null} openProfile={openFarmerProfile} closeProfile={closeProfile} /> : null}
      {view === "actions" ? <ActionsView t={t} portfolio={state.portfolio} trackwick={state.trackwick} /> : null}
      {view === "settings" ? <SettingsView t={t} state={state} managerBusy={managerBusy} logout={endManagerSession} /> : null}
    </main>
  );
}

function headingFor(view: View, t: Translation) {
  return ({ home: "Today, in the field.", fields: t.reviewedFields, farmers: t.farmers, actions: t.nextMove, settings: t.settings })[view];
}

function HomeView({ t, state }: { t: Translation; state: State }) {
  const portfolio = state.portfolio;
  const readiness = state.readiness;
  const history = state.procurementHistory?.summary;
  const trackwick = state.trackwick;
  const nextMove = portfolio?.risk_action_ledger.items[0];
  const firstTruth = readiness?.next_stage;
  const reportedFarmCount = trackwick?.counts.farm_candidates || 0;
  const statusLine = nextMove
    ? `${count(portfolio?.risk_action_ledger.total_count)} open action${portfolio?.risk_action_ledger.total_count === 1 ? "" : "s"}`
    : reportedFarmCount
      ? `${count(reportedFarmCount)} reported farms await review`
      : history
        ? `${count(history.coverage.quantity_qtl)} qtl · ${count(history.coverage.villages)} villages · ${count(history.coverage.varieties)} varieties`
        : readiness ? `${readiness.progress.completed} of ${readiness.progress.total} operating checks complete` : "Reading the operating record";
  const title = nextMove
    ? nextMove.title
    : reportedFarmCount
      ? `Review ${count(reportedFarmCount)} reported farms.`
      : history
        ? `${count(history.coverage.quantity_qtl)} qtl of past purchase context.`
        : firstTruth?.title || "Start with one reviewed farm.";
  const detail = nextMove
    ? actionLine(nextMove)
    : reportedFarmCount
      ? "TrackWick has source context for people, reported farms, and field activity. Review it before it becomes AGRO CEO field truth."
      : history
        ? `${history.coverage.months.join(" · ")} · historical Fortune procurement by village and variety. It is not a current crop, farmer, or field map.`
        : firstTruth?.next_action || "The operating record begins with a real field, not a guessed one.";
  return <section className="single-stage home-stage">
    <p className="eyebrow">{nextMove ? "One next move" : reportedFarmCount ? "Reported field context" : history ? "Historical supply context" : "Start here"}</p>
    <h2>{title}</h2>
    <p>{detail}</p>
    {nextMove
      ? <Link href="/actions" className="primary-action">Open action <span aria-hidden="true">→</span></Link>
      : reportedFarmCount
        ? <a href="/manager" className="primary-action">Review reported farms <span aria-hidden="true">→</span></a>
        : <Link href="/settings" className="primary-action">Open data connections <span aria-hidden="true">→</span></Link>}
    <footer>{statusLine} · {state.profile?.display_name || "Fortune Farms"}</footer>
  </section>;
}

function FieldsView({ t, state, canOpenProfiles, selection, openProfile, closeProfile }: {
  t: Translation;
  state: State;
  canOpenProfiles: boolean;
  selection: ProfileSelection | null;
  openProfile: (id: string, recordState: FarmProfile["state"], openerId: string) => Promise<void>;
  closeProfile: () => void;
}) {
  const fields = reviewedFarmsFromRuntime(state.runtime);
  const verifiedFeatures = state.map?.features || [];
  const waitingForFarm = state.readiness?.counts.operating_units === 0;
  const reportedFarms = state.trackwick?.farms || [];
  if (selection) return <ProfileReading selection={selection} close={closeProfile} />;
  return <section className="single-surface fields-stage">
    <div className="surface-heading"><div><p className="eyebrow">{fields.length ? t.fieldMap : reportedFarms.length ? "Reported farm context" : t.fieldMap}</p><h2>{fields.length ? "Reviewed fields" : reportedFarms.length ? "Reported farms, ready for review" : "No field has been claimed yet."}</h2></div><span className="count-badge">{count(fields.length || reportedFarms.length)}</span></div>
    {fields.length ? <div className="field-card-grid">{fields.map((field) => <article className="field-card" key={field.id}><span className="status-chip">{field.status}</span><h3>{field.name}</h3><p>{field.crops.join(" · ") || "No active crop recorded"}</p><ProfileControl canOpenProfiles={canOpenProfiles} controlId={`profile-reviewed-farm-${field.id}`} label={`Open ${field.name} profile`} text="Open profile" open={(openerId) => void openProfile(field.id, "reviewed", openerId)} /></article>)}</div> : reportedFarms.length ? <ReportedFarmCandidates farms={reportedFarms} canOpenProfiles={canOpenProfiles} openProfile={openProfile} /> : <EmptyState title={waitingForFarm ? "No reviewed field yet." : t.noData} detail={waitingForFarm ? "Field truth will appear here after a reported farm is reviewed. A purchase village or source pin never becomes a field by itself." : "Publish a reviewed farm record to make a field visible."} />}
    {state.session?.authenticated && verifiedFeatures.length ? <ReviewedGeometry features={verifiedFeatures} /> : null}
  </section>;
}

function ReportedFarmCandidates({ farms, canOpenProfiles, openProfile }: {
  farms: TrackwickFarm[];
  canOpenProfiles: boolean;
  openProfile: (id: string, recordState: FarmProfile["state"], openerId: string) => Promise<void>;
}) {
  return <><p className="surface-copy">These are TrackWick-reported farms, not AGRO CEO fields or boundaries.</p><div className="field-card-grid">{farms.slice(0, 6).map((farm) => <article className="field-card" key={farm.id}><span className="status-chip">reported</span><h3>{farm.place}</h3><p>{farm.farmer_name} · {farm.reported_area_acres ? `${farm.reported_area_acres} acres` : "area not reported"}</p><p className="card-detail">{farm.reported_plot_count ? `${farm.reported_plot_count} reported plots · ` : ""}{farm.open_work} open source work</p><ProfileControl canOpenProfiles={canOpenProfiles} controlId={`profile-reported-farm-${farm.id}`} label={`Open reported farm profile for ${farm.place}`} text="Open reported profile" open={(openerId) => void openProfile(farm.id, "reported", openerId)} /></article>)}</div></>;
}

function ReviewedGeometry({ features }: { features: Array<{ properties?: Record<string, unknown> }> }) {
  if (!features.length) return <div className="map-empty"><strong>No reviewed field geometry yet.</strong><p>AGRO CEO will not draw an inferred boundary or put a programme location on this map.</p></div>;
  return <div className="geometry-list"><p>{features.length} reviewed feature{features.length === 1 ? "" : "s"} are available to the manager map.</p>{features.slice(0, 8).map((feature, index) => <span key={`${String(feature.properties?.plot_label || "field")}-${index}`}>{String(feature.properties?.plot_label || "Reviewed field")}</span>)}</div>;
}

function FarmersView({ farmers, readiness, trackwick, canOpenProfiles, selection, openProfile, closeProfile }: {
  farmers: ReviewedFarmerCard[];
  readiness: PilotReadiness | null;
  trackwick: TrackwickBoard | null;
  canOpenProfiles: boolean;
  selection: ProfileSelection | null;
  openProfile: (id: string, recordState: FarmerProfile["state"], openerId: string) => Promise<void>;
  closeProfile: () => void;
}) {
  const sourceFarmers = trackwick?.farmers || [];
  if (selection) return <ProfileReading selection={selection} close={closeProfile} />;
  return <section className="single-surface people-stage">
    <div className="surface-heading"><div><p className="eyebrow">{farmers.length ? "Reviewed grower relationships" : sourceFarmers.length ? "Reported farmers" : "Reviewed grower relationships"}</p><h2>{farmers.length ? "Farmers on this operating record" : sourceFarmers.length ? "Farmers reported by TrackWick" : "Farmers on this operating record"}</h2></div><span className="count-badge">{count(farmers.length || sourceFarmers.length)}</span></div>
    {farmers.length ? <div className="people-list">{farmers.map((person) => <article className="person-row" key={person.id}><span className="person-initial">{person.name.slice(0, 1).toUpperCase()}</span><div className="person-summary"><h3>{person.name}</h3><p>{person.relationshipRoles.map(roleName).join(" · ")} relationship</p></div><ProfileControl canOpenProfiles={canOpenProfiles} controlId={`profile-reviewed-farmer-${person.id}`} label={`Open ${person.name} farmer profile`} text="Open profile" open={(openerId) => void openProfile(person.id, "reviewed", openerId)} /></article>)}</div> : sourceFarmers.length ? <ReportedFarmers farmers={sourceFarmers} canOpenProfiles={canOpenProfiles} openProfile={openProfile} /> : <p className="empty-copy">{readiness?.counts.people ? "No reviewed grower relationship is attached to this operating record yet." : "Farmers appear here only after a reviewed grower relationship is recorded."}</p>}
  </section>;
}

function ReportedFarmers({ farmers, canOpenProfiles, openProfile }: {
  farmers: TrackwickFarmer[];
  canOpenProfiles: boolean;
  openProfile: (id: string, recordState: FarmerProfile["state"], openerId: string) => Promise<void>;
}) {
  return <><p className="surface-copy">Reported farmers are not sign-ins or reviewed grower relationships.</p><div className="people-list">{farmers.slice(0, 6).map((person) => <article className="person-row" key={person.id}><span className="person-initial">{person.name.slice(0, 1).toUpperCase()}</span><div className="person-summary"><h3>{person.name}</h3><p>{person.farm_candidates} reported farm{person.farm_candidates === 1 ? "" : "s"} · {person.open_work} open source work</p></div><ProfileControl canOpenProfiles={canOpenProfiles} controlId={`profile-reported-farmer-${person.id}`} label={`Open reported farmer profile for ${person.name}`} text="Open reported profile" open={(openerId) => void openProfile(person.id, "reported", openerId)} /></article>)}</div></>;
}

function ProfileControl({ canOpenProfiles, controlId, label, text, open }: {
  canOpenProfiles: boolean;
  controlId: string;
  label: string;
  text: string;
  open: (openerId: string) => void;
}) {
  if (!canOpenProfiles) return <span className="profile-locked" aria-disabled="true">Manager access required</span>;
  return <button id={controlId} type="button" className="text-link profile-open" onClick={(event) => open(event.currentTarget.id)} aria-label={label}>{text} <span aria-hidden="true">→</span></button>;
}

function ProfileReading({ selection, close }: { selection: ProfileSelection; close: () => void }) {
  if (selection.profile) return <ProfilePanel profile={selection.profile} close={close} />;
  const subject = selection.kind === "farm" ? "farm" : "farmer";
  return <aside className="single-surface profile-panel" aria-label={`${subject} profile`} aria-busy={selection.loading}>
    <button type="button" className="quiet-button profile-back" onClick={close} autoFocus>Back to {selection.kind === "farm" ? "fields" : "farmers"}</button>
    {selection.loading
      ? <p className="profile-message" role="status">Reading this {subject} profile…</p>
      : <p className="profile-message profile-error" role="alert">{selection.error} {selection.reauth ? <a href="/manager">Re-authenticate in Farm Truth</a> : null}</p>}
  </aside>;
}

function ProfilePanel({ profile, close }: { profile: FarmProfile | FarmerProfile; close: () => void }) {
  const reported = profile.state === "reported";
  return <aside className="single-surface profile-panel" aria-label={`${profile.name} profile`}>
    <button type="button" className="quiet-button profile-back" onClick={close} autoFocus>Back to {profile.kind === "farm" ? "fields" : "farmers"}</button>
    <p className="eyebrow">{reported ? "Reported context" : profile.kind === "farm" ? "Reviewed farm record" : "Reviewed grower relationship"}</p>
    <h2>{profile.name}</h2>
    <p className="profile-context">{profile.limitations?.[0] || (profile.kind === "farm" ? "This farm record has been reviewed for the current operating record." : "Only reviewed operating relationships are shown here.")}</p>
    {profile.kind === "farm" ? <FarmProfileFacts profile={profile} /> : <FarmerProfileFacts profile={profile} />}
    <div className="profile-action">
      {reported
        ? <a className="primary-action" href="/manager">Review in Farm Truth <span aria-hidden="true">→</span></a>
        : profile.kind === "farm"
          ? <Link className="primary-action" href="/actions">Open actions <span aria-hidden="true">→</span></Link>
          : <a className="primary-action" href="/manager">Open in Farm Truth <span aria-hidden="true">→</span></a>}
    </div>
  </aside>;
}

function FarmProfileFacts({ profile }: { profile: FarmProfile }) {
  if (profile.state === "reported") {
    const photoReferences = (profile.reported?.plot_photo_references || 0)
      + (profile.reported?.crop_photo_references || 0);
    return <dl className="profile-facts">
      <div><dt>Reported farmer</dt><dd>{profile.reported?.farmer_name || "Not reported"}</dd></div>
      <div><dt>Reported area</dt><dd>{profile.reported?.reported_area_acres == null ? "Not reported" : `${profile.reported.reported_area_acres} acres`}</dd></div>
      <div><dt>Reported plots</dt><dd>{profile.reported?.reported_plot_count == null ? "Not reported" : count(profile.reported.reported_plot_count)}</dd></div>
      <div><dt>Open source work</dt><dd>{count(profile.reported?.open_work)}</dd></div>
      <div><dt>Latest activity</dt><dd>{dateTime(profile.reported?.latest_activity_at)}</dd></div>
      <div><dt>Photo references</dt><dd>{count(photoReferences)}</dd></div>
    </dl>;
  }
  const crop = profile.current
    ? `${profile.current.crop_name}${profile.current.cultivar ? ` · ${profile.current.cultivar}` : ""}`
    : "No active crop recorded";
  return <div className="profile-groups">
    <dl className="profile-facts">
      <div><dt>Current crop</dt><dd>{crop}</dd></div>
      <div><dt>Reviewed growers</dt><dd>{profile.people?.length ? profile.people.map((person) => `${person.name} · ${roleName(person.role)}`).join(", ") : "None recorded"}</dd></div>
      <div><dt>Open work</dt><dd>{count(profile.open_work_count)}</dd></div>
      <div><dt>Field map</dt><dd>{profile.location?.state === "not_published" ? "Not published" : profile.location?.state === "published" ? "Published" : "Not available"}</dd></div>
    </dl>
    <section className="profile-record">
      <h3>Field record</h3>
      <dl className="profile-facts">
        <div><dt>Latest observation</dt><dd>{dateTime(profile.record?.latest_observed_at)}</dd></div>
        <div><dt>Limitation</dt><dd>{profile.record?.limitation || "No field-record limitation is available."}</dd></div>
      </dl>
    </section>
  </div>;
}

function FarmerProfileFacts({ profile }: { profile: FarmerProfile }) {
  if (profile.state === "reported") {
    return <dl className="profile-facts">
      <div><dt>Reported farms</dt><dd>{count(profile.reported?.farm_candidates)}</dd></div>
      <div><dt>Reported area</dt><dd>{profile.reported?.reported_area_acres == null ? "Not reported" : `${profile.reported.reported_area_acres} acres`}</dd></div>
      <div><dt>Open source work</dt><dd>{count(profile.reported?.open_work)}</dd></div>
      <div><dt>Latest activity</dt><dd>{dateTime(profile.reported?.latest_activity_at)}</dd></div>
      <div><dt>Photo references</dt><dd>{count(profile.reported?.crop_photo_references)}</dd></div>
      <div><dt>Account</dt><dd>{profile.account?.state === "not_created" ? "No sign-in created" : "Not reported"}</dd></div>
    </dl>;
  }
  return <div className="profile-groups">
    <section className="profile-relationships">
      <h3>Linked farms</h3>
      {profile.farms?.length
        ? <ul>{profile.farms.map((farm) => {
          const crop = farm.current
            ? `${farm.current.crop_name}${farm.current.cultivar ? ` · ${farm.current.cultivar}` : ""}`
            : "No active crop recorded";
          return <li key={farm.id}><strong>{farm.name}</strong><span>{crop} · {count(farm.open_work_count)} open work</span></li>;
        })}</ul>
        : <p>No linked reviewed farm is recorded.</p>}
    </section>
    <section className="profile-relationships">
      <h3>Reviewed relationships</h3>
      {profile.relationships?.length
        ? <ul>{profile.relationships.map((relationship, index) => <li key={`${relationship.scope_type}-${relationship.starts_on}-${index}`}><strong>{roleName(relationship.role)}</strong><span>{relationship.scope_name} · since {relationship.starts_on}</span></li>)}</ul>
        : <p>No active reviewed grower relationship is recorded.</p>}
    </section>
  </div>;
}

function ActionsView({ t, portfolio, trackwick }: { t: Translation; portfolio: Portfolio | null; trackwick: TrackwickBoard | null }) {
  const actions = portfolio?.risk_action_ledger.items || [];
  const sourceWork = trackwick?.inbox || [];
  return <section className="single-surface actions-surface"><div className="surface-heading"><div><p className="eyebrow">{actions.length ? "Decision queue" : sourceWork.length ? "Reported source work" : "Decision queue"}</p><h2>{actions.length ? "Open actions" : sourceWork.length ? "Source work awaiting review" : "Open actions"}</h2></div><span className="count-badge">{count(actions.length || sourceWork.length)}</span></div>{actions.length ? <ActionRows items={actions} empty={t.noActions} /> : sourceWork.length ? <SourceWorkRows items={sourceWork} /> : <ActionRows items={actions} empty={t.noActions} />}</section>;
}

function SourceWorkRows({ items }: { items: TrackwickWork[] }) {
  return <><p className="surface-copy">These are TrackWick tasks. They are not yet assigned AGRO CEO actions and cannot complete work here.</p><ol className="action-list">{items.slice(0, 8).map((item) => <li key={item.id}><span className="severity medium">reported</span><div><h3>{item.task_type}</h3><p>{[item.farmer_name, item.follow_up_at ? `due ${dateTime(item.follow_up_at)}` : null].filter(Boolean).join(" · ")}</p></div><a className="text-link" href="/manager">Review <span aria-hidden="true">→</span></a></li>)}</ol></>;
}

function ActionRows({ items, empty }: { items: LedgerItem[]; empty: string }) {
  if (!items.length) return <p className="empty-copy">{empty}</p>;
  return <ol className="action-list">{items.map((item) => <li key={`${item.entity.type}-${item.entity.id}`}><span className={`severity ${item.severity}`}>{item.severity}</span><div><h3>{item.title}</h3><p>{actionLine(item)}</p></div><Link className="text-link" href={item.allocation_id ? `/fields?field=${encodeURIComponent(item.allocation_id)}` : "/actions"}>Open <span aria-hidden="true">→</span></Link></li>)}</ol>;
}

function SettingsView({ t, state, managerBusy, logout }: {
  t: Translation; state: State; managerBusy: boolean; logout: () => Promise<void>;
}) {
  const session = state.session;
  const history = state.procurementHistory?.summary;
  const trackwick = state.trackwick;
  const trackwickStatus = trackwick?.source.state === "succeeded"
    ? `Last synced ${dateTime(trackwick.source.last_synced_at)}.`
    : "Not connected yet. No TrackWick data is being shown.";
  return <section className="single-surface settings-stage">
    <div className="surface-heading"><div><p className="eyebrow">Private setup</p><h2>Access and connections</h2></div></div>
    <p className="surface-copy">{state.profile?.display_name || "Fortune Farms"} stays private until a named person is given the exact access they need.</p>
    <div className="settings-rows">
      <div><strong>People</strong><span>{session?.authenticated ? "Manage named ID access below." : "Use your admin ID to manage access."}</span></div>
      <div><strong>Purchase history</strong><span>{history ? `${count(history.coverage.quantity_qtl)} qtl across ${count(history.coverage.villages)} villages, ${history.coverage.months.join(" · ")}. Historical context only.` : "No reviewed purchase history yet."}</span></div>
      <div><strong>Field context</strong><span>{trackwickStatus}</span></div>
      <div className="disabled-connection" aria-disabled="true"><strong>WhatsApp updates <em>Coming soon</em></strong><span>Named requests and reviewable evidence will arrive here after the separate launch gate. WhatsApp never decides or closes work.</span></div>
    </div>
    {session?.authenticated ? <><PasswordChanger /><AccountManager /><div className="settings-actions"><a className="text-link" href="/manager">Open Farm Truth <span aria-hidden="true">→</span></a><button className="quiet-button" type="button" disabled={managerBusy} onClick={() => void logout()}>{t.lock}</button></div></> : <p className="empty-copy">Sign in with a named admin account to manage people and connections.</p>}
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

function profileReadError(error: unknown) {
  const status = error instanceof Error ? (error as Error & { status?: number }).status : undefined;
  return status === 403
    ? "Manager access expired."
    : status === 404
    ? "This profile is no longer available. Return to the list and refresh the operating record."
    : "This profile could not be read. Return to the list and try again.";
}
