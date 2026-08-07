"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CommandSearch, CommandSearchItem } from "./command-search";
import { FarmActivityFilter, FarmOrder, FarmStateFilter, MultiFilter, SortMenu } from "./directory-controls";

type View = "home" | "map" | "fields" | "farmers" | "actions" | "settings";
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
type OperatingTag = { key: string; label: string; tone: "attention" | "current" | "neutral" };
type OperatingSnapshot = {
  metrics: {
    farm_count: number;
    farmer_count: number;
    open_task_count: number;
    completed_work_count: number;
    visit_count: number;
    disease_report_count: number;
    pest_report_count: number;
    location_evidence_count: number;
    photo_reference_count: number;
    attendance_present_days: number;
    reported_area_acres?: number | null;
    latest_activity_at?: string | null;
    refreshed_at?: string | null;
  };
  tags: OperatingTag[];
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
  operating?: OperatingSnapshot;
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
  operating?: OperatingSnapshot;
};
type TrackwickFieldWorker = {
  id: string;
  name: string;
  reported_farmer_reach: number;
  open_work: number;
  completed_work: number;
  latest_activity_at?: string | null;
  latest_attendance_on?: string | null;
  operating?: OperatingSnapshot;
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
  map?: { points: Array<MapPoint>; total_points: number; truncated: boolean };
};
type MapSubjectKind = "reported_farm" | "farmer" | "field_worker" | "work" | "point";
type MapPoint = {
  id: string;
  latitude: number;
  longitude: number;
  kind: string;
  confidence: string;
  observed_at: string;
  label: string;
  subject: { kind: MapSubjectKind; id: string | null; name: string; place: string | null; farmer_name: string | null; open_work: number; operating?: OperatingSnapshot };
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
  operating?: OperatingSnapshot;
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
  operating?: OperatingSnapshot;
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
    operating?: OperatingSnapshot;
  };
  limitations: string[];
};
type FarmCandidateCase = {
  id: string;
  status: "open" | "held" | "accepted" | "rejected";
  updated_at: string;
  farm_name_suggestion: string;
  farmer_name: string;
  limitations: string[];
  accepted_farm_id?: string | null;
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
    field_id?: string;
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
  state: FarmStateFilter[];
  activity: FarmActivityFilter[];
  order: FarmOrder;
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
    operating?: OperatingSnapshot;
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
    operating?: OperatingSnapshot;
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

type OperatingAgent = { id: string; name: string; count: number; summary: string };
type CustomAgent = { id: string; name: string; instruction: string; enabled: boolean; updated_at: string };
type AgentBoard = { agents: OperatingAgent[]; custom_agents: CustomAgent[] };

type State = {
  profile: OperatingProfile | null;
  portfolio: Portfolio | null;
  runtime: Runtime | null;
  lanes: DataLanes | null;
  session: ManagerSession | null;
  readiness: PilotReadiness | null;
  trackwick: TrackwickBoard | null;
  agents: AgentBoard | null;
  canonicalFarmers: ReviewedFarmerCard[];
  procurementHistory: ProcurementHistory | null;
  loading: boolean;
  error: string | null;
  needsLaunchLogin: boolean;
  stale: boolean;
  updatedAt: string | null;
};

const EMPTY_STATE: State = {
  profile: null,
  portfolio: null,
  runtime: null,
  lanes: null,
  session: null,
  readiness: null,
  trackwick: null,
  agents: null,
  canonicalFarmers: [],
  procurementHistory: null,
  loading: true,
  error: null,
  needsLaunchLogin: false,
  stale: false,
  updatedAt: null,
};

const OPERATING_CACHE_KEY = "agro-ceo-operating-record-v1";
const DIRECTORY_CACHE_PREFIX = "agro-ceo-farm-directory-v1:";
const PROFILE_CACHE_PREFIX = "agro-ceo-profile-v1:";

function readSessionCache<T>(key: string): T | null {
  try {
    const saved = window.sessionStorage.getItem(key);
    return saved ? JSON.parse(saved) as T : null;
  } catch { return null; }
}

function writeSessionCache(key: string, value: unknown) {
  try { window.sessionStorage.setItem(key, JSON.stringify(value)); } catch { /* caching never blocks the record */ }
}

type Translation = {
  home: string; map: string; fields: string; farmers: string; actions: string; settings: string;
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
    home: "Home", map: "Map", fields: "Farms", farmers: "Farmers", actions: "Agents", settings: "Settings",
    refresh: "Refresh", updated: "Updated", loading: "Reading the operating record…",
    noData: "Nothing has been verified here yet.", open: "Open", fieldMap: "Field map",
    programmeContext: "Programme context", notFieldMap: "This is public programme context, not a farm boundary.",
    reviewedFields: "Reviewed fields", people: "People", nextMove: "Agents", dataReadiness: "Data readiness",
    unlock: "Unlock manager actions", lock: "Lock manager actions", manager: "Manager access",
    signIn: "Sign in", signal: "signals", source: "sources", fieldUpdates: "field updates",
    evidence: "Proof required", work: "work", noActions: "No open actions need attention.",
    english: "EN", hindi: "हि", operator: "Field team", farm: "Farm", received: "Observed",
    farmTruth: "Review",
  },
  hi: {
    home: "होम", map: "नक्शा", fields: "फार्म", farmers: "किसान", actions: "एजेंट", settings: "सेटिंग्स",
    refresh: "ताज़ा करें", updated: "अपडेट", loading: "रिकॉर्ड पढ़ा जा रहा है…",
    noData: "अभी यहां कोई सत्यापित जानकारी नहीं है।", open: "खुला", fieldMap: "खेत का नक्शा",
    programmeContext: "कार्यक्रम संदर्भ", notFieldMap: "यह सार्वजनिक कार्यक्रम संदर्भ है, खेत की सीमा नहीं।",
    reviewedFields: "सत्यापित खेत", people: "लोग", nextMove: "एजेंट", dataReadiness: "डेटा की तैयारी",
    unlock: "मैनेजर कार्रवाइयां खोलें", lock: "मैनेजर कार्रवाइयां बंद करें", manager: "मैनेजर पहुंच",
    signIn: "साइन इन", signal: "संकेत", source: "स्रोत", fieldUpdates: "खेत अपडेट",
    evidence: "प्रमाण ज़रूरी", work: "काम", noActions: "ध्यान देने वाला कोई खुला काम नहीं है।",
    english: "EN", hindi: "हि", operator: "फील्ड टीम", farm: "फार्म", received: "देखा गया",
    farmTruth: "Review",
  },
};

const NAV: Array<{ view: View; href: string }> = [
  { view: "home", href: "/home" },
  { view: "map", href: "/map" },
  { view: "fields", href: "/farms" },
  { view: "farmers", href: "/farmers" },
  { view: "actions", href: "/actions" },
  { view: "settings", href: "/settings" },
];

async function readJson<T>(url: string, init?: RequestInit): Promise<{ value: T; response: Response }> {
  const response = await fetch(url, { credentials: "same-origin", cache: "no-store", ...init });
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

function personName(value: string) {
  const match = value.match(/\(([^)]+)\)/);
  return match?.[1] || value.replace(/^FC-\d+\s*/i, "").trim() || value;
}

function personCode(value: string) {
  return value.match(/^(FC-\d+)/i)?.[1] || "";
}

function dateTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "—" : new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" }).format(date);
}

function hasRecentActivity(value?: string | null, days = 30) {
  if (!value) return false;
  const timestamp = new Date(value).valueOf();
  return !Number.isNaN(timestamp) && timestamp >= Date.now() - days * 24 * 60 * 60 * 1000;
}

