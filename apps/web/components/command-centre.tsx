"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

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
type TrackwickFieldWorker = {
  id: string;
  name: string;
  reported_farmer_reach: number;
  open_work: number;
  completed_work: number;
  latest_activity_at?: string | null;
  latest_attendance_on?: string | null;
};
type TrackwickSignal = {
  id: string;
  finding_kind: "disease" | "pest";
  declared_severity: "unknown" | "low" | "moderate" | "high" | "critical";
  observed_at: string;
  farmer_name?: string | null;
};
type TrackwickWork = {
  id: string;
  label: string;
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
    field_workers: number;
    open_work: number;
    crop_photo_references: number;
    plot_photo_references: number;
    reported_visits: number;
    reported_input_events: number;
    reported_signals: number;
    geotagged_evidence: number;
  };
  farms: TrackwickFarm[];
  farmers: TrackwickFarmer[];
  field_workers: TrackwickFieldWorker[];
  signals: TrackwickSignal[];
  inbox: TrackwickWork[];
};
type ReviewedFarmerCard = {
  state: "reviewed";
  kind: "farmer";
  id: string;
  name: string;
  assignment_count: number;
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

type ReviewedFarmDirectoryItem = {
  state: "reviewed";
  kind: "farm";
  id: string;
  name: string;
  field_count: number;
  crops: string[];
  open_work_count: number;
  latest_update_at?: string | null;
};
type ReportedFarmDirectoryItem = {
  state: "reported";
  kind: "reported_farm_candidate";
  id: string;
  name: string;
  reported_farmer_name: string;
  reported_area_acres?: number | null;
  reported_plot_count?: number | null;
  open_work_count: number;
  latest_update_at?: string | null;
  destination: { kind: "review_reported_farm"; id: string };
};
type FarmDirectoryItem = ReviewedFarmDirectoryItem | ReportedFarmDirectoryItem;

type FarmDirectory = FarmDirectoryItem[];
type PersonKind = "farmer" | "field_worker";
type EntityPerson = {
  id: string;
  name: string;
  kind: PersonKind;
  role: string;
  starts_on: string;
  field_id: string;
  field_name: string;
};
type EntityUpdate = {
  id: string;
  occurred_at: string;
  kind: string;
  state: "reviewed" | "reported";
  field_id: string;
  field_name: string;
  summary: string;
  status?: string;
  actor?: string | null;
  finding_kind?: string;
  declared_severity?: string;
};
type FarmRecord = {
  state: "reviewed";
  kind: "farm";
  id: string;
  name: string;
  now: {
    fields: Array<{ id: string; name: string }>;
    active_allocations: Array<{
      id: string;
      crop_name: string;
      cultivar?: string | null;
      season_id: string;
      season_name: string;
    }>;
    open_work_count: number;
    latest_update_at?: string | null;
  };
  people: EntityPerson[];
  updates: EntityUpdate[];
  context: { state: string; message: string };
  limitations: string[];
};
type ReportedFarmProfile = {
  state: "reported";
  kind: "farm";
  id: string;
  name: string;
  reported: {
    farmer_name: string;
    place: string;
    reported_area_acres?: number | null;
    reported_plot_count?: number | null;
    open_work: number;
    latest_activity_at?: string | null;
    plot_photo_references: number;
    crop_photo_references: number;
  };
  limitations: string[];
};
type FieldRecord = {
  state: "reviewed";
  kind: "field";
  id: string;
  name: string;
  area_hectares?: number | null;
  farm?: { id: string; name: string } | null;
  geometry: { state: string; message?: string };
  allocations: Array<{
    id: string;
    season_id: string;
    season_name: string;
    crop_name: string;
    cultivar?: string | null;
    area_hectares?: number | null;
    status: string;
    starts_on: string;
    ends_on: string;
  }>;
  people: EntityPerson[];
  updates: EntityUpdate[];
  limitations: string[];
};
type PersonContext = {
  state: "reviewed";
  kind: PersonKind;
  id: string;
  name: string;
  assignments: Array<{
    farm_id: string;
    farm_name: string;
    field_id: string;
    field_name: string;
    role: string;
    starts_on: string;
  }>;
  context: { state: string; message: string };
  limitations: string[];
};
type ContextRecord = FarmRecord | ReportedFarmProfile | FieldRecord | PersonContext;
type ContextHistoryItem = { record: ContextRecord; openerId: string };
type ContextPanel = {
  kind: ContextRecord["kind"];
  loading: boolean;
  error: string | null;
  record: ContextRecord | null;
  history: ContextHistoryItem[];
  reauth?: boolean;
};
type DirectoryFilters = {
  state: "all" | "reviewed" | "reported";
  query: string;
  dateFrom: string;
  dateTo: string;
};

type ReportedFarmerProfile = {
  state: "reported";
  kind: "farmer";
  id: string;
  name: string;
  reported?: {
    farm_candidates?: number;
    reported_area_acres?: number | null;
    open_work?: number;
    latest_activity_at?: string | null;
    crop_photo_references?: number;
    source_activity?: ReportedSourceActivity;
  };
  account?: { state: "not_created" };
  limitations?: string[];
};
type ReportedFieldWorkerProfile = {
  state: "reported";
  kind: "field_worker";
  id: string;
  name: string;
  reported?: {
    reported_farmer_reach?: number;
    open_work?: number;
    completed_work?: number;
    latest_activity_at?: string | null;
    latest_attendance_on?: string | null;
    source_activity?: ReportedSourceActivity;
  };
  account?: { state: "not_created" };
  limitations?: string[];
};
type ReportedSourceActivity = {
  source_work: number;
  completed_source_work: number;
  reported_visits: number;
  reported_disease: number;
  reported_pest: number;
  reported_input_events: number;
  geotagged_evidence: number;
  latest_crop_context?: {
    observed_at: string;
    crop_stage?: string | null;
    water_condition?: string | null;
    crop_condition_score?: number | null;
  } | null;
};
type PersonProfile = PersonContext | ReportedFarmerProfile | ReportedFieldWorkerProfile;

type ProfileSelection = {
  kind: PersonProfile["kind"];
  loading: boolean;
  error: string | null;
  profile: PersonProfile | null;
  reauth?: boolean;
};

type State = {
  profile: OperatingProfile | null;
  portfolio: Portfolio | null;
  runtime: Runtime | null;
  lanes: DataLanes | null;
  session: ManagerSession | null;
  readiness: PilotReadiness | null;
  trackwick: TrackwickBoard | null;
  canonicalFarmers: ReviewedFarmerCard[];
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
  readiness: null,
  trackwick: null,
  canonicalFarmers: [],
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
    const [trackwick, canonicalFarmers] = session?.authenticated
      ? await Promise.all([
          readJson<TrackwickBoard>("/api/v1/trackwick/command-centre-board").then(({ value }) => value).catch(() => null),
          readJson<ReviewedFarmerCard[]>("/api/v1/people?kind=farmer&limit=100").then(({ value }) => value).catch(() => []),
        ])
      : [null, []];
    setState({
      profile: results[0].status === "fulfilled" ? results[0].value.value : null,
      portfolio: results[1].status === "fulfilled" ? results[1].value.value : null,
      runtime: results[2].status === "fulfilled" ? results[2].value.value : null,
      lanes: results[3].status === "fulfilled" ? results[3].value.value : null,
      session,
      readiness: results[5].status === "fulfilled" ? results[5].value.value : null,
      trackwick,
      canonicalFarmers,
      procurementHistory: results[6].status === "fulfilled" ? results[6].value.value : null,
      loading: false,
      needsLaunchLogin: false,
      error: rejected ? "Some current operating data could not be read. Nothing has been estimated." : null,
    });
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function openPersonProfile(
    id: string, kind: PersonKind, recordState: "reviewed" | "reported", openerId: string,
  ) {
    if (!state.session?.authenticated) return;
    profileOpener.current = openerId;
    const request = ++profileRequest.current;
    setProfileSelection({ kind, loading: true, error: null, profile: null });
    try {
      const { value } = recordState === "reviewed"
        ? await readJson<PersonContext>("/api/v1/people/" + kind + "/" + id)
        : kind === "farmer"
          ? await readJson<ReportedFarmerProfile>("/api/v1/reported-farmer-profiles/" + id)
          : await readJson<ReportedFieldWorkerProfile>("/api/v1/reported-field-worker-profiles/" + id);
      if (request === profileRequest.current) {
        setProfileSelection({ kind, loading: false, error: null, profile: value });
      }
    } catch (error) {
      if (request === profileRequest.current) {
        const reauth = profileReadError(error) === "Manager access expired.";
        if (reauth) setState((current) => ({ ...current, session: { authenticated: false } }));
        setProfileSelection({ kind, loading: false, error: profileReadError(error), profile: null, reauth });
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

  const expireManagerSession = useCallback(() => {
    setState((current) => ({ ...current, session: { authenticated: false } }));
  }, []);

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
          {!state.session?.authenticated ? <Link href={`/login?next=/${view}`} className="quiet-button">Sign in</Link> : null}
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
      {view === "fields" ? <FieldsView t={t} state={state} canOpenProfiles={Boolean(state.session?.authenticated)} expireManagerSession={expireManagerSession} /> : null}
      {view === "farmers" ? <FarmersView farmers={state.canonicalFarmers} readiness={state.readiness} trackwick={state.trackwick} canOpenProfiles={Boolean(state.session?.authenticated)} selection={profileSelection?.kind === "farmer" ? profileSelection : null} openProfile={openPersonProfile} closeProfile={closeProfile} /> : null}
      {view === "actions" ? <ActionsView t={t} portfolio={state.portfolio} trackwick={state.trackwick} canOpenProfiles={Boolean(state.session?.authenticated)} selection={profileSelection?.kind === "field_worker" ? profileSelection : null} openProfile={openPersonProfile} closeProfile={closeProfile} /> : null}
      {view === "settings" ? <SettingsView t={t} state={state} managerBusy={managerBusy} logout={endManagerSession} /> : null}
    </main>
  );
}

function headingFor(view: View, t: Translation) {
  return ({ home: "Today, in the field.", fields: languageFarmHeading(t), farmers: t.farmers, actions: t.nextMove, settings: t.settings })[view];
}

function languageFarmHeading(t: Translation) {
  return t.farm === "Farm" ? "Farms" : t.farm;
}

function HomeView({ t, state }: { t: Translation; state: State }) {
  const portfolio = state.portfolio;
  const readiness = state.readiness;
  const history = state.procurementHistory?.summary;
  const trackwick = state.trackwick;
  const nextMove = portfolio?.risk_action_ledger.items[0];
  const firstTruth = readiness?.next_stage;
  const reportedFarmCount = trackwick?.counts.farm_candidates || 0;
  const statusLine = reportedFarmCount
    ? `${count(reportedFarmCount)} reported farms · ${count(trackwick?.counts.farmers)} farmers · ${count(trackwick?.counts.field_workers)} field workers`
    : nextMove
      ? `${count(portfolio?.risk_action_ledger.total_count)} open action${portfolio?.risk_action_ledger.total_count === 1 ? "" : "s"}`
      : history
        ? `${count(history.coverage.quantity_qtl)} qtl · ${count(history.coverage.villages)} villages · ${count(history.coverage.varieties)} varieties`
        : readiness ? `${readiness.progress.completed} of ${readiness.progress.total} operating checks complete` : "Reading the operating record";
  const title = reportedFarmCount
    ? `${count(reportedFarmCount)} reported farms in TrackWick.`
    : nextMove
      ? nextMove.title
      : history
        ? `${count(history.coverage.quantity_qtl)} qtl of past purchase context.`
        : firstTruth?.title || "Start with one reviewed farm.";
  const detail = reportedFarmCount
    ? `${count(trackwick?.counts.reported_visits)} reported visits · ${count(trackwick?.counts.reported_signals)} disease and pest reports · ${count(trackwick?.counts.open_work)} open source work. Review source facts before they become AGRO CEO field truth.`
    : nextMove
      ? actionLine(nextMove)
      : history
        ? `${history.coverage.months.join(" · ")} · historical Fortune procurement by village and variety. It is not a current crop, farmer, or field map.`
        : firstTruth?.next_action || "The operating record begins with a real field, not a guessed one.";
  return <section className="single-stage home-stage">
    <p className="eyebrow">{nextMove ? "One next move" : reportedFarmCount ? "Reported field context" : history ? "Historical supply context" : "Start here"}</p>
    <h2>{title}</h2>
    <p>{detail}</p>
    {reportedFarmCount
      ? <Link href="/fields?state=reported" className="primary-action">Browse reported farms <span aria-hidden="true">→</span></Link>
      : nextMove
        ? <Link href="/actions" className="primary-action">Open action <span aria-hidden="true">→</span></Link>
        : <Link href="/settings" className="primary-action">Open data connections <span aria-hidden="true">→</span></Link>}
    <footer>{statusLine} · {state.profile?.display_name || "Fortune Farms"}</footer>
  </section>;
}

const EMPTY_DIRECTORY_FILTERS: DirectoryFilters = {
  state: "reported",
  query: "",
  dateFrom: "",
  dateTo: "",
};
const MANAGER_ACCESS_BOUNDARY_ID = "farm-manager-access-boundary";
const FARM_DIRECTORY_PAGE_SIZE = 100;

function filtersFromLocation() {
  const params = new URLSearchParams(window.location.search);
  const state = params.get("state");
  return {
    state: state === "all" || state === "reviewed" || state === "reported" ? state : "reported",
    query: params.get("query") || "",
    dateFrom: params.get("date_from") || "",
    dateTo: params.get("date_to") || "",
  } satisfies DirectoryFilters;
}

function directoryParams(filters: DirectoryFilters) {
  const params = new URLSearchParams();
  params.set("kind", "farm");
  params.set("state", filters.state);
  if (filters.query.trim()) params.set("query", filters.query.trim());
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  return params;
}

function FieldsView({ t, state, canOpenProfiles, expireManagerSession }: {
  t: Translation;
  state: State;
  canOpenProfiles: boolean;
  expireManagerSession: () => void;
}) {
  const [filters, setFilters] = useState<DirectoryFilters>(EMPTY_DIRECTORY_FILTERS);
  const [draftFilters, setDraftFilters] = useState<DirectoryFilters>(EMPTY_DIRECTORY_FILTERS);
  const [filtersReady, setFiltersReady] = useState(false);
  const [directoryPage, setDirectoryPage] = useState(0);
  const [directory, setDirectory] = useState<{ items: FarmDirectory; loading: boolean; error: string | null }>({
    items: [], loading: false, error: null,
  });
  const [panel, setPanel] = useState<ContextPanel | null>(null);
  const directoryRequest = useRef(0);
  const panelRequest = useRef(0);
  const directoryOpener = useRef<string | null>(null);
  const managerAccessWasEnabled = useRef(canOpenProfiles);
  const pendingManagerExpiryFocus = useRef(false);
  const initialFarmRequest = useRef<string | null>(null);

  useEffect(() => {
    function syncFromUrl() {
      const next = filtersFromLocation();
      initialFarmRequest.current = new URLSearchParams(window.location.search).get("farm");
      setFilters(next);
      setDraftFilters(next);
      setFiltersReady(true);
    }
    syncFromUrl();
    window.addEventListener("popstate", syncFromUrl);
    return () => window.removeEventListener("popstate", syncFromUrl);
  }, []);

  useEffect(() => {
    if (!filtersReady || !canOpenProfiles) {
      if (filtersReady) setDirectory({ items: [], loading: false, error: null });
      return;
    }
    const request = ++directoryRequest.current;
    const params = directoryParams(filters);
    params.set("limit", String(FARM_DIRECTORY_PAGE_SIZE));
    params.set("offset", String(directoryPage * FARM_DIRECTORY_PAGE_SIZE));
    setDirectory((current) => ({ ...current, loading: true, error: null }));
    void readJson<FarmDirectory>("/api/v1/farms?" + params)
      .then(({ value }) => {
        if (request === directoryRequest.current) setDirectory((current) => ({
          items: directoryPage ? [...current.items, ...value] : value,
          loading: false,
          error: null,
        }));
      })
      .catch((error: unknown) => {
        if (request !== directoryRequest.current) return;
        const message = profileReadError(error);
        if (message === "Manager access expired.") expireManagerSession();
        setDirectory({ items: [], loading: false, error: message });
      });
  }, [canOpenProfiles, directoryPage, expireManagerSession, filters, filtersReady]);

  useEffect(() => {
    const expired = managerAccessWasEnabled.current && !canOpenProfiles;
    managerAccessWasEnabled.current = canOpenProfiles;
    if (canOpenProfiles) return;
    directoryRequest.current += 1;
    panelRequest.current += 1;
    if (expired) pendingManagerExpiryFocus.current = true;
    setPanel(null);
  }, [canOpenProfiles]);

  useEffect(() => {
    if (canOpenProfiles || panel || !pendingManagerExpiryFocus.current) return;
    pendingManagerExpiryFocus.current = false;
    restoreFocusAfterManagerExpiry();
  }, [canOpenProfiles, panel]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next = { ...draftFilters, query: draftFilters.query.trim() };
    const params = directoryParams(next);
    params.delete("kind");
    const query = params.toString();
    window.history.pushState({}, "", query ? `/fields?${query}` : "/fields");
    setDirectoryPage(0);
    setFilters(next);
  }

  function clearFilters() {
    window.history.pushState({}, "", "/fields?state=reported");
    setDraftFilters(EMPTY_DIRECTORY_FILTERS);
    setDirectoryPage(0);
    setFilters(EMPTY_DIRECTORY_FILTERS);
  }

  function restoreFocusAfterManagerExpiry() {
    const openerId = directoryOpener.current;
    directoryOpener.current = null;
    const target = (openerId ? document.getElementById(openerId) : null)
      || document.getElementById(MANAGER_ACCESS_BOUNDARY_ID);
    target?.focus();
  }

  function panelHistory(openerId: string, nested: boolean) {
    if (!nested || !panel?.record) return [];
    return [...panel.history, { record: panel.record, openerId }];
  }

  async function openFarm(id: string, openerId: string, nested = false) {
    if (!canOpenProfiles) return;
    if (!nested) directoryOpener.current = openerId;
    const history = panelHistory(openerId, nested);
    const request = ++panelRequest.current;
    setPanel({ kind: "farm", loading: true, error: null, record: null, history });
    try {
      const { value } = await readJson<FarmRecord>("/api/v1/farms/" + id);
      if (request === panelRequest.current) setPanel({ kind: "farm", loading: false, error: null, record: value, history });
    } catch (error) {
      finishPanelError(request, "farm", history, error);
    }
  }

  async function openReportedFarm(id: string, openerId: string) {
    if (!canOpenProfiles) return;
    directoryOpener.current = openerId;
    const request = ++panelRequest.current;
    setPanel({ kind: "farm", loading: true, error: null, record: null, history: [] });
    try {
      const { value } = await readJson<ReportedFarmProfile>("/api/v1/reported-farm-profiles/" + id);
      if (request === panelRequest.current) setPanel({ kind: "farm", loading: false, error: null, record: value, history: [] });
    } catch (error) {
      finishPanelError(request, "farm", [], error);
    }
  }

  useEffect(() => {
    const farmId = initialFarmRequest.current;
    if (!filtersReady || !canOpenProfiles || !farmId) return;
    initialFarmRequest.current = null;
    void openFarm(farmId, MANAGER_ACCESS_BOUNDARY_ID);
  }, [canOpenProfiles, filtersReady]);

  async function openField(id: string, openerId: string) {
    if (!canOpenProfiles) return;
    const history = panelHistory(openerId, true);
    const request = ++panelRequest.current;
    setPanel({ kind: "field", loading: true, error: null, record: null, history });
    try {
      const { value } = await readJson<FieldRecord>("/api/v1/fields/" + id);
      if (request === panelRequest.current) setPanel({ kind: "field", loading: false, error: null, record: value, history });
    } catch (error) {
      finishPanelError(request, "field", history, error);
    }
  }

  async function openPerson(kind: PersonKind, id: string, openerId: string) {
    if (!canOpenProfiles) return;
    const history = panelHistory(openerId, true);
    const request = ++panelRequest.current;
    setPanel({ kind, loading: true, error: null, record: null, history });
    try {
      const { value } = await readJson<PersonContext>("/api/v1/people/" + kind + "/" + id);
      if (request === panelRequest.current) setPanel({ kind, loading: false, error: null, record: value, history });
    } catch (error) {
      finishPanelError(request, kind, history, error);
    }
  }

  function finishPanelError(
    request: number,
    kind: ContextPanel["kind"],
    history: ContextHistoryItem[],
    error: unknown,
  ) {
    if (request !== panelRequest.current) return;
    const message = profileReadError(error);
    const reauth = message === "Manager access expired.";
    if (reauth) expireManagerSession();
    setPanel({ kind, loading: false, error: message, record: null, history, reauth });
  }

  function closePanel() {
    if (!panel) return;
    panelRequest.current += 1;
    const previous = panel.history.at(-1);
    if (previous) {
      setPanel({
        kind: previous.record.kind,
        loading: false,
        error: null,
        record: previous.record,
        history: panel.history.slice(0, -1),
      });
      window.requestAnimationFrame(() => document.getElementById(previous.openerId)?.focus());
      return;
    }
    const openerId = directoryOpener.current;
    directoryOpener.current = null;
    setPanel(null);
    window.requestAnimationFrame(() => {
      if (openerId) document.getElementById(openerId)?.focus();
    });
  }

  if (panel) {
    return <ContextProfilePanel
      panel={panel}
      close={closePanel}
      openFarm={(id, openerId) => void openFarm(id, openerId, true)}
      openField={(id, openerId) => void openField(id, openerId)}
      openPerson={(kind, id, openerId) => void openPerson(kind, id, openerId)}
    />;
  }

  const reportedTotal = filters.state === "reported" || filters.state === "all" ? state.trackwick?.counts.farm_candidates : undefined;
  const canLoadMore = Boolean(reportedTotal && directory.items.length < reportedTotal);
  return <section className="single-surface fields-stage farm-directory">
    <div className="surface-heading"><div><p className="eyebrow">Farm directory</p><h2>Farms</h2></div><span className="count-badge">{reportedTotal ? `${count(directory.items.length)} of ${count(reportedTotal)}` : count(directory.items.length)}</span></div>
    <form className="directory-filters" onSubmit={applyFilters}>
      <label>State<select value={draftFilters.state} onChange={(event) => setDraftFilters((current) => ({ ...current, state: event.target.value as DirectoryFilters["state"] }))}><option value="all">All states</option><option value="reviewed">Reviewed</option><option value="reported">Reported</option></select></label>
      <label>Search<input type="search" maxLength={80} value={draftFilters.query} onChange={(event) => setDraftFilters((current) => ({ ...current, query: event.target.value }))} placeholder="Farm name" /></label>
      <label>From<input type="date" value={draftFilters.dateFrom} onChange={(event) => setDraftFilters((current) => ({ ...current, dateFrom: event.target.value }))} /></label>
      <label>To<input type="date" value={draftFilters.dateTo} onChange={(event) => setDraftFilters((current) => ({ ...current, dateTo: event.target.value }))} /></label>
      <div className="directory-filter-actions"><button className="quiet-button" type="submit" disabled={!canOpenProfiles || directory.loading}>Apply filters</button><button className="text-link" type="button" onClick={clearFilters}>Clear</button></div>
    </form>
    {!canOpenProfiles
      ? <EmptyState focusId={MANAGER_ACCESS_BOUNDARY_ID} title="Sign in to open the Farm directory" detail="The private source directory is available to named Fortune admins. Reported candidates remain distinct from reviewed Farms." action={{ href: "/login?next=/fields", label: "Sign in" }} />
      : directory.loading
        ? <p className="empty-copy" role="status">Reading the Farm directory…</p>
        : directory.error
          ? <p className="profile-message profile-error" role="alert">{directory.error} <a href="/manager">Re-authenticate in Farm Truth</a></p>
          : directory.items.length
            ? <><div className="farm-card-grid">{directory.items.map((farm) => farm.state === "reported"
              ? <article className="farm-directory-card reported-candidate-card" key={farm.id}><div><span className="status-chip reported">reported candidate</span><h3>{farm.name}</h3><p>{farm.reported_farmer_name} · source context awaiting review</p></div><dl><div><dt>Reported plots</dt><dd>{count(farm.reported_plot_count || undefined)}</dd></div><div><dt>Open source work</dt><dd>{count(farm.open_work_count)}</dd></div><div><dt>Latest update</dt><dd>{dateTime(farm.latest_update_at)}</dd></div></dl><ProfileControl canOpenProfiles controlId={`reported-farm-directory-${farm.id}`} label={`Open reported candidate profile for ${farm.name}`} text="Review reported profile" open={(openerId) => void openReportedFarm(farm.destination.id, openerId)} /></article>
              : <article className="farm-directory-card" key={farm.id}><div><span className="status-chip">{farm.state}</span><h3>{farm.name}</h3><p>{farm.crops.join(" · ") || "No active crop recorded"}</p></div><dl><div><dt>Fields</dt><dd>{count(farm.field_count)}</dd></div><div><dt>Open work</dt><dd>{count(farm.open_work_count)}</dd></div><div><dt>Latest update</dt><dd>{dateTime(farm.latest_update_at)}</dd></div></dl><ProfileControl canOpenProfiles controlId={`farm-directory-${farm.id}`} label={`Open ${farm.name} Farm profile`} text="Open Farm" open={(openerId) => void openFarm(farm.id, openerId)} /></article>)}</div>{canLoadMore ? <button className="quiet-button directory-more" type="button" onClick={() => setDirectoryPage((current) => current + 1)} disabled={directory.loading}>Show {count(Math.min(FARM_DIRECTORY_PAGE_SIZE, reportedTotal! - directory.items.length))} more ({count(reportedTotal! - directory.items.length)} remaining)</button> : null}</>
            : <EmptyState title="No Farms match these filters." detail={t.noData + " Reported source candidates do not become Farms until they are reviewed."} />}
  </section>;
}

function ContextProfilePanel({ panel, close, openFarm, openField, openPerson }: {
  panel: ContextPanel;
  close: () => void;
  openFarm: (id: string, openerId: string) => void;
  openField: (id: string, openerId: string) => void;
  openPerson: (kind: PersonKind, id: string, openerId: string) => void;
}) {
  const backTarget = panel.history.at(-1)?.record.name || "Farms";
  const subject = panel.kind === "field_worker" ? "Field Worker" : roleName(panel.kind);
  return <aside className="single-surface profile-panel entity-profile-panel" aria-label={`${subject} context`} aria-busy={panel.loading}>
    <button type="button" className="quiet-button profile-back" onClick={close} autoFocus>Back to {backTarget}</button>
    {panel.loading
      ? <p className="profile-message" role="status">Reading this {subject} context…</p>
      : panel.error
        ? <p className="profile-message profile-error" role="alert">{panel.error} {panel.reauth ? <a href="/manager">Re-authenticate in Farm Truth</a> : null}</p>
        : panel.record?.kind === "farm" && panel.record.state === "reported"
          ? <ReportedFarmPanel record={panel.record} />
          : panel.record?.kind === "farm"
          ? <FarmRecordPanel record={panel.record} openField={openField} openPerson={openPerson} />
          : panel.record?.kind === "field"
            ? <FieldRecordPanel record={panel.record} openFarm={openFarm} openPerson={openPerson} />
            : panel.record
              ? <PersonContextPanel record={panel.record} openFarm={openFarm} openField={openField} />
              : null}
  </aside>;
}

function ReportedFarmPanel({ record }: { record: ReportedFarmProfile }) {
  const photoReferences = record.reported.plot_photo_references + record.reported.crop_photo_references;
  return <div className="entity-profile-content reported-farm-context">
    <p className="eyebrow">Reported farm candidate</p>
    <h2>{record.name}</h2>
    <p className="profile-context">TrackWick reported this candidate. It is not a reviewed Farm, Field boundary, or crop allocation.</p>
    <div className="farm-profile-sections">
      <section>
        <h3>Source footprint</h3>
        <dl className="profile-facts">
          <div><dt>Reported farmer</dt><dd>{record.reported.farmer_name}</dd></div>
          <div><dt>Reported place</dt><dd>{record.reported.place}</dd></div>
          <div><dt>Reported area</dt><dd>{record.reported.reported_area_acres == null ? "Not reported" : `${record.reported.reported_area_acres} acres`}</dd></div>
          <div><dt>Reported plots</dt><dd>{count(record.reported.reported_plot_count || undefined)}</dd></div>
        </dl>
      </section>
      <section>
        <h3>Evidence &amp; activity</h3>
        <dl className="profile-facts">
          <div><dt>Open source work</dt><dd>{count(record.reported.open_work)}</dd></div>
          <div><dt>Latest activity</dt><dd>{dateTime(record.reported.latest_activity_at)}</dd></div>
          <div><dt>Photo references</dt><dd>{count(photoReferences)} reported references; media remains private</dd></div>
        </dl>
      </section>
      <section>
        <h3>Review state</h3>
        <p className="profile-context">This source footprint can inform a review, but no boundary, crop allocation, owner relationship, or operational action has been created from it.</p>
        {record.limitations.map((limitation) => <p className="context-limitation" key={limitation}>{limitation}</p>)}
        <div className="profile-action"><a className="primary-action" href="/manager?review=farm-truth">Open review workspace <span aria-hidden="true">→</span></a></div>
      </section>
    </div>
  </div>;
}

function FarmRecordPanel({ record, openField, openPerson }: {
  record: FarmRecord;
  openField: (id: string, openerId: string) => void;
  openPerson: (kind: PersonKind, id: string, openerId: string) => void;
}) {
  return <div className="entity-profile-content">
    <p className="eyebrow">Reviewed Farm</p>
    <h2>{record.name}</h2>
    <div className="farm-profile-sections">
      <section>
        <h3>Now</h3>
        <div className="profile-summary-line"><span>{count(record.now.open_work_count)} open work</span><span>Latest update {dateTime(record.now.latest_update_at)}</span></div>
        <div className="entity-chip-list" aria-label="Fields">
          {record.now.fields.length ? record.now.fields.map((field) => <button id={`farm-field-${record.id}-${field.id}`} className="entity-chip entity-chip-link" type="button" key={field.id} onClick={(event) => openField(field.id, event.currentTarget.id)}>{field.name} <span aria-hidden="true">→</span></button>) : <span className="empty-copy">No reviewed Fields</span>}
        </div>
      </section>
      <section>
        <h3>People</h3>
        {record.people.length ? <ul className="entity-link-list">{record.people.map((person, index) => <li key={`${person.id}-${person.field_id}-${person.role}`}><button id={`farm-person-${record.id}-${person.id}-${index}`} className="context-link" type="button" onClick={(event) => openPerson(person.kind, person.id, event.currentTarget.id)}><strong>{person.name}</strong><span>{roleName(person.role)} · {person.field_name}</span></button></li>)}</ul> : <p className="empty-copy">No reviewed Farmer or Field Worker relationship is attached.</p>}
      </section>
      <section>
        <h3>Updates</h3>
        <EntityUpdates updates={record.updates} />
      </section>
      <section>
        <h3>Context</h3>
        <p className="profile-context">{record.context.message}</p>
        {record.limitations.map((limitation) => <p className="context-limitation" key={limitation}>{limitation}</p>)}
      </section>
    </div>
  </div>;
}

function FieldRecordPanel({ record, openFarm, openPerson }: {
  record: FieldRecord;
  openFarm: (id: string, openerId: string) => void;
  openPerson: (kind: PersonKind, id: string, openerId: string) => void;
}) {
  return <div className="entity-profile-content field-context">
    <p className="eyebrow">Reviewed Field</p>
    <h2>{record.name}</h2>
    <div className="profile-summary-line"><span>{record.area_hectares == null ? "Area not recorded" : `${record.area_hectares} hectares`}</span><span>Geometry {roleName(record.geometry.state)}</span></div>
    {record.farm ? <button id={`field-farm-${record.id}-${record.farm.id}`} className="context-link context-parent-link" type="button" onClick={(event) => openFarm(record.farm!.id, event.currentTarget.id)}><strong>{record.farm.name}</strong><span>Open Farm <span aria-hidden="true">→</span></span></button> : <p className="empty-copy">This Field is not attached to an active reviewed Farm.</p>}
    <section className="field-crop-seasons">
      <h3>Crop seasons</h3>
      {record.allocations.length ? <div className="entity-chip-list">{record.allocations.map((allocation) => <span className="entity-chip crop-season-chip" key={allocation.id}><strong>{allocation.crop_name}{allocation.cultivar ? ` · ${allocation.cultivar}` : ""}</strong>{allocation.season_name} · {allocation.starts_on} to {allocation.ends_on} · {roleName(allocation.status)}</span>)}</div> : <p className="empty-copy">No crop season is recorded for this Field.</p>}
    </section>
      <section>
        <h3>People</h3>
      {record.people.length ? <ul className="entity-link-list">{record.people.map((person, index) => <li key={`${person.id}-${person.role}-${index}`}><button id={`field-person-${record.id}-${person.id}-${index}`} className="context-link" type="button" onClick={(event) => openPerson(person.kind, person.id, event.currentTarget.id)}><strong>{person.name}</strong><span>{roleName(person.role)}</span></button></li>)}</ul> : <p className="empty-copy">No reviewed people are attached to this Field.</p>}
      </section>
      <section>
        <h3>Geometry</h3>
        <p className="profile-context">{record.geometry.message || "A reviewed field boundary is required before this Field can appear on a map."}</p>
        <p className="context-limitation">TrackWick source points, village context, and reported areas never become a Field boundary.</p>
      </section>
      <section>
      <h3>Updates</h3>
      <EntityUpdates updates={record.updates} />
    </section>
    {record.limitations.map((limitation) => <p className="context-limitation" key={limitation}>{limitation}</p>)}
  </div>;
}

function PersonContextPanel({ record, openFarm, openField }: {
  record: PersonContext;
  openFarm: (id: string, openerId: string) => void;
  openField: (id: string, openerId: string) => void;
}) {
  return <div className="entity-profile-content person-context">
    <p className="eyebrow">Reviewed {record.kind === "farmer" ? "Farmer" : "Field Worker"}</p>
    <h2>{record.name}</h2>
    <section>
      <h3>Assignments</h3>
      <ul className="assignment-list">{record.assignments.map((assignment, index) => <li key={`${assignment.farm_id}-${assignment.field_id}-${assignment.role}`}><div><strong>{roleName(assignment.role)}</strong><span>Since {assignment.starts_on}</span></div><div className="assignment-links"><button id={`person-farm-${record.id}-${index}`} className="entity-chip entity-chip-link" type="button" onClick={(event) => openFarm(assignment.farm_id, event.currentTarget.id)}>{assignment.farm_name}</button><button id={`person-field-${record.id}-${index}`} className="entity-chip entity-chip-link" type="button" onClick={(event) => openField(assignment.field_id, event.currentTarget.id)}>{assignment.field_name}</button></div></li>)}</ul>
    </section>
    <section>
      <h3>Context</h3>
      <p className="profile-context">{record.context.message}</p>
      {record.limitations.map((limitation) => <p className="context-limitation" key={limitation}>{limitation}</p>)}
    </section>
  </div>;
}

function EntityUpdates({ updates }: { updates: EntityUpdate[] }) {
  if (!updates.length) return <p className="empty-copy">No updates in this record.</p>;
  return <ol className="entity-update-list">{updates.map((update) => {
    const disease = update.finding_kind === "disease";
    const severity = update.declared_severity || "not declared";
    return <li className={disease ? "disease-update" : undefined} key={`${update.kind}-${update.id}`}>
      <div><span className={`status-chip ${update.state}`}>{update.state}</span>{disease ? <span className={`severity ${severity}`}>{severity} severity</span> : null}</div>
      <strong>{disease ? "Disease reported" : update.summary}</strong>
      <time dateTime={update.occurred_at}>{dateTime(update.occurred_at)}</time>
      <p>{disease ? `Reported event with ${severity} declared severity. This is not a diagnosis.` : [update.field_name, update.actor, update.status ? roleName(update.status) : null].filter(Boolean).join(" · ")}</p>
    </li>;
  })}</ol>;
}

function FarmersView({ farmers, readiness, trackwick, canOpenProfiles, selection, openProfile, closeProfile }: {
  farmers: ReviewedFarmerCard[];
  readiness: PilotReadiness | null;
  trackwick: TrackwickBoard | null;
  canOpenProfiles: boolean;
  selection: ProfileSelection | null;
  openProfile: (id: string, kind: PersonKind, recordState: "reviewed" | "reported", openerId: string) => Promise<void>;
  closeProfile: () => void;
}) {
  const sourceFarmers = trackwick?.farmers || [];
  if (selection) return <ProfileReading selection={selection} close={closeProfile} />;
  return <section className="single-surface people-stage">
    <div className="surface-heading"><div><p className="eyebrow">{farmers.length ? "Reviewed grower relationships" : sourceFarmers.length ? "Reported farmers" : "Reviewed grower relationships"}</p><h2>{farmers.length ? "Farmers on this operating record" : sourceFarmers.length ? "Farmers reported by TrackWick" : "Farmers on this operating record"}</h2></div><span className="count-badge">{count(farmers.length || sourceFarmers.length)}</span></div>
    {farmers.length ? <div className="people-list source-card-grid">{farmers.map((person) => <article className="person-row" key={person.id}><span className="person-initial">{person.name.slice(0, 1).toUpperCase()}</span><div className="person-summary"><h3>{person.name}</h3><p>{count(person.assignment_count)} reviewed Farm assignment{person.assignment_count === 1 ? "" : "s"}</p></div><ProfileControl canOpenProfiles={canOpenProfiles} controlId={`profile-reviewed-farmer-${person.id}`} label={`Open ${person.name} farmer profile`} text="Open profile" open={(openerId) => void openProfile(person.id, "farmer", "reviewed", openerId)} /></article>)}</div> : sourceFarmers.length ? <ReportedFarmers farmers={sourceFarmers} canOpenProfiles={canOpenProfiles} openProfile={openProfile} /> : <p className="empty-copy">{readiness?.counts.people ? "No reviewed grower relationship is attached to a canonical Farm yet." : "Farmers appear here only after a reviewed grower relationship is attached to a canonical Farm."}</p>}
  </section>;
}

function ReportedFarmers({ farmers, canOpenProfiles, openProfile }: {
  farmers: TrackwickFarmer[];
  canOpenProfiles: boolean;
  openProfile: (id: string, kind: "farmer", recordState: "reported", openerId: string) => Promise<void>;
}) {
  const [visibleCount, setVisibleCount] = useState(100);
  const visible = farmers.slice(0, visibleCount);
  return <><p className="surface-copy">Reported farmers are cached TrackWick context, not sign-ins or reviewed grower relationships.</p><div className="people-list source-card-grid">{visible.map((person) => <article className="person-row" key={person.id}><span className="person-initial">{person.name.slice(0, 1).toUpperCase()}</span><div className="person-summary"><h3>{person.name}</h3><p>{person.farm_candidates} reported farm{person.farm_candidates === 1 ? "" : "s"} · {person.open_work} open source work</p></div><ProfileControl canOpenProfiles={canOpenProfiles} controlId={`profile-reported-farmer-${person.id}`} label={`Open reported farmer profile for ${person.name}`} text="Open reported profile" open={(openerId) => void openProfile(person.id, "farmer", "reported", openerId)} /></article>)}</div>{visible.length < farmers.length ? <button type="button" className="quiet-button directory-more" onClick={() => setVisibleCount((current) => current + 100)}>Show 100 more ({count(farmers.length - visible.length)} remaining)</button> : null}</>;
}

function ProfileControl({ canOpenProfiles, controlId, label, text, open }: {
  canOpenProfiles: boolean;
  controlId: string;
  label: string;
  text: string;
  open: (openerId: string) => void;
}) {
  if (!canOpenProfiles) return <Link id={controlId} className="profile-locked" href="/login">Sign in to open</Link>;
  return <button id={controlId} type="button" className="text-link profile-open" onClick={(event) => open(event.currentTarget.id)} aria-label={label}>{text} <span aria-hidden="true">→</span></button>;
}

function ProfileReading({ selection, close }: { selection: ProfileSelection; close: () => void }) {
  if (selection.profile) return <ProfilePanel profile={selection.profile} close={close} />;
  const subject = selection.kind === "field_worker" ? "field worker" : "farmer";
  return <aside className="single-surface profile-panel" aria-label={`${subject} profile`} aria-busy={selection.loading}>
    <button type="button" className="quiet-button profile-back" onClick={close} autoFocus>Back to {selection.kind === "field_worker" ? "field work" : "farmers"}</button>
    {selection.loading
      ? <p className="profile-message" role="status">Reading this {subject} profile…</p>
      : <p className="profile-message profile-error" role="alert">{selection.error} {selection.reauth ? <a href="/manager">Re-authenticate in Farm Truth</a> : null}</p>}
  </aside>;
}

function ProfilePanel({ profile, close }: { profile: PersonProfile; close: () => void }) {
  const reported = profile.state === "reported";
  const subject = profile.kind === "field_worker" ? "Field worker" : "Farmer";
  return <aside className="single-surface profile-panel" aria-label={`${profile.name} profile`}>
    <button type="button" className="quiet-button profile-back" onClick={close} autoFocus>Back to {profile.kind === "field_worker" ? "field work" : "farmers"}</button>
    <p className="eyebrow">{reported ? `Reported ${subject} context` : `Reviewed ${subject}`}</p>
    <h2>{profile.name}</h2>
    <p className="profile-context">{profile.limitations?.[0] || "Only reviewed operating relationships are shown here."}</p>
    <PersonProfileFacts profile={profile} />
    <div className="profile-action">
      {reported
        ? <a className="primary-action" href="/manager?review=farm-truth">Review in Farm Truth <span aria-hidden="true">→</span></a>
        : <a className="primary-action" href="/manager">Open in Farm Truth <span aria-hidden="true">→</span></a>}
    </div>
  </aside>;
}

function PersonProfileFacts({ profile }: { profile: PersonProfile }) {
  if (profile.state === "reported") {
    const activity = profile.reported?.source_activity;
    const latest = activity?.latest_crop_context;
    if (profile.kind === "field_worker") {
      return <dl className="profile-facts">
        <div><dt>Reported farmer reach</dt><dd>{count(profile.reported?.reported_farmer_reach)} linked through source work</dd></div>
        <div><dt>Open source work</dt><dd>{count(profile.reported?.open_work)}</dd></div>
        <div><dt>Completed source work</dt><dd>{count(profile.reported?.completed_work)}</dd></div>
        <div><dt>Latest activity</dt><dd>{dateTime(profile.reported?.latest_activity_at)}</dd></div>
        <div><dt>Latest attendance</dt><dd>{profile.reported?.latest_attendance_on ? `Reported ${profile.reported.latest_attendance_on}` : "Not reported"}</dd></div>
        <div><dt>Reported visits</dt><dd>{count(activity?.reported_visits)}</dd></div>
        <div><dt>Reported crop inputs</dt><dd>{count(activity?.reported_input_events)}</dd></div>
        <div><dt>Disease / pest reports</dt><dd>{count(activity?.reported_disease)} / {count(activity?.reported_pest)}</dd></div>
        <div><dt>Latest crop context</dt><dd>{latest ? [latest.crop_stage, latest.water_condition, latest.crop_condition_score == null ? null : `${latest.crop_condition_score}/10`].filter(Boolean).join(" · ") || `Reported ${dateTime(latest.observed_at)}` : "Not reported"}</dd></div>
        <div><dt>Geotagged evidence</dt><dd>{count(activity?.geotagged_evidence)} source points; coordinates remain private</dd></div>
        <div><dt>Account</dt><dd>{profile.account?.state === "not_created" ? "No sign-in created" : "Not reported"}</dd></div>
      </dl>;
    }
    return <dl className="profile-facts">
      <div><dt>Reported farms</dt><dd>{count(profile.reported?.farm_candidates)}</dd></div>
      <div><dt>Reported area</dt><dd>{profile.reported?.reported_area_acres == null ? "Not reported" : `${profile.reported.reported_area_acres} acres`}</dd></div>
      <div><dt>Open source work</dt><dd>{count(profile.reported?.open_work)}</dd></div>
      <div><dt>Latest activity</dt><dd>{dateTime(profile.reported?.latest_activity_at)}</dd></div>
      <div><dt>Photo references</dt><dd>{count(profile.reported?.crop_photo_references)}</dd></div>
      <div><dt>Reported visits</dt><dd>{count(activity?.reported_visits)}</dd></div>
      <div><dt>Reported crop inputs</dt><dd>{count(activity?.reported_input_events)}</dd></div>
      <div><dt>Disease / pest reports</dt><dd>{count(activity?.reported_disease)} / {count(activity?.reported_pest)}</dd></div>
      <div><dt>Latest crop context</dt><dd>{latest ? [latest.crop_stage, latest.water_condition, latest.crop_condition_score == null ? null : `${latest.crop_condition_score}/10`].filter(Boolean).join(" · ") || `Reported ${dateTime(latest.observed_at)}` : "Not reported"}</dd></div>
      <div><dt>Geotagged evidence</dt><dd>{count(activity?.geotagged_evidence)} source points; coordinates remain private</dd></div>
      <div><dt>Account</dt><dd>{profile.account?.state === "not_created" ? "No sign-in created" : "Not reported"}</dd></div>
    </dl>;
  }
  const farms = Array.from(new Map(profile.assignments.map((assignment) => [assignment.farm_id, {
    id: assignment.farm_id, name: assignment.farm_name,
  }])).values());
  return <div className="profile-groups">
    <section className="profile-relationships">
      <h3>Canonical Farms</h3>
      <ul>{farms.map((farm) => <li key={farm.id}><strong>{farm.name}</strong><Link className="text-link" href={`/fields?farm=${encodeURIComponent(farm.id)}`}>Open Farm <span aria-hidden="true">→</span></Link></li>)}</ul>
    </section>
    <section className="profile-relationships">
      <h3>Reviewed assignments</h3>
      <ul>{profile.assignments.map((assignment) => <li key={`${assignment.farm_id}-${assignment.field_id}-${assignment.role}`}><strong>{roleName(assignment.role)}</strong><span>{assignment.field_name} · {assignment.farm_name} · since {assignment.starts_on}</span></li>)}</ul>
    </section>
  </div>;
}

function ActionsView({ t, portfolio, trackwick, canOpenProfiles, selection, openProfile, closeProfile }: {
  t: Translation;
  portfolio: Portfolio | null;
  trackwick: TrackwickBoard | null;
  canOpenProfiles: boolean;
  selection: ProfileSelection | null;
  openProfile: (id: string, kind: "field_worker", recordState: "reported", openerId: string) => Promise<void>;
  closeProfile: () => void;
}) {
  const actions = portfolio?.risk_action_ledger.items || [];
  const sourceWork = trackwick?.inbox || [];
  const workers = trackwick?.field_workers || [];
  const signals = trackwick?.signals || [];
  if (selection) return <ProfileReading selection={selection} close={closeProfile} />;
  return <section className="single-surface actions-surface"><div className="surface-heading"><div><p className="eyebrow">{actions.length ? "Decision queue" : sourceWork.length ? "Reported source work" : "Decision queue"}</p><h2>{actions.length ? "Open actions" : sourceWork.length ? "Source work awaiting review" : "Open actions"}</h2></div><span className="count-badge">{count(actions.length || sourceWork.length)}</span></div>{actions.length ? <ActionRows items={actions} empty={t.noActions} /> : <ActionRows items={actions} empty={t.noActions} />}{sourceWork.length ? <section className="reported-source-work"><div className="surface-heading"><div><p className="eyebrow">Cached TrackWick work</p><h2>Source work awaiting review</h2></div><span className="count-badge">{count(sourceWork.length)}</span></div><SourceWorkRows items={sourceWork} /></section> : null}{trackwick ? <TrackwickSourceCoverage counts={trackwick.counts} /> : null}{signals.length ? <ReportedSignalQueue signals={signals} total={trackwick?.counts.reported_signals || signals.length} /> : null}{workers.length ? <ReportedFieldWorkers workers={workers} canOpenProfiles={canOpenProfiles} openProfile={openProfile} /> : null}</section>;
}

function TrackwickSourceCoverage({ counts: source }: { counts: TrackwickBoard["counts"] }) {
  return <section className="reported-source-coverage">
    <div className="surface-heading"><div><p className="eyebrow">TrackWick source coverage</p><h2>Historical field footprint</h2></div></div>
    <p className="surface-copy">Reported source context only. It becomes a Farm, Field, assignment, or action only through manager review.</p>
    <dl className="profile-facts">
      <div><dt>Reported visits</dt><dd>{count(source.reported_visits)}</dd></div>
      <div><dt>Disease / pest reports</dt><dd>{count(source.reported_signals)}</dd></div>
      <div><dt>Crop-input events</dt><dd>{count(source.reported_input_events)}</dd></div>
      <div><dt>Geotagged evidence</dt><dd>{count(source.geotagged_evidence)} source points; coordinates remain private</dd></div>
      <div><dt>Crop-photo references</dt><dd>{count(source.crop_photo_references)}; media remains private</dd></div>
    </dl>
  </section>;
}

function SourceWorkRows({ items }: { items: TrackwickWork[] }) {
  const [visibleCount, setVisibleCount] = useState(100);
  const visible = items.slice(0, visibleCount);
  return <><p className="surface-copy">These are cached TrackWick tasks. They are not yet assigned AGRO CEO actions and cannot complete work here.</p><ol className="action-list source-work-card-grid">{visible.map((item) => <li key={item.id}><span className="severity medium">reported</span><div><h3>{item.label}</h3><p>{[item.farmer_name, item.follow_up_at ? `due ${dateTime(item.follow_up_at)}` : null].filter(Boolean).join(" · ")}</p></div><a className="text-link" href="/manager?review=farm-truth">Review <span aria-hidden="true">→</span></a></li>)}</ol>{visible.length < items.length ? <button type="button" className="quiet-button directory-more" onClick={() => setVisibleCount((current) => current + 100)}>Show 100 more ({count(items.length - visible.length)} remaining)</button> : null}</>;
}

function ReportedFieldWorkers({ workers, canOpenProfiles, openProfile }: {
  workers: TrackwickFieldWorker[];
  canOpenProfiles: boolean;
  openProfile: (id: string, kind: "field_worker", recordState: "reported", openerId: string) => Promise<void>;
}) {
  const [visibleCount, setVisibleCount] = useState(40);
  const visible = workers.slice(0, visibleCount);
  return <section className="reported-field-workers">
    <div className="surface-heading"><div><p className="eyebrow">Reported field workers</p><h2>Source work coverage</h2></div><span className="count-badge">{count(workers.length)}</span></div>
    <p className="surface-copy">Coverage is derived only from cached TrackWick source work. It is not a reviewed assignment, account, or farmer relationship.</p>
    <div className="people-list source-card-grid">{visible.map((worker) => <article className="person-row" key={worker.id}><span className="person-initial">{worker.name.slice(0, 1).toUpperCase()}</span><div className="person-summary"><h3>{worker.name}</h3><p>{count(worker.reported_farmer_reach)} reported farmer reach · {count(worker.open_work)} open source work</p></div><ProfileControl canOpenProfiles={canOpenProfiles} controlId={`profile-reported-field-worker-${worker.id}`} label={`Open reported field worker profile for ${worker.name}`} text="Open reported profile" open={(openerId) => void openProfile(worker.id, "field_worker", "reported", openerId)} /></article>)}</div>{visible.length < workers.length ? <button type="button" className="quiet-button directory-more" onClick={() => setVisibleCount((current) => current + 40)}>Show 40 more ({count(workers.length - visible.length)} remaining)</button> : null}
  </section>;
}

function ReportedSignalQueue({ signals, total }: { signals: TrackwickSignal[]; total: number }) {
  const [kind, setKind] = useState<"all" | TrackwickSignal["finding_kind"]>("all");
  const [severity, setSeverity] = useState<"all" | TrackwickSignal["declared_severity"]>("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [visibleCount, setVisibleCount] = useState(100);
  const filtered = signals.filter((signal) => {
    const observedOn = signal.observed_at.slice(0, 10);
    return (kind === "all" || signal.finding_kind === kind)
      && (severity === "all" || signal.declared_severity === severity)
      && (!from || observedOn >= from)
      && (!to || observedOn <= to);
  });
  const visible = filtered.slice(0, visibleCount);
  return <section className="reported-signal-queue">
    <div className="surface-heading"><div><p className="eyebrow">Reported field signals</p><h2>Disease &amp; pest reports</h2></div><span className="count-badge">{count(filtered.length)} of {count(total)}</span></div>
    <p className="surface-copy">Declared TrackWick observations only. A report is not a diagnosis, verified field attribution, or AGRO CEO action.</p>
    <div className="signal-filters" aria-label="Filter reported field signals">
      <label>Type<select value={kind} onChange={(event) => setKind(event.target.value as typeof kind)}><option value="all">All reports</option><option value="disease">Disease</option><option value="pest">Pest</option></select></label>
      <label>Severity<select value={severity} onChange={(event) => setSeverity(event.target.value as typeof severity)}><option value="all">All severities</option><option value="critical">Critical</option><option value="high">High</option><option value="moderate">Moderate</option><option value="low">Low</option><option value="unknown">Not declared</option></select></label>
      <label>From<input type="date" value={from} onChange={(event) => setFrom(event.target.value)} /></label>
      <label>To<input type="date" value={to} onChange={(event) => setTo(event.target.value)} /></label>
    </div>
    {filtered.length ? <><ol className="action-list reported-signal-list">{visible.map((signal) => <li key={signal.id}><span className={`severity ${signal.declared_severity}`}>{signal.declared_severity}</span><div><h3>{signal.finding_kind === "disease" ? "Disease reported" : "Pest reported"}</h3><p>{[signal.farmer_name, dateTime(signal.observed_at)].filter(Boolean).join(" · ")} · This is not a diagnosis.</p></div><a className="text-link" href="/manager?review=farm-truth">Review <span aria-hidden="true">→</span></a></li>)}</ol>{visible.length < filtered.length ? <button type="button" className="quiet-button" onClick={() => setVisibleCount((current) => current + 100)}>Show 100 more ({count(filtered.length - visible.length)} remaining)</button> : null}</> : <p className="empty-copy">No reported signals match these filters.</p>}
  </section>;
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

function EmptyState({ title, detail, focusId, action }: { title: string; detail: string; focusId?: string; action?: { href: string; label: string } }) {
  return <section id={focusId} tabIndex={focusId ? -1 : undefined} className="empty-state"><strong>{title}</strong><p>{detail}</p>{action ? <Link className="text-link" href={action.href}>{action.label} <span aria-hidden="true">→</span></Link> : null}</section>;
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