function updatedAgo(value?: string | null) {
  if (!value) return "No update yet";
  const timestamp = new Date(value).valueOf();
  if (Number.isNaN(timestamp)) return "No update yet";
  const elapsed = Math.max(0, Date.now() - timestamp);
  const minutes = Math.floor(elapsed / 60_000);
  if (minutes < 1) return "Updated just now";
  if (minutes < 60) return `Updated ${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `Updated ${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  if (days < 60) return `Updated ${days} day${days === 1 ? "" : "s"} ago`;
  const months = Math.floor(days / 30);
  return `Updated ${months} month${months === 1 ? "" : "s"} ago`;
}

function OperatingTagChips({ snapshot, limit = 3 }: { snapshot?: OperatingSnapshot; limit?: number }) {
  return <>{snapshot?.tags.slice(0, limit).map((tag) => <span className={`operating-tag ${tag.tone}`} key={tag.key}>{tag.label}</span>)}</>;
}

function OperatingTags({ snapshot, limit = 3, className = "" }: { snapshot?: OperatingSnapshot; limit?: number; className?: string }) {
  if (!snapshot?.tags.length) return null;
  return <div className={`operating-tags ${className}`.trim()}><OperatingTagChips snapshot={snapshot} limit={limit} /></div>;
}

function activityTimestamp(value?: string | null) {
  const timestamp = value ? new Date(value).valueOf() : 0;
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function matchesActivityFilters(value: string | null | undefined, openWork: number, filters: FarmActivityFilter[]) {
  if (filters.includes("all")) return true;
  const timestamp = activityTimestamp(value);
  const age = timestamp ? Date.now() - timestamp : Number.POSITIVE_INFINITY;
  return filters.includes("open_tasks") && openWork > 0
    || filters.includes("updated_week") && age <= 7 * 86_400_000
    || filters.includes("updated_month") && age <= 30 * 86_400_000
    || filters.includes("no_recent_update") && age > 30 * 86_400_000;
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
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [profileSelection, setProfileSelection] = useState<ProfileSelection | null>(null);
  const stateRef = useRef<State>(EMPTY_STATE);
  const loadRequest = useRef<Promise<void> | null>(null);
  const profileRequest = useRef(0);
  const profileOpener = useRef<string | null>(null);
  const t = WORDS[language];

  useEffect(() => {
    try {
      const cached = window.sessionStorage.getItem(OPERATING_CACHE_KEY);
      if (!cached) return;
      const value = JSON.parse(cached) as Partial<State>;
      if (!value.session?.authenticated) return;
      setState((current) => ({ ...current, ...value, session: { authenticated: true }, loading: false, error: null }));
    } catch { /* a bad local cache should never block the operating record */ }
  }, []);

  useEffect(() => { stateRef.current = state; }, [state]);

  useEffect(() => {
    if (state.session && !state.session.authenticated) {
      try { window.sessionStorage.removeItem(OPERATING_CACHE_KEY); } catch { /* cache cleanup never blocks the record */ }
      return;
    }
    if (!state.session?.authenticated || !state.profile || !state.trackwick) return;
    try {
      const { session: _session, loading: _loading, error: _error, needsLaunchLogin: _needsLaunchLogin, ...cached } = state;
      window.sessionStorage.setItem(OPERATING_CACHE_KEY, JSON.stringify({ ...cached, session: { authenticated: true } }));
    } catch { /* cache is an enhancement, not a dependency */ }
  }, [state]);

  const load = useCallback(() => {
    if (loadRequest.current) return loadRequest.current;
    const request = (async () => {
    setState((current) => ({ ...current, loading: current.profile === null, error: null }));
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
    if (status === 401) {
      setState((current) => ({ ...current, loading: false, needsLaunchLogin: true }));
      return;
    }
    const previous = stateRef.current;
    const session = results[4].status === "fulfilled" ? results[4].value.value : previous.session;
    const hasPrivateAccess = Boolean(session?.authenticated);
    const privateResults = hasPrivateAccess
      ? await Promise.allSettled([
          readJson<TrackwickBoard>("/api/v1/trackwick/command-centre-board").then(({ value }) => value),
          readJson<ReviewedFarmerCard[]>("/api/v1/people?kind=farmer&limit=100").then(({ value }) => value),
          readJson<AgentBoard>("/api/v1/agents").then(({ value }) => value),
        ])
      : [];
    const privateFailed = privateResults.some((result) => result.status === "rejected");
    const currentRecordExists = Boolean(previous.profile);
    setState((current) => ({
      profile: results[0].status === "fulfilled" ? results[0].value.value : current.profile,
      portfolio: results[1].status === "fulfilled" ? results[1].value.value : current.portfolio,
      runtime: results[2].status === "fulfilled" ? results[2].value.value : current.runtime,
      lanes: results[3].status === "fulfilled" ? results[3].value.value : current.lanes,
      session,
      readiness: results[5].status === "fulfilled" ? results[5].value.value : current.readiness,
      trackwick: hasPrivateAccess ? (privateResults[0]?.status === "fulfilled" ? privateResults[0].value : current.trackwick) : null,
      agents: hasPrivateAccess ? (privateResults[2]?.status === "fulfilled" ? privateResults[2].value : current.agents) : null,
      canonicalFarmers: hasPrivateAccess ? (privateResults[1]?.status === "fulfilled" ? privateResults[1].value : current.canonicalFarmers) : [],
      procurementHistory: results[6].status === "fulfilled" ? results[6].value.value : current.procurementHistory,
      loading: false,
      needsLaunchLogin: !session?.authenticated && !currentRecordExists,
      stale: Boolean(rejected || privateFailed),
      updatedAt: rejected || privateFailed ? current.updatedAt : new Date().toISOString(),
      error: rejected && !currentRecordExists ? "The live record could not be reached." : null,
    }));
    })();
    loadRequest.current = request;
    void request.then(
      () => { if (loadRequest.current === request) loadRequest.current = null; },
      () => { if (loadRequest.current === request) loadRequest.current = null; },
    );
    return request;
  }, []);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    let lastRevalidation = 0;
    const revalidate = () => {
      if (document.visibilityState === "hidden" || Date.now() - lastRevalidation < 30_000) return;
      lastRevalidation = Date.now();
      void load();
    };
    window.addEventListener("focus", revalidate);
    window.addEventListener("online", revalidate);
    document.addEventListener("visibilitychange", revalidate);
    return () => {
      window.removeEventListener("focus", revalidate);
      window.removeEventListener("online", revalidate);
      document.removeEventListener("visibilitychange", revalidate);
    };
  }, [load]);

  useEffect(() => {
    function openSearch(event: KeyboardEvent) {
      if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "f") return;
      event.preventDefault();
      setSearchOpen(true);
    }
    window.addEventListener("keydown", openSearch);
    return () => window.removeEventListener("keydown", openSearch);
  }, []);

  async function openPersonProfile(
    id: string, kind: PersonKind, recordState: "reviewed" | "reported", openerId: string,
  ) {
    if (!state.session?.authenticated) return;
    profileOpener.current = openerId;
    const request = ++profileRequest.current;
    const cacheKey = `${PROFILE_CACHE_PREFIX}${recordState}:${kind}:${id}`;
    const cached = readSessionCache<PersonProfile>(cacheKey);
    setProfileSelection({ kind, loading: !cached, error: null, profile: cached });
    try {
      const { value } = recordState === "reviewed"
        ? await readJson<PersonContext>("/api/v1/people/" + kind + "/" + id)
        : kind === "farmer"
          ? await readJson<ReportedFarmerProfile>("/api/v1/reported-farmer-profiles/" + id)
          : await readJson<ReportedFieldWorkerProfile>("/api/v1/reported-field-worker-profiles/" + id);
      if (request === profileRequest.current) {
        writeSessionCache(cacheKey, value);
        setProfileSelection({ kind, loading: false, error: null, profile: value });
      }
    } catch (error) {
      if (request === profileRequest.current) {
        if (cached) return;
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
          <button type="button" className="tool-icon language-toggle" onClick={() => setLanguage((current) => current === "en" ? "hi" : "en")} aria-label="Switch interface language">{language === "en" ? t.hindi : t.english}</button>
          <button type="button" className="tool-icon" onClick={() => setSearchOpen(true)} aria-label="Search farms, farmers, and workers" title="Search (⌘F)"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.8" cy="10.8" r="6.8" /><path d="m16 16 4.2 4.2" /></svg></button>
          <button type="button" className="tool-icon" aria-label="Notifications" title="Notifications"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></svg></button>
          <div className="profile-menu"><button type="button" className="profile-avatar" onClick={() => setProfileMenuOpen((current) => !current)} aria-expanded={profileMenuOpen} aria-label="Fortune Farms menu"><img src="/favicon.png" alt="" /></button>{profileMenuOpen ? <div className="profile-dropdown"><strong>Fortune Farms</strong><Link href="/settings" onClick={() => setProfileMenuOpen(false)}>Settings</Link></div> : null}</div>
        </div>
      </header>
      {searchOpen ? <CommandSearch items={commandSearchItems(state)} close={() => setSearchOpen(false)} refresh={() => void load()} /> : null}

      {view === "home" || view === "map" ? <section className={`command-intro ${view === "map" ? "command-intro-compact" : ""}`}>
        <div>
          <p className="eyebrow">{state.profile?.coverage_label || "Fortune Farms"}</p>
          <h1>{headingFor(view, t)}</h1>
        </div>
      </section> : null}

      {state.error ? <p className="honest-notice" role="status">{state.error}</p> : state.stale ? <p className="honest-notice honest-notice-stale" role="status">Showing saved data while we reconnect.</p> : null}
      {view === "home" ? <HomeView t={t} state={state} /> : null}
      {view === "map" ? <MapView state={state} /> : null}
      {view === "fields" ? <FieldsView t={t} state={state} canOpenProfiles={Boolean(state.session?.authenticated)} accessResolved={state.session !== null} expireManagerSession={expireManagerSession} /> : null}
      {view === "farmers" ? <FarmersView farmers={state.canonicalFarmers} readiness={state.readiness} trackwick={state.trackwick} canOpenProfiles={Boolean(state.session?.authenticated)} accessResolved={state.session !== null} selection={profileSelection} openProfile={openPersonProfile} closeProfile={closeProfile} /> : null}
      {view === "actions" ? <AgentsView agents={state.agents} reload={() => void load()} /> : null}
      {view === "settings" ? <SettingsView t={t} state={state} managerBusy={managerBusy} logout={endManagerSession} /> : null}
      <nav className="mobile-nav" aria-label="Primary views">
        {NAV.filter((item) => item.view !== "settings").map((item) => <Link key={item.view} href={item.href} aria-current={item.view === view ? "page" : undefined} className={item.view === view ? "active" : ""}>{t[item.view]}</Link>)}
      </nav>
    </main>
  );
}

function headingFor(view: View, t: Translation) {
  return ({ home: "Today, in the field.", map: "Map", fields: languageFarmHeading(t), farmers: t.farmers, actions: t.nextMove, settings: t.settings })[view];
}

function commandSearchItems(state: State): CommandSearchItem[] {
  const all: CommandSearchItem[] = [
    ...(state.trackwick?.farms || []).map((farm) => ({ id: farm.id, kind: "farm" as const, name: farm.place, detail: farm.farmer_name, href: `/farms?reported_farm=${encodeURIComponent(farm.id)}` })),
    ...(state.trackwick?.farmers || []).map((farmer) => ({ id: farmer.id, kind: "farmer" as const, name: personName(farmer.name), detail: `${count(farmer.farm_candidates)} farms · ${count(farmer.open_work)} open tasks`, href: `/farmers?person=${encodeURIComponent(farmer.id)}` })),
    ...(state.trackwick?.field_workers || []).map((worker) => ({ id: worker.id, kind: "field_worker" as const, name: worker.name, detail: `${count(worker.reported_farmer_reach)} farmers assigned · ${count(worker.open_work)} open tasks`, href: `/farmers?worker=${encodeURIComponent(worker.id)}` })),
    ...state.canonicalFarmers.map((farmer) => ({ id: farmer.id, kind: "farmer" as const, name: farmer.name, detail: `${count(farmer.assignment_count)} farms`, href: `/farmers?person=${encodeURIComponent(farmer.id)}` })),
  ];
  const seen = new Set<string>();
  return all.filter((item) => {
    const key = `${item.kind}:${item.id}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
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
  const mapPoints = trackwick?.map?.points || [];
  const locationCount = trackwick?.map?.total_points || trackwick?.counts.geotagged_evidence || 0;
  const title = reportedFarmCount ? `${count(reportedFarmCount)} farms in the field.` : nextMove?.title || firstTruth?.title || "Start with one reviewed farm.";
  const detail = reportedFarmCount
    ? `${count(trackwick?.counts.reported_visits)} visits · ${count(trackwick?.counts.reported_signals)} field issues · ${count(trackwick?.counts.open_work)} open tasks.`
    : nextMove ? actionLine(nextMove) : history ? `${count(history.coverage.quantity_qtl)} qtl across ${count(history.coverage.villages)} villages.` : "The operating record begins with a real field, not a guessed one.";
  const mapIsPreparing = state.loading && !mapPoints.length;
  return <section className="single-surface home-map-stage">
    <div className="home-map-copy"><p className="eyebrow">Fortune Farms</p><h2>{title}</h2><p>{detail}</p><div className="home-map-metrics"><span><strong>{count(locationCount)}</strong> locations</span><span><strong>{count(trackwick?.counts.farmers)}</strong> farmers</span><span><strong>{count(trackwick?.counts.field_workers)}</strong> field workers</span></div><Link href="/map" className="primary-action">Open map <span aria-hidden="true">→</span></Link></div>
    {mapIsPreparing ? <MapLoadingState label="Opening the field map" /> : <OperatingMap points={mapPoints} preview />}
  </section>;
}

function OperatingMap({ points, preview = false, selectedPoint, onSelect }: { points: MapPoint[]; preview?: boolean; selectedPoint?: MapPoint | null; onSelect?: (point: MapPoint | null) => void }) {
  const mapElement = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<import("leaflet").Map | null>(null);
  const markerLayerRef = useRef<import("leaflet").LayerGroup | null>(null);
  const leafletRef = useRef<typeof import("leaflet") | null>(null);
  const fittedDataRef = useRef<string | null>(null);
  const [active, setActive] = useState<MapPoint | null>(selectedPoint || null);
  const [mapReady, setMapReady] = useState(false);
  const [mapHealth, setMapHealth] = useState<"loading" | "ready" | "cached">("loading");
  const visible = useMemo(() => preview ? points.slice(0, 700) : points, [points, preview]);
  const hasMapPoints = visible.length > 0;
  const dataKey = `${preview}:${visible.length}:${visible[0]?.id || ""}:${visible.at(-1)?.id || ""}`;

  const select = useCallback((point: MapPoint | null) => {
    setActive(point);
    onSelect?.(point);
  }, [onSelect]);

  useEffect(() => { setActive(selectedPoint || null); }, [selectedPoint]);

  useEffect(() => {
    // The board arrives after the shell. Wait until there is a real map node
    // and cached points before booting Leaflet; otherwise an early empty pass
    // would leave the real map permanently in its fallback state.
    if (!hasMapPoints) return;
    let cancelled = false;
    setMapHealth("loading");
    void import("leaflet").then((module) => {
      // Leaflet is CommonJS. Browser bundlers differ on whether its API lives
      // on the module namespace or `default`; accept both so a deployment
      // never leaves the cached activity canvas blank.
      const L = (typeof module.map === "function" ? module : module.default) as typeof import("leaflet");
      if (cancelled || !mapElement.current || typeof L?.map !== "function") throw new Error("Map could not start");
      const map = L.map(mapElement.current, {
        zoomControl: false,
        attributionControl: true,
        preferCanvas: true,
        scrollWheelZoom: true,
        dragging: true,
        doubleClickZoom: true,
        keyboard: true,
        touchZoom: true,
      });
      L.control.zoom({ position: "bottomright" }).addTo(map);
      map.getContainer().setAttribute("aria-label", "Interactive field activity map. Drag to explore, scroll or pinch to zoom, and use arrow keys after focusing the map to pan.");
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 18,
        attribution: "© OpenStreetMap contributors",
      }).addTo(map);
      leafletRef.current = L;
      mapRef.current = map;
      markerLayerRef.current = L.layerGroup().addTo(map);
      setMapReady(true);
      setMapHealth("ready");
      const resize = () => map.invalidateSize({ pan: false });
      map.whenReady(() => { window.requestAnimationFrame(resize); window.setTimeout(resize, 120); });
    }).catch(() => {
      if (!cancelled) {
        setMapReady(false);
        setMapHealth("cached");
      }
    });
    return () => {
      cancelled = true;
      const map = mapRef.current;
      if (map) map.remove();
      if (mapRef.current === map) {
        mapRef.current = null;
        markerLayerRef.current = null;
        leafletRef.current = null;
      }
    };
  }, [hasMapPoints, preview]);

  useEffect(() => {
    const L = leafletRef.current;
    const map = mapRef.current;
    const layer = markerLayerRef.current;
    if (!L || !map || !layer) return;
    layer.clearLayers();
    if (!visible.length) return;
    const render = () => {
      layer.clearLayers();
      for (const group of mapClusters(visible, map.getZoom())) {
        if (group.points.length > 1) {
          const status = mapClusterStatus(group.points);
          const color = mapMarkerColor(status.tone);
          const marker = L.circleMarker([group.latitude, group.longitude], {
            radius: Math.min(22, 6 + Math.sqrt(group.points.length) * 1.25),
            color: color.stroke, weight: 1.5, fillColor: color.fill, fillOpacity: .96,
          }).bindTooltip(`${count(group.points.length)} field activities · ${status.label}`, { direction: "top", sticky: true });
          marker.on("click", () => map.setView([group.latitude, group.longitude], Math.min(map.getZoom() + 2, 16)));
          marker.addTo(layer);
          continue;
        }
        const point = group.points[0];
        const status = mapActivityStatus(point);
        const color = mapMarkerColor(status.tone);
        const marker = L.circleMarker([point.latitude, point.longitude], {
          radius: active?.id === point.id ? 9 : status.tone === "attention" ? 7.2 : 5.8,
          color: color.stroke, weight: active?.id === point.id ? 2.8 : 1.35, fillColor: color.fill, fillOpacity: .97,
        }).bindTooltip(mapTooltip(point), { direction: "top", sticky: true, opacity: .98 });
        marker.on("click", () => select(point));
        marker.addTo(layer);
      }
    };
    const bounds = L.latLngBounds(visible.map((point) => [point.latitude, point.longitude] as [number, number]));
    if (bounds.isValid() && fittedDataRef.current !== dataKey) {
      fittedDataRef.current = dataKey;
      map.fitBounds(bounds.pad(preview ? .18 : .1), { maxZoom: preview ? 11 : 13, animate: false });
    }
    render();
    map.on("zoomend", render);
    return () => { map.off("zoomend", render); };
  }, [active?.id, dataKey, mapReady, preview, select, visible]);

  if (!visible.length) return <div className="operating-map map-empty"><strong>Map is preparing</strong><p>Location activity will appear here as the operating record arrives.</p></div>;
  const area = mapAreaLabel(visible);
  return <div className={`operating-map ${preview ? "operating-map-preview" : ""}`} aria-label="Field activity map">
    <div className="leaflet-map" ref={mapElement} aria-hidden={mapHealth !== "ready"} />
    {mapHealth !== "ready" ? <CachedMapFallback points={visible} onSelect={select} /> : null}
    <div className="map-area-label"><strong>{area}</strong><span className="map-gesture-copy">Drag · scroll to zoom</span><span className="map-touch-copy">Drag · pinch to zoom</span></div>
    {preview && active ? <MapGlance point={active} close={() => select(null)} /> : null}
  </div>;
}

function mapAreaLabel(points: MapPoint[]) {
  const frequency = new Map<string, number>();
  for (const point of points) {
    const place = point.subject.place?.split("·").at(-1)?.trim();
    if (place) frequency.set(place, (frequency.get(place) || 0) + 1);
  }
  return [...frequency.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || "Field area";
}

function CachedMapFallback({ points, onSelect }: { points: MapPoint[]; onSelect: (point: MapPoint) => void }) {
  const groups = useMemo(() => mapClusters(points.slice(0, 900), 9), [points]);
  const extent = useMemo(() => {
    const latitudes = points.map((point) => point.latitude);
    const longitudes = points.map((point) => point.longitude);
    const minLat = Math.min(...latitudes); const maxLat = Math.max(...latitudes);
    const minLng = Math.min(...longitudes); const maxLng = Math.max(...longitudes);
    return { minLat, maxLat, minLng, maxLng, latSpan: Math.max(.01, maxLat - minLat), lngSpan: Math.max(.01, maxLng - minLng) };
  }, [points]);
  return <div className="cached-map-fallback" aria-label="Cached field activity">
    <svg viewBox="0 0 1000 650" role="img" aria-label={`${count(points.length)} cached field activities`}>
      <path d="M80 510C230 420 295 530 430 385S690 245 910 120" className="cached-map-route" />
      <path d="M110 150C320 270 460 130 620 255S795 455 920 535" className="cached-map-route muted" />
      {groups.map((group, index) => {
        const x = 60 + ((group.longitude - extent.minLng) / extent.lngSpan) * 880;
        const y = 590 - ((group.latitude - extent.minLat) / extent.latSpan) * 530;
        const first = group.points[0];
        const radius = Math.min(18, 5 + Math.log2(group.points.length + 1) * 3);
        const status = mapClusterStatus(group.points);
        return <g key={`${group.latitude}:${group.longitude}:${index}`} className={`cached-map-point ${status.tone}`} role="button" tabIndex={0} aria-label={`${first.subject.name}, ${count(group.points.length)} activities, ${status.label}`} onClick={() => onSelect(first)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(first); } }}>
          <title>{`${first.subject.name} · ${count(group.points.length)} activities`}</title><circle cx={x} cy={y} r={radius} /><circle cx={x} cy={y} r="2.4" className="cached-map-point-core" />
        </g>;
      })}
    </svg>
  </div>;
}

function MapView({ state }: { state: State }) {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<"all" | MapSubjectKind>("all");
  const [days, setDays] = useState<"all" | "7" | "30">("all");
  const [selected, setSelected] = useState<MapPoint | null>(null);
  const allPoints = state.trackwick?.map?.points || [];
  const mapIsPreparing = state.loading && !allPoints.length;
  const points = useMemo(() => {
    const minimum = days === "all" ? null : Date.now() - Number(days) * 86_400_000;
    const needle = query.trim().toLocaleLowerCase();
    return allPoints.filter((point) => {
      if (kind !== "all" && point.subject.kind !== kind) return false;
      if (minimum && new Date(point.observed_at).valueOf() < minimum) return false;
      if (!needle) return true;
      return [point.subject.name, point.subject.place, point.subject.farmer_name, point.label].filter(Boolean).some((value) => value!.toLocaleLowerCase().includes(needle));
    });
  }, [allPoints, days, kind, query]);
  useEffect(() => {
    setSelected((current) => {
      if (current && points.some((point) => point.id === current.id)) return current;
      return points.find((point) => point.subject.kind === "field_worker") || points[0] || null;
    });
  }, [points]);
  return <section className={`map-workspace ${selected ? "map-workspace-selected" : ""}`}>
    <div className="map-controls" aria-label="Map filters">
      <label>Find<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Farmer, farm, village" /></label>
      <MapTabs label="View" value={kind} onChange={setKind} options={[["all", "Everything"], ["reported_farm", "Farms"], ["farmer", "Farmers"], ["field_worker", "Workers"]]} />
      <MapTabs label="When" value={days} onChange={setDays} options={[["all", "All time"], ["7", "This week"], ["30", "This month"]]} />
    </div>
    <div className="map-content"><div className="map-canvas">{mapIsPreparing ? <MapLoadingState label="Opening map" /> : <OperatingMap points={points} selectedPoint={selected} onSelect={setSelected} />}</div></div>
    {selected ? <MapInspector point={selected} state={state} close={() => setSelected(null)} /> : null}
  </section>;
}

function MapTabs<T extends string>({ label, value, onChange, options }: { label: string; value: T; onChange: (value: T) => void; options: ReadonlyArray<readonly [T, string]> }) {
  return <div className="map-type-tabs" aria-label={label}><span>{label}</span><div>{options.map(([option, title]) => <button type="button" key={option} className={value === option ? "active" : ""} aria-pressed={value === option} onClick={() => onChange(option)}>{title}</button>)}</div></div>;
}

function MapInspector({ point, state, close }: { point: MapPoint; state: State; close: () => void }) {
  const subject = point.subject;
  const status = mapActivityStatus(point);
  const metrics = subject.operating?.metrics;
  const matchingActivity = (state.trackwick?.map?.points || []).filter((candidate) => candidate.subject.kind === subject.kind && candidate.subject.id === subject.id).sort((a, b) => new Date(b.observed_at).valueOf() - new Date(a.observed_at).valueOf());
  const farm = subject.kind === "reported_farm" ? state.trackwick?.farms.find((candidate) => candidate.id === subject.id) : null;
  const farmer = subject.kind === "farmer" ? state.trackwick?.farmers.find((candidate) => candidate.id === subject.id) : null;
  const worker = subject.kind === "field_worker" ? state.trackwick?.field_workers.find((candidate) => candidate.id === subject.id) : null;
  const facts = subject.kind === "reported_farm"
    ? [["Farmer", farm?.farmer_name || subject.farmer_name || "—"], ["Plots", count(farm?.reported_plot_count ?? undefined)], ["Open Tasks", count(metrics?.open_task_count ?? farm?.open_work ?? subject.open_work)], ["Field Activity", count(metrics?.location_evidence_count ?? matchingActivity.length)]]
    : subject.kind === "farmer"
      ? [["Farms", count(metrics?.farm_count ?? farmer?.farm_candidates)], ["Open Tasks", count(metrics?.open_task_count ?? farmer?.open_work ?? subject.open_work)], ["Photo Evidence", count(metrics?.photo_reference_count ?? farmer?.crop_photo_references)], ["Field Activity", count(metrics?.location_evidence_count ?? matchingActivity.length)]]
      : subject.kind === "field_worker"
        ? [["Farmers Assigned", count(metrics?.farmer_count ?? worker?.reported_farmer_reach)], ["Open Tasks", count(metrics?.open_task_count ?? worker?.open_work ?? subject.open_work)], ["Completed Work", count(metrics?.completed_work_count ?? worker?.completed_work)], ["Field Activity", count(metrics?.location_evidence_count ?? matchingActivity.length)]]
        : [["Place", subject.place || "—"], ["Open Tasks", count(subject.open_work)], ["Field Activity", count(matchingActivity.length)], ["Last Activity", dateTime(point.observed_at)]];
  return <aside className="map-inspector" aria-label="Selected map record">
    <div className="map-inspector-record">
      <button type="button" className="map-glance-close" onClick={close} aria-label="Close selected record">×</button>
      <p className="eyebrow">{subject.kind === "reported_farm" ? "Farm" : subject.kind.replaceAll("_", " ")}</p>
      <h2>{subject.name}</h2>
      <p className="map-inspector-place">{[subject.place, subject.farmer_name].filter(Boolean).join(" · ") || "Field activity location"}<span>{updatedAgo(point.observed_at)}</span></p>
      <div className="map-record-tags"><span>{subject.kind === "reported_farm" ? "Farm" : subject.kind.replaceAll("_", " ")}</span><span className={status.tone}>{status.label}</span><OperatingTagChips snapshot={subject.operating} limit={2} /></div>
      <dl>{facts.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      <section className="map-inspector-history"><p className="eyebrow">Recent activity</p>{matchingActivity.slice(0, 4).map((activity) => <div key={activity.id}><strong>{activity.subject.place || activity.subject.farmer_name || "Field activity"}</strong><span>{dateTime(activity.observed_at)}</span></div>)}</section>
      {mapProfileHref(subject) ? <Link href={mapProfileHref(subject)!} className="primary-action">Open full profile <span aria-hidden="true">→</span></Link> : null}
    </div>
  </aside>;
}

function mapTooltip(point: MapPoint) {
  const label = escapeMapText(point.subject.name || point.label);
  const detail = point.subject.place || point.subject.farmer_name || dateTime(point.observed_at);
  return `<strong>${label}</strong><br><span>${escapeMapText(detail)} · ${mapActivityStatus(point).label}</span>`;
}

type MapActivityTone = "attention" | "current" | "earlier";

function mapActivityStatus(point: MapPoint): { tone: MapActivityTone; label: string } {
  const metrics = point.subject.operating?.metrics;
  const openTasks = metrics?.open_task_count ?? point.subject.open_work;
  if (openTasks > 0) return { tone: "attention", label: openTasks === 1 ? "1 open task" : `${openTasks} open tasks` };
  if (metrics?.disease_report_count) return { tone: "attention", label: "Disease reported" };
  if (metrics?.pest_report_count) return { tone: "attention", label: "Pest reported" };
  const activityAt = metrics?.latest_activity_at || point.observed_at;
  const age = Date.now() - new Date(activityAt).valueOf();
  if (age <= 7 * 86_400_000) return { tone: "current", label: "Updated this week" };
  if (age <= 30 * 86_400_000) return { tone: "current", label: "Updated this month" };
  return { tone: "earlier", label: "Earlier activity" };
}

function mapClusterStatus(points: MapPoint[]) {
  const statuses = points.map(mapActivityStatus);
  const attention = statuses.filter((status) => status.tone === "attention").length;
  const current = statuses.filter((status) => status.tone === "current").length;
  if (attention) return { tone: "attention" as const, label: `${count(attention)} need attention` };
  if (current) return { tone: "current" as const, label: `${count(current)} updated recently` };
  return { tone: "earlier" as const, label: "Earlier activity" };
}

function mapMarkerColor(tone: MapActivityTone) {
  return ({ attention: { stroke: "#a6574b", fill: "#f4d8d2" }, current: { stroke: "#497054", fill: "#dcebcf" }, earlier: { stroke: "#879783", fill: "#f3f5ed" } })[tone];
}

function escapeMapText(value: string) {
  return value.replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[character] || character);
}

function mapClusters(points: MapPoint[], zoom: number) {
  const precision = Math.max(.0012, .24 / 2 ** Math.max(0, zoom - 7));
  const groups = new Map<string, { latitude: number; longitude: number; points: MapPoint[] }>();
  for (const point of points) {
    const key = `${Math.round(point.latitude / precision)}:${Math.round(point.longitude / precision)}`;
    const group = groups.get(key) || { latitude: 0, longitude: 0, points: [] };
    group.latitude += point.latitude;
    group.longitude += point.longitude;
    group.points.push(point);
    groups.set(key, group);
  }
  return [...groups.values()].map((group) => ({ ...group, latitude: group.latitude / group.points.length, longitude: group.longitude / group.points.length }));
}

function MapGlance({ point, close }: { point: MapPoint; close: () => void }) {
  const subject = point.subject;
  const status = mapActivityStatus(point);
  return <aside className="map-glance" aria-live="polite">
    <button type="button" className="map-glance-close" onClick={close} aria-label="Close map card">×</button>
    <p className="eyebrow">{subject.kind === "reported_farm" ? "Farm" : subject.kind.replaceAll("_", " ")}</p>
    <strong>{subject.name}</strong>
    <p>{[subject.place, subject.farmer_name, status.label, `Updated ${dateTime(point.observed_at)}`].filter(Boolean).join(" · ")}</p>
    {mapProfileHref(subject) ? <Link href={mapProfileHref(subject)!} className="text-link">Open profile <span aria-hidden="true">→</span></Link> : null}
  </aside>;
}

function mapProfileHref(subject: MapPoint["subject"]) {
  if (!subject.id) return null;
  if (subject.kind === "reported_farm") return `/farms?reported_farm=${encodeURIComponent(subject.id)}`;
  if (subject.kind === "farmer") return `/farmers?person=${encodeURIComponent(subject.id)}`;
  if (subject.kind === "field_worker") return `/farmers?worker=${encodeURIComponent(subject.id)}`;
  return null;
}

const EMPTY_DIRECTORY_FILTERS: DirectoryFilters = {
  state: ["all"],
  activity: ["all"],
  order: "open_tasks",
  query: "",
  dateFrom: "",
  dateTo: "",
};
const MANAGER_ACCESS_BOUNDARY_ID = "farm-manager-access-boundary";
const FARM_DIRECTORY_PAGE_SIZE = 100;

function filtersFromLocation() {
  const params = new URLSearchParams(window.location.search);
  const state = parseFilterValues<FarmStateFilter>(params.get("state"), ["all", "reviewed", "reported"]);
  const activity = parseFilterValues<FarmActivityFilter>(params.get("activity"), ["all", "open_tasks", "updated_week", "updated_month", "no_recent_update"]);
  const order = params.get("order");
  return {
    state,
    activity,
    order: order === "recently_updated" || order === "least_updated" || order === "name" || order === "open_tasks" ? order : "open_tasks",
    query: params.get("query") || "",
    dateFrom: params.get("date_from") || "",
    dateTo: params.get("date_to") || "",
  } satisfies DirectoryFilters;
}

function parseFilterValues<T extends string>(value: string | null, allowed: readonly T[]): T[] {
  const values = (value || "all").split(",").filter((entry): entry is T => (allowed as readonly string[]).includes(entry));
  if (!values.length || values.includes("all" as T)) return ["all" as T];
  return [...new Set(values)];
}

function directoryParams(filters: DirectoryFilters) {
  const params = new URLSearchParams();
  params.set("kind", "farm");
  params.set("state", filters.state.join(","));
  params.set("activity", filters.activity.join(","));
  params.set("order", filters.order);
  if (filters.query.trim()) params.set("query", filters.query.trim());
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  return params;
}

function FieldsView({ t, state, canOpenProfiles, accessResolved, expireManagerSession }: {
  t: Translation;
  state: State;
  canOpenProfiles: boolean;
  accessResolved: boolean;
  expireManagerSession: () => void;
}) {
  const [filters, setFilters] = useState<DirectoryFilters>(EMPTY_DIRECTORY_FILTERS);
  const [draftFilters, setDraftFilters] = useState<DirectoryFilters>(EMPTY_DIRECTORY_FILTERS);
  const [filtersReady, setFiltersReady] = useState(false);
  const [directoryPage, setDirectoryPage] = useState(0);
  const [directory, setDirectory] = useState<{ items: FarmDirectory; loading: boolean; error: string | null; stale: boolean }>({
    items: [], loading: false, error: null, stale: false,
  });
  const [panel, setPanel] = useState<ContextPanel | null>(null);
  const directoryRequest = useRef(0);
  const panelRequest = useRef(0);
  const directoryOpener = useRef<string | null>(null);
  const managerAccessWasEnabled = useRef(canOpenProfiles);
  const pendingManagerExpiryFocus = useRef(false);
  const initialFarmRequest = useRef<string | null>(null);
  const initialReportedFarmRequest = useRef<string | null>(null);

  useEffect(() => {
    function syncFromUrl() {
      const next = filtersFromLocation();
      initialFarmRequest.current = new URLSearchParams(window.location.search).get("farm");
      initialReportedFarmRequest.current = new URLSearchParams(window.location.search).get("reported_farm");
      setFilters(next);
      setDraftFilters(next);
      setFiltersReady(true);
    }
    syncFromUrl();
    window.addEventListener("popstate", syncFromUrl);
    return () => window.removeEventListener("popstate", syncFromUrl);
  }, []);

  useEffect(() => {
    if (!filtersReady || draftFilters.query.trim() === filters.query) return;
    const timeout = window.setTimeout(() => {
      const next = { ...filters, query: draftFilters.query.trim() };
      const params = directoryParams(next);
      params.delete("kind");
      window.history.replaceState({}, "", `/farms?${params.toString()}`);
      setDirectoryPage(0);
      setFilters(next);
    }, 220);
    return () => window.clearTimeout(timeout);
  }, [draftFilters.query, filters, filtersReady]);

  useEffect(() => {
    if (!filtersReady || !accessResolved || !canOpenProfiles) {
      if (filtersReady && accessResolved) setDirectory({ items: [], loading: false, error: null, stale: false });
      return;
    }
    const request = ++directoryRequest.current;
    const params = directoryParams(filters);
    params.set("limit", String(FARM_DIRECTORY_PAGE_SIZE));
    params.set("offset", String(directoryPage * FARM_DIRECTORY_PAGE_SIZE));
    const cacheKey = DIRECTORY_CACHE_PREFIX + params.toString();
    let cached: FarmDirectory | null = null;
    try {
      const saved = window.sessionStorage.getItem(cacheKey);
      cached = saved ? JSON.parse(saved) as FarmDirectory : null;
    } catch { /* a bad local cache is discarded by the next successful read */ }
    setDirectory((current) => ({ items: cached || current.items, loading: true, error: null, stale: Boolean(current.items.length) }));
    void readJson<FarmDirectory>("/api/v1/farms?" + params)
      .then(({ value }) => {
        if (request === directoryRequest.current) {
          setDirectory((current) => {
            const items = directoryPage ? [...current.items, ...value] : value;
            try { window.sessionStorage.setItem(cacheKey, JSON.stringify(items)); } catch { /* cache is optional */ }
            return { items, loading: false, error: null, stale: false };
          });
        }
      })
      .catch((error: unknown) => {
        if (request !== directoryRequest.current) return;
        const message = profileReadError(error);
        if (message === "Manager access expired.") expireManagerSession();
        setDirectory((current) => ({ items: current.items, loading: false, error: current.items.length ? null : message, stale: Boolean(current.items.length) }));
      });
  }, [accessResolved, canOpenProfiles, directoryPage, expireManagerSession, filters, filtersReady]);

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

  function updateDirectoryFilters(patch: Partial<Pick<DirectoryFilters, "state" | "activity" | "order">>) {
    const next = { ...filters, ...patch };
    const params = directoryParams(next);
    params.delete("kind");
    const query = params.toString();
    window.history.pushState({}, "", query ? `/farms?${query}` : "/farms");
    setDraftFilters((current) => ({ ...current, ...patch }));
    setDirectoryPage(0);
    setFilters(next);
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
    const cacheKey = `${PROFILE_CACHE_PREFIX}reviewed:farm:${id}`;
    const cached = readSessionCache<FarmRecord>(cacheKey);
    setPanel({ kind: "farm", loading: !cached, error: null, record: cached, history });
    try {
      const { value } = await readJson<FarmRecord>("/api/v1/farms/" + id);
      if (request === panelRequest.current) { writeSessionCache(cacheKey, value); setPanel({ kind: "farm", loading: false, error: null, record: value, history }); }
    } catch (error) {
      if (cached) return;
      finishPanelError(request, "farm", history, error);
    }
  }

  async function openReportedFarm(id: string, openerId: string) {
    if (!canOpenProfiles) return;
    directoryOpener.current = openerId;
    const request = ++panelRequest.current;
    const cacheKey = `${PROFILE_CACHE_PREFIX}reported:farm:${id}`;
    const cached = readSessionCache<ReportedFarmProfile>(cacheKey);
    setPanel({ kind: "farm", loading: !cached, error: null, record: cached, history: [] });
    try {
      const { value } = await readJson<ReportedFarmProfile>("/api/v1/reported-farm-profiles/" + id);
      if (request === panelRequest.current) { writeSessionCache(cacheKey, value); setPanel({ kind: "farm", loading: false, error: null, record: value, history: [] }); }
    } catch (error) {
      if (cached) return;
      finishPanelError(request, "farm", [], error);
    }
  }

  useEffect(() => {
    const farmId = initialFarmRequest.current;
    if (!filtersReady || !canOpenProfiles || !farmId) return;
    initialFarmRequest.current = null;
    void openFarm(farmId, MANAGER_ACCESS_BOUNDARY_ID);
  }, [canOpenProfiles, filtersReady]);

  useEffect(() => {
    const farmId = initialReportedFarmRequest.current;
    if (!filtersReady || !canOpenProfiles || !farmId) return;
    initialReportedFarmRequest.current = null;
    void openReportedFarm(farmId, MANAGER_ACCESS_BOUNDARY_ID);
  }, [canOpenProfiles, filtersReady]);

  async function openField(id: string, openerId: string) {
    if (!canOpenProfiles) return;
    const history = panelHistory(openerId, true);
    const request = ++panelRequest.current;
    const cacheKey = `${PROFILE_CACHE_PREFIX}reviewed:field:${id}`;
    const cached = readSessionCache<FieldRecord>(cacheKey);
    setPanel({ kind: "field", loading: !cached, error: null, record: cached, history });
    try {
      const { value } = await readJson<FieldRecord>("/api/v1/fields/" + id);
      if (request === panelRequest.current) { writeSessionCache(cacheKey, value); setPanel({ kind: "field", loading: false, error: null, record: value, history }); }
    } catch (error) {
      if (cached) return;
      finishPanelError(request, "field", history, error);
    }
  }

  async function openPerson(kind: PersonKind, id: string, openerId: string) {
    if (!canOpenProfiles) return;
    const history = panelHistory(openerId, true);
    const request = ++panelRequest.current;
    const cacheKey = `${PROFILE_CACHE_PREFIX}reviewed:${kind}:${id}`;
    const cached = readSessionCache<PersonContext>(cacheKey);
    setPanel({ kind, loading: !cached, error: null, record: cached, history });
    try {
      const { value } = await readJson<PersonContext>("/api/v1/people/" + kind + "/" + id);
      if (request === panelRequest.current) { writeSessionCache(cacheKey, value); setPanel({ kind, loading: false, error: null, record: value, history }); }
    } catch (error) {
      if (cached) return;
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
      operatingUnit={state.runtime?.operating_unit}
      openFarm={(id, openerId) => void openFarm(id, openerId, true)}
      openField={(id, openerId) => void openField(id, openerId)}
      openPerson={(kind, id, openerId) => void openPerson(kind, id, openerId)}
    />;
  }

  const reportedTotal = filters.state.includes("all") || filters.state.includes("reported") ? state.trackwick?.counts.farm_candidates : undefined;
  const canLoadMore = Boolean(reportedTotal && directory.items.length < reportedTotal);
  return <section className="directory-workspace farm-directory">
    <div className="directory-toolbar directory-toolbar-controls"><div className="directory-title"><h1>Farms</h1><span>{reportedTotal ? `${count(directory.items.length)} of ${count(reportedTotal)}` : count(directory.items.length)}</span></div><MultiFilter label="Status" values={filters.state} options={[["all", "All farms"], ["reported", "To review"], ["reviewed", "Active"]]} onChange={(state) => updateDirectoryFilters({ state })} /><MultiFilter label="Activity" values={filters.activity} options={[["all", "All activity"], ["open_tasks", "Open tasks"], ["updated_week", "Updated this week"], ["updated_month", "Updated this month"], ["no_recent_update", "No recent update"]]} onChange={(activity) => updateDirectoryFilters({ activity })} /><SortMenu value={filters.order} onChange={(order) => updateDirectoryFilters({ order })} options={[["open_tasks", "Open tasks"], ["recently_updated", "Recently updated"], ["least_updated", "Least updated"], ["name", "Name"]]} /><label className="directory-find"><span className="sr-only">Find farms</span><input type="search" maxLength={80} value={draftFilters.query} onChange={(event) => setDraftFilters((current) => ({ ...current, query: event.target.value }))} placeholder="Find farm, farmer, or village" /></label></div>
    {!accessResolved
      ? <DirectoryLoadingState label="Opening farms" />
      : !canOpenProfiles
      ? <EmptyState focusId={MANAGER_ACCESS_BOUNDARY_ID} title="Sign in to open farms" detail="Farm records are available to named Fortune admins." action={{ href: "/login?next=/farms", label: "Sign in" }} />
      : directory.loading && !directory.items.length
        ? <DirectoryLoadingState label="Updating farms" />
        : directory.items.length
          ? <><div className="farm-card-grid">{directory.items.map((farm) => farm.state === "reported"
            ? <button id={`reported-farm-directory-${farm.id}`} type="button" className="farm-directory-card directory-card-button compact-entity-card reported-candidate-card" key={farm.id} onClick={(event) => void openReportedFarm(farm.destination.id, event.currentTarget.id)}><span className="person-initial farm-initial">{farm.name.slice(0, 1).toUpperCase()}</span><div className="farm-card-summary"><p className="entity-card-type">Farm to review</p><h3>{farm.name}</h3><p className="farm-card-context">{farm.reported_farmer_name}</p><div className="entity-card-metrics"><span><strong>{count(farm.reported_plot_count || undefined)}</strong> Plots</span><span className={farm.open_work_count ? "attention" : undefined}><strong>{count(farm.open_work_count)}</strong> Open Tasks</span></div><OperatingTags snapshot={farm.operating} limit={2} /><p className="entity-card-updated">{updatedAgo(farm.latest_update_at)}</p></div></button>
            : <button id={`farm-directory-${farm.id}`} type="button" className="farm-directory-card directory-card-button compact-entity-card" key={farm.id} onClick={(event) => void openFarm(farm.id, event.currentTarget.id)}><span className="person-initial farm-initial">{farm.name.slice(0, 1).toUpperCase()}</span><div className="farm-card-summary"><p className="entity-card-type">Farm</p><h3>{farm.name}</h3><p className="farm-card-context">{farm.crops.join(" · ") || "No active crop recorded"}</p><div className="entity-card-metrics"><span><strong>{count(farm.field_count)}</strong> Fields</span><span className={farm.open_work_count ? "attention" : undefined}><strong>{count(farm.open_work_count)}</strong> Open Tasks</span></div><p className="entity-card-updated">{updatedAgo(farm.latest_update_at)}</p></div></button>)}</div>{canLoadMore ? <button className="quiet-button directory-more" type="button" onClick={() => setDirectoryPage((current) => current + 1)} disabled={directory.loading}>Show {count(Math.min(FARM_DIRECTORY_PAGE_SIZE, reportedTotal! - directory.items.length))} more ({count(reportedTotal! - directory.items.length)} remaining)</button> : null}</>
        : directory.error
          ? <p className="profile-message profile-error" role="alert">{directory.error} <a href="/manager">Re-authenticate in Farm Truth</a></p>
          : <EmptyState title="No farms match these filters." detail="Try another view or search." />}
  </section>;
}

function ContextProfilePanel({ panel, close, operatingUnit, openFarm, openField, openPerson }: {
  panel: ContextPanel;
  close: () => void;
  operatingUnit?: { id: string; name: string };
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
          ? <ReportedFarmPanel record={panel.record} operatingUnit={operatingUnit} />
          : panel.record?.kind === "farm"
          ? <FarmRecordPanel record={panel.record} openField={openField} openPerson={openPerson} />
          : panel.record?.kind === "field"
            ? <FieldRecordPanel record={panel.record} openFarm={openFarm} openPerson={openPerson} />
            : panel.record
              ? <PersonContextPanel record={panel.record} openFarm={openFarm} openField={openField} />
              : null}
  </aside>;
}

function ReportedFarmPanel({ record, operatingUnit }: {
  record: ReportedFarmProfile;
  operatingUnit?: { id: string; name: string };
}) {
  const photoReferences = record.reported.plot_photo_references + record.reported.crop_photo_references;
  const [candidate, setCandidate] = useState<FarmCandidateCase | null>(null);
  const [farmName, setFarmName] = useState(record.name);
  const [reviewState, setReviewState] = useState<"loading" | "ready" | "saving" | "done" | "error">("loading");
  const [reviewMessage, setReviewMessage] = useState("");
  useEffect(() => {
    let active = true;
    void readJson<FarmCandidateCase>(`/api/v1/farm-candidates/registrations/${record.id}/case`, { method: "POST" })
      .then(({ value }) => { if (active) { setCandidate(value); setFarmName(value.farm_name_suggestion || record.name); setReviewState("ready"); } })
      .catch(() => { if (active) { setReviewState("error"); setReviewMessage("This registration is not eligible for Farm review right now."); } });
    return () => { active = false; };
  }, [record.id, record.name]);
  async function acceptCandidate() {
    if (!candidate || !operatingUnit || !farmName.trim()) return;
    if (!window.confirm(`Create “${farmName.trim()}” and link ${candidate.farmer_name} as its reviewed Grower? No Field, boundary, crop, or land right will be created.`)) return;
    setReviewState("saving");
    try {
      const { value } = await readJson<{ status: string; farm_id?: string }>(`/api/v1/farm-candidates/cases/${candidate.id}/accept`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ operating_unit_id: operatingUnit.id, farm_name: farmName.trim(), grower_effective_on: new Date().toISOString().slice(0, 10), expected_updated_at: candidate.updated_at }),
      });
      setReviewState("done");
      setReviewMessage(value.status === "accepted" ? "Farm created." : "Saved.");
    } catch {
      setReviewState("error");
      setReviewMessage("The review could not be saved. Refresh this profile and try again.");
    }
  }
  return <div className="entity-profile-content reported-farm-context">
    <p className="eyebrow">Farm</p>
    <h2>{record.name}</h2>
    <p className="profile-context">Review the farm. Build the record as work happens.</p>
    <OperatingTags snapshot={record.reported.operating} limit={6} className="profile-operating-tags" />
    <div className="farm-profile-sections">
      <section>
        <h3>Farm details</h3>
        <dl className="profile-facts">
          <div><dt>Farmer</dt><dd>{record.reported.farmer_name}</dd></div>
          <div><dt>Location</dt><dd>{record.reported.place}</dd></div>
          <div><dt>Area</dt><dd>{record.reported.reported_area_acres == null ? "—" : `${record.reported.reported_area_acres} acres`}</dd></div>
          <div><dt>Plots</dt><dd>{count(record.reported.reported_plot_count || undefined)}</dd></div>
        </dl>
      </section>
      <section>
        <h3>Activity</h3>
        <dl className="profile-facts">
          <div><dt>Open tasks</dt><dd>{count(record.reported.open_work)}</dd></div>
          <div><dt>Last activity</dt><dd>{updatedAgo(record.reported.latest_activity_at)}</dd></div>
          <div><dt>Photos</dt><dd>{count(photoReferences)}</dd></div>
        </dl>
      </section>
      <section>
        <h3>Make it a Farm</h3>
        <p className="profile-context">Create the Farm and connect its farmer.</p>
        {reviewState === "loading" ? <p className="empty-copy" role="status">Getting it ready…</p> : null}
        {reviewState === "ready" && candidate ? <div className="candidate-review-form"><label>Farm name<input value={farmName} maxLength={160} onChange={(event) => setFarmName(event.target.value)} /></label><p>{candidate.farmer_name} · {operatingUnit?.name || "Fortune Farms"}</p><button className="primary-action" type="button" onClick={() => void acceptCandidate()} disabled={!operatingUnit || !farmName.trim()}>Create Farm <span aria-hidden="true">→</span></button></div> : null}
        {reviewState === "saving" ? <p className="empty-copy" role="status">Creating Farm…</p> : null}
        {reviewState === "done" || reviewState === "error" ? <p className={reviewState === "error" ? "profile-message profile-error" : "profile-message"}>{reviewMessage}</p> : null}
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
        <div className="profile-summary-line"><span>{count(record.now.open_work_count)} open work</span><span>{updatedAgo(record.now.latest_update_at)}</span></div>
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
  const latestUpdateAt = record.updates.reduce<string | null>((latest, update) => {
    if (!latest || activityTimestamp(update.occurred_at) > activityTimestamp(latest)) return update.occurred_at;
    return latest;
  }, null);
  return <div className="entity-profile-content field-context">
    <p className="eyebrow">Reviewed Field</p>
    <h2>{record.name}</h2>
    <div className="profile-summary-line"><span>{record.area_hectares == null ? "Area not recorded" : `${record.area_hectares} hectares`}</span><span>Geometry {roleName(record.geometry.state)}</span><span>{updatedAgo(latestUpdateAt)}</span></div>
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
        <p className="context-limitation">A Field boundary is added only when it is confirmed.</p>
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
      <ul className="assignment-list">{record.assignments.map((assignment, index) => <li key={`${assignment.farm_id}-${assignment.field_id || "no-field"}-${assignment.role}`}><div><strong>{roleName(assignment.role)}</strong><span>Since {assignment.starts_on}</span></div><div className="assignment-links"><button id={`person-farm-${record.id}-${index}`} className="entity-chip entity-chip-link" type="button" onClick={(event) => openFarm(assignment.farm_id, event.currentTarget.id)}>{assignment.farm_name}</button>{assignment.field_id ? <button id={`person-field-${record.id}-${index}`} className="entity-chip entity-chip-link" type="button" onClick={(event) => openField(assignment.field_id!, event.currentTarget.id)}>{assignment.field_name}</button> : <span className="entity-chip">{assignment.field_name}</span>}</div></li>)}</ul>
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

function FarmersView({ farmers, readiness, trackwick, canOpenProfiles, accessResolved, selection, openProfile, closeProfile }: {
  farmers: ReviewedFarmerCard[];
  readiness: PilotReadiness | null;
  trackwick: TrackwickBoard | null;
  canOpenProfiles: boolean;
  accessResolved: boolean;
  selection: ProfileSelection | null;
  openProfile: (id: string, kind: PersonKind, recordState: "reviewed" | "reported", openerId: string) => Promise<void>;
  closeProfile: () => void;
}) {
  const sourceFarmers = trackwick?.farmers || [];
  const mapProfileRequested = useRef(false);
  useEffect(() => {
    if (!canOpenProfiles || mapProfileRequested.current) return;
    const params = new URLSearchParams(window.location.search);
    const farmerId = params.get("person");
    const workerId = params.get("worker");
    if (!farmerId && !workerId) return;
    mapProfileRequested.current = true;
    void openProfile(farmerId || workerId!, farmerId ? "farmer" : "field_worker", "reported", "map-profile-link");
  }, [canOpenProfiles, openProfile]);
  if (selection) return <ProfileReading selection={selection} close={closeProfile} />;
  return <section className="directory-workspace people-workspace">
    <div className="directory-toolbar people-toolbar"><div className="directory-title"><h1>Farmers</h1><span>{count(farmers.length || sourceFarmers.length)}</span></div></div>
    {!accessResolved ? <DirectoryLoadingState label="Opening farmers" /> : farmers.length ? <div className="people-list source-card-grid">{farmers.map((person) => <button id={`profile-reviewed-farmer-${person.id}`} type="button" className="person-row compact-entity-card" key={person.id} onClick={(event) => void openProfile(person.id, "farmer", "reviewed", event.currentTarget.id)}><span className="person-initial">{person.name.slice(0, 1).toUpperCase()}</span><div className="person-summary"><p className="entity-card-type">Farmer</p><h3>{person.name}</h3><div className="entity-card-metrics"><span><strong>{count(person.assignment_count)}</strong> Farms</span></div></div></button>)}</div> : sourceFarmers.length ? <ReportedFarmers farmers={sourceFarmers} canOpenProfiles={canOpenProfiles} openProfile={openProfile} /> : <p className="empty-copy">No farmers yet.</p>}
  </section>;
}

function ReportedFarmers({ farmers, canOpenProfiles, openProfile }: {
  farmers: TrackwickFarmer[];
  canOpenProfiles: boolean;
  openProfile: (id: string, kind: "farmer", recordState: "reported", openerId: string) => Promise<void>;
}) {
  const [visibleCount, setVisibleCount] = useState(100);
  const [query, setQuery] = useState("");
  const [work, setWork] = useState<Array<"all" | "open_tasks" | "no_open_tasks">>(["all"]);
  const [activity, setActivity] = useState<FarmActivityFilter[]>(["all"]);
  const [order, setOrder] = useState<"open_tasks" | "recently_updated" | "least_updated" | "name">("open_tasks");
  const matched = farmers.filter((person) => `${person.name} ${personName(person.name)}`.toLowerCase().includes(query.trim().toLowerCase())
    && (work.includes("all") || work.includes("open_tasks") && person.open_work > 0 || work.includes("no_open_tasks") && person.open_work === 0)
    && matchesActivityFilters(person.latest_activity_at, person.open_work, activity));
  const ordered = [...matched].sort((left, right) => order === "name"
    ? personName(left.name).localeCompare(personName(right.name))
    : order === "recently_updated"
      ? activityTimestamp(right.latest_activity_at) - activityTimestamp(left.latest_activity_at) || personName(left.name).localeCompare(personName(right.name))
      : order === "least_updated"
        ? activityTimestamp(left.latest_activity_at) - activityTimestamp(right.latest_activity_at) || personName(left.name).localeCompare(personName(right.name))
        : right.open_work - left.open_work || activityTimestamp(right.latest_activity_at) - activityTimestamp(left.latest_activity_at) || personName(left.name).localeCompare(personName(right.name)));
  const visible = ordered.slice(0, visibleCount);
  return <><div className="directory-secondary-toolbar directory-secondary-toolbar-filters"><MultiFilter label="Work" values={work} options={[["all", "All farmers"], ["open_tasks", "Open tasks"], ["no_open_tasks", "No open tasks"]]} onChange={(next) => { setWork(next); setVisibleCount(100); }} /><MultiFilter label="Activity" values={activity} options={[["all", "All activity"], ["updated_week", "Updated this week"], ["updated_month", "Updated this month"], ["no_recent_update", "No recent update"]]} onChange={(next) => { setActivity(next); setVisibleCount(100); }} /><SortMenu value={order} options={[["open_tasks", "Open tasks"], ["recently_updated", "Recently updated"], ["least_updated", "Least updated"], ["name", "Name"]]} onChange={(next) => { setOrder(next); setVisibleCount(100); }} /><label className="directory-find"><span className="sr-only">Find farmers</span><input type="search" value={query} onChange={(event) => { setQuery(event.target.value); setVisibleCount(100); }} placeholder="Find farmer" /></label></div><div className="people-list source-card-grid">{visible.map((person) => <button id={`profile-reported-farmer-${person.id}`} type="button" className="person-row compact-entity-card" key={person.id} onClick={(event) => void openProfile(person.id, "farmer", "reported", event.currentTarget.id)}><span className="person-initial">{personName(person.name).slice(0, 1).toUpperCase()}</span><div className="person-summary"><p className="person-code">{personCode(person.name)}</p><p className="entity-card-type">Farmer</p><h3>{personName(person.name)}</h3><div className="entity-card-metrics"><span><strong>{count(person.farm_candidates)}</strong> Farms</span><span className={person.open_work ? "attention" : undefined}><strong>{count(person.open_work)}</strong> Open Tasks</span></div><OperatingTags snapshot={person.operating} limit={2} /><p className="entity-card-updated">{updatedAgo(person.latest_activity_at)}</p></div></button>)}</div>{visible.length < ordered.length ? <button type="button" className="quiet-button directory-more" onClick={() => setVisibleCount((current) => current + 100)}>Show more ({count(ordered.length - visible.length)} remaining)</button> : null}</>;
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
    <p className="eyebrow">{subject}</p>
    <h2>{profile.name}</h2>
    <p className="profile-context">{reported ? "Farm history, field activity, and current work in one place." : profile.limitations?.[0] || "Current operating relationships in one place."}</p>
    {reported ? <OperatingTags snapshot={profile.reported?.operating} limit={6} className="profile-operating-tags" /> : null}
    <PersonProfileFacts profile={profile} />
    <div className="profile-action">
      {reported
        ? <a className="primary-action" href="/manager?review=farm-truth">Open <span aria-hidden="true">→</span></a>
        : <a className="primary-action" href="/manager">Open <span aria-hidden="true">→</span></a>}
    </div>
  </aside>;
}

function PersonProfileFacts({ profile }: { profile: PersonProfile }) {
  if (profile.state === "reported") {
    const activity = profile.reported?.source_activity;
    const latest = activity?.latest_crop_context;
    if (profile.kind === "field_worker") {
      return <dl className="profile-facts">
        <div><dt>Farmers</dt><dd>{count(profile.reported?.reported_farmer_reach)}</dd></div>
        <div><dt>Open tasks</dt><dd>{count(profile.reported?.open_work)}</dd></div>
        <div><dt>Completed tasks</dt><dd>{count(profile.reported?.completed_work)}</dd></div>
        <div><dt>Latest activity</dt><dd>{updatedAgo(profile.reported?.latest_activity_at)}</dd></div>
        <div><dt>Latest attendance</dt><dd>{profile.reported?.latest_attendance_on || "—"}</dd></div>
        <div><dt>Visits</dt><dd>{count(activity?.reported_visits)}</dd></div>
        <div><dt>Crop inputs</dt><dd>{count(activity?.reported_input_events)}</dd></div>
        <div><dt>Disease / pest</dt><dd>{count(activity?.reported_disease)} / {count(activity?.reported_pest)}</dd></div>
        <div><dt>Latest crop check</dt><dd>{latest ? [latest.crop_stage, latest.water_condition, latest.crop_condition_score == null ? null : `${latest.crop_condition_score}/10`].filter(Boolean).join(" · ") || dateTime(latest.observed_at) : "—"}</dd></div>
      </dl>;
    }
    return <dl className="profile-facts">
      <div><dt>Farms</dt><dd>{count(profile.reported?.farm_candidates)}</dd></div>
      <div><dt>Area</dt><dd>{profile.reported?.reported_area_acres == null ? "—" : `${profile.reported.reported_area_acres} acres`}</dd></div>
      <div><dt>Open tasks</dt><dd>{count(profile.reported?.open_work)}</dd></div>
      <div><dt>Latest activity</dt><dd>{updatedAgo(profile.reported?.latest_activity_at)}</dd></div>
      <div><dt>Photos</dt><dd>{count(profile.reported?.crop_photo_references)}</dd></div>
      <div><dt>Visits</dt><dd>{count(activity?.reported_visits)}</dd></div>
      <div><dt>Crop inputs</dt><dd>{count(activity?.reported_input_events)}</dd></div>
      <div><dt>Disease / pest</dt><dd>{count(activity?.reported_disease)} / {count(activity?.reported_pest)}</dd></div>
      <div><dt>Latest crop check</dt><dd>{latest ? [latest.crop_stage, latest.water_condition, latest.crop_condition_score == null ? null : `${latest.crop_condition_score}/10`].filter(Boolean).join(" · ") || dateTime(latest.observed_at) : "—"}</dd></div>
    </dl>;
  }
  const farms = Array.from(new Map(profile.assignments.map((assignment) => [assignment.farm_id, {
    id: assignment.farm_id, name: assignment.farm_name,
  }])).values());
  return <div className="profile-groups">
    <section className="profile-relationships">
      <h3>Canonical Farms</h3>
      <ul>{farms.map((farm) => <li key={farm.id}><strong>{farm.name}</strong><Link className="text-link" href={`/farms?farm=${encodeURIComponent(farm.id)}`}>Open Farm <span aria-hidden="true">→</span></Link></li>)}</ul>
    </section>
    <section className="profile-relationships">
      <h3>Reviewed assignments</h3>
      <ul>{profile.assignments.map((assignment) => <li key={`${assignment.farm_id}-${assignment.field_id}-${assignment.role}`}><strong>{roleName(assignment.role)}</strong><span>{assignment.field_name} · {assignment.farm_name} · since {assignment.starts_on}</span></li>)}</ul>
    </section>
  </div>;
}

function AgentsView({ agents, reload }: {
  agents: AgentBoard | null;
  reload: () => void;
}) {
  const [name, setName] = useState("");
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  async function createAgent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setMessage(null);
    try {
      const response = await fetch("/api/v1/agents", {
        method: "POST", credentials: "same-origin", headers: { "content-type": "application/json" },
        body: JSON.stringify({ name, instruction }),
      });
      const payload = await response.json().catch(() => null) as { detail?: string } | null;
      if (!response.ok) throw new Error(payload?.detail || "Agent could not be saved.");
      setName(""); setInstruction(""); setMessage("Agent saved."); reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Agent could not be saved.");
    } finally { setBusy(false); }
  }

  return <section className="directory-workspace agents-workspace">
    <div className="directory-toolbar people-toolbar"><div className="directory-title"><h1>Agents</h1><span>{count(agents?.agents.length)}</span></div></div>
    <div className="agent-list">
      {(agents?.agents || []).map((agent) => <article className="agent-row" key={agent.id}>
        <strong className="agent-count">{count(agent.count)}</strong>
        <div><h3>{agent.name}</h3><p>{agent.summary}</p></div>
        <Link href={agent.id === "disease-watch" ? "/farms?state=reported" : "/farmers"} className="text-link">Open <span aria-hidden="true">→</span></Link>
      </article>)}
      {!agents ? <DirectoryLoadingState label="Opening agents" /> : null}
    </div>
    <section className="agent-builder">
      <div><p className="eyebrow">Your agent</p><h3>Tell us what to watch</h3><p>Write a plain-language notification for anything in your operating data.</p></div>
      <form className="agent-form" onSubmit={createAgent}>
        <label>Name<input value={name} onChange={(event) => setName(event.target.value)} maxLength={80} placeholder="e.g. High-priority farmers" required /></label>
        <label>Notification<textarea value={instruction} onChange={(event) => setInstruction(event.target.value)} maxLength={500} minLength={8} placeholder="Tell me when a farmer has two disease reports in a week." required /></label>
        <button className="primary-action" disabled={busy}>{busy ? "Saving…" : "Save agent"} <span aria-hidden="true">→</span></button>
      </form>
      {message ? <p className="form-error" role="status">{message}</p> : null}
      {agents?.custom_agents.length ? <div className="custom-agent-list">{agents.custom_agents.map((agent) => <CustomAgentEditor key={agent.id} agent={agent} reload={reload} />)}</div> : null}
    </section>
  </section>;
}

function CustomAgentEditor({ agent, reload }: { agent: CustomAgent; reload: () => void }) {
  const [name, setName] = useState(agent.name);
  const [instruction, setInstruction] = useState(agent.instruction);
  const [enabled, setEnabled] = useState(agent.enabled);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  async function update(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage(null);
    try {
      const response = await fetch(`/api/v1/agents/${agent.id}`, { method: "PATCH", credentials: "same-origin", headers: { "content-type": "application/json" }, body: JSON.stringify({ name, instruction, enabled }) });
      const payload = await response.json().catch(() => null) as { detail?: string } | null;
      if (!response.ok) throw new Error(payload?.detail || "Agent could not be updated.");
      setMessage("Saved."); reload();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Agent could not be updated."); } finally { setBusy(false); }
  }
  return <details className="custom-agent"><summary><span><strong>{agent.name}</strong><small>{agent.enabled ? "Active" : "Paused"}</small></span><span>Edit</span></summary><form className="agent-form" onSubmit={update}><label>Name<input value={name} onChange={(event) => setName(event.target.value)} maxLength={80} required /></label><label>Notification<textarea value={instruction} onChange={(event) => setInstruction(event.target.value)} maxLength={500} minLength={8} required /></label><label className="agent-enabled"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} /> Active</label><button className="quiet-button" disabled={busy}>{busy ? "Saving…" : "Save changes"}</button></form>{message ? <p className="form-error" role="status">{message}</p> : null}</details>;
}

function TrackwickSourceCoverage({ counts: source }: { counts: TrackwickBoard["counts"] }) {
  return <section className="reported-source-coverage">
    <div className="surface-heading"><div><p className="eyebrow">Field activity</p><h2>What we know</h2></div></div>
    <dl className="profile-facts">
      <div><dt>Visits</dt><dd>{count(source.reported_visits)}</dd></div>
      <div><dt>Disease / pest</dt><dd>{count(source.reported_signals)}</dd></div>
      <div><dt>Crop-input events</dt><dd>{count(source.reported_input_events)}</dd></div>
      <div><dt>Locations</dt><dd>{count(source.geotagged_evidence)}</dd></div>
      <div><dt>Photos</dt><dd>{count(source.crop_photo_references)}</dd></div>
    </dl>
  </section>;
}

function SourceWorkRows({ items }: { items: TrackwickWork[] }) {
  const [visibleCount, setVisibleCount] = useState(100);
  const visible = items.slice(0, visibleCount);
  return <><ol className="action-list source-work-card-grid">{visible.map((item) => <li key={item.id}><span className="severity medium">open</span><div><h3>{item.label}</h3><p>{[item.farmer_name, item.follow_up_at ? `due ${dateTime(item.follow_up_at)}` : null].filter(Boolean).join(" · ")}</p></div></li>)}</ol>{visible.length < items.length ? <button type="button" className="quiet-button directory-more" onClick={() => setVisibleCount((current) => current + 100)}>Show 100 more ({count(items.length - visible.length)} remaining)</button> : null}</>;
}

function ReportedFieldWorkers({ workers, canOpenProfiles, openProfile }: {
  workers: TrackwickFieldWorker[];
  canOpenProfiles: boolean;
  openProfile: (id: string, kind: "field_worker", recordState: "reported", openerId: string) => Promise<void>;
}) {
  const [visibleCount, setVisibleCount] = useState(40);
  const [query, setQuery] = useState("");
  const [order, setOrder] = useState<"tasks" | "assigned" | "activity">("tasks");
  const [view, setView] = useState<"all" | "attention" | "recent">("all");
  const matched = workers.filter((worker) => worker.name.toLowerCase().includes(query.trim().toLowerCase())
    && (view === "all" || view === "attention" && worker.open_work > 0 || view === "recent" && hasRecentActivity(worker.latest_activity_at)));
  const ordered = [...matched].sort((left, right) => order === "assigned"
    ? right.reported_farmer_reach - left.reported_farmer_reach || right.open_work - left.open_work || left.name.localeCompare(right.name)
    : order === "activity"
      ? new Date(right.latest_activity_at || 0).valueOf() - new Date(left.latest_activity_at || 0).valueOf() || left.name.localeCompare(right.name)
      : right.open_work - left.open_work || right.reported_farmer_reach - left.reported_farmer_reach || left.name.localeCompare(right.name));
  const visible = ordered.slice(0, visibleCount);
  return <section className="reported-field-workers">
    <div className="surface-heading"><div><p className="eyebrow">Field team</p><h2>Field workers</h2></div><span className="count-badge">{count(workers.length)}</span></div>
    <div className="directory-secondary-toolbar"><label className="directory-find"><span className="sr-only">Find field workers</span><input type="search" value={query} onChange={(event) => { setQuery(event.target.value); setVisibleCount(40); }} placeholder="Find field worker" /></label><div className="directory-view-tabs" aria-label="Field worker view"><button type="button" className={view === "all" ? "active" : ""} onClick={() => { setView("all"); setVisibleCount(40); }}>All</button><button type="button" className={view === "attention" ? "active" : ""} onClick={() => { setView("attention"); setVisibleCount(40); }}>Open tasks</button><button type="button" className={view === "recent" ? "active" : ""} onClick={() => { setView("recent"); setVisibleCount(40); }}>Active</button></div><label className="directory-order"><span className="sr-only">Order field workers</span><select value={order} onChange={(event) => { setOrder(event.target.value as typeof order); setVisibleCount(40); }}><option value="tasks">Order: open tasks</option><option value="assigned">Order: farmers assigned</option><option value="activity">Order: latest activity</option></select></label></div>
    <div className="people-list source-card-grid">{visible.map((worker) => <button id={`profile-reported-field-worker-${worker.id}`} type="button" className="person-row compact-entity-card" key={worker.id} onClick={(event) => void openProfile(worker.id, "field_worker", "reported", event.currentTarget.id)}><span className="person-initial">{worker.name.slice(0, 1).toUpperCase()}</span><div className="person-summary"><p className="entity-card-type">Field worker</p><h3>{worker.name}</h3><div className="entity-card-metrics"><span><strong>{count(worker.reported_farmer_reach)}</strong> Farmers Assigned</span><span className={worker.open_work ? "attention" : undefined}><strong>{count(worker.open_work)}</strong> Open Tasks</span><span><strong>{count(worker.completed_work)}</strong> Completed</span></div><OperatingTags snapshot={worker.operating} limit={2} /><p className="entity-card-updated">{updatedAgo(worker.latest_activity_at)}</p></div></button>)}</div>{visible.length < ordered.length ? <button type="button" className="quiet-button directory-more" onClick={() => setVisibleCount((current) => current + 40)}>Show 40 more ({count(ordered.length - visible.length)} remaining)</button> : null}
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
    <div className="surface-heading"><div><p className="eyebrow">Field watch</p><h2>Disease &amp; pest</h2></div><span className="count-badge">{count(filtered.length)} of {count(total)}</span></div>
    <div className="signal-filters" aria-label="Filter field issues">
      <label>Type<select value={kind} onChange={(event) => setKind(event.target.value as typeof kind)}><option value="all">All reports</option><option value="disease">Disease</option><option value="pest">Pest</option></select></label>
      <label>Severity<select value={severity} onChange={(event) => setSeverity(event.target.value as typeof severity)}><option value="all">All severities</option><option value="critical">Critical</option><option value="high">High</option><option value="moderate">Moderate</option><option value="low">Low</option><option value="unknown">Not declared</option></select></label>
      <label>From<input type="date" value={from} onChange={(event) => setFrom(event.target.value)} /></label>
      <label>To<input type="date" value={to} onChange={(event) => setTo(event.target.value)} /></label>
    </div>
    {filtered.length ? <><ol className="action-list reported-signal-list">{visible.map((signal) => <li key={signal.id}><span className={`severity ${signal.declared_severity}`}>{signal.declared_severity}</span><div><h3>{signal.finding_kind === "disease" ? "Disease" : "Pest"}</h3><p>{[signal.farmer_name, dateTime(signal.observed_at)].filter(Boolean).join(" · ")}</p></div></li>)}</ol>{visible.length < filtered.length ? <button type="button" className="quiet-button" onClick={() => setVisibleCount((current) => current + 100)}>Show 100 more ({count(filtered.length - visible.length)} remaining)</button> : null}</> : <p className="empty-copy">No issues match these filters.</p>}
  </section>;
}

function ActionRows({ items, empty }: { items: LedgerItem[]; empty: string }) {
  if (!items.length) return <p className="empty-copy">{empty}</p>;
  return <ol className="action-list">{items.map((item) => <li key={`${item.entity.type}-${item.entity.id}`}><span className={`severity ${item.severity}`}>{item.severity}</span><div><h3>{item.title}</h3><p>{actionLine(item)}</p></div><Link className="text-link" href={item.allocation_id ? `/farms?field=${encodeURIComponent(item.allocation_id)}` : "/actions"}>Open <span aria-hidden="true">→</span></Link></li>)}</ol>;
}

function SettingsView({ t, state, managerBusy, logout }: {
  t: Translation; state: State; managerBusy: boolean; logout: () => Promise<void>;
}) {
  const session = state.session;
  const history = state.procurementHistory?.summary;
  const trackwick = state.trackwick;
  const trackwickStatus = trackwick?.source.state === "succeeded"
    ? `Updated ${dateTime(trackwick.source.last_synced_at)}.`
    : "No field updates yet.";
  return <section className="directory-workspace settings-workspace">
    <div className="directory-toolbar people-toolbar"><div className="directory-title"><h1>Settings</h1></div></div>
    <div className="settings-rows">
      <div><strong>People</strong><span>{session?.authenticated ? "Manage named ID access below." : "Use your admin ID to manage access."}</span></div>
      <div><strong>Purchase history</strong><span>{history ? `${count(history.coverage.quantity_qtl)} qtl across ${count(history.coverage.villages)} villages, ${history.coverage.months.join(" · ")}. Historical context only.` : "No reviewed purchase history yet."}</span></div>
      <div><strong>Field updates</strong><span>{trackwickStatus}</span></div>
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
    <p className="surface-copy">Create access only for people you have confirmed.</p>
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

function DirectoryLoadingState({ label }: { label: string }) {
  return <section className="directory-loading" role="status" aria-live="polite" aria-label={label}>
    <p><span className="directory-loading-dot" aria-hidden="true" />{label}</p>
    <div className="directory-skeleton-grid" aria-hidden="true">
      {Array.from({ length: 8 }, (_, index) => <i className="directory-skeleton-card" key={index} />)}
    </div>
  </section>;
}

function MapLoadingState({ label }: { label: string }) {
  return <div className="map-loading" role="status" aria-live="polite" aria-label={label}>
    <span className="directory-loading-dot" aria-hidden="true" />
    <p>{label}</p>
    <i /><i /><i />
  </div>;
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
