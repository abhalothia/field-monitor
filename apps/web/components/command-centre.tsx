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
  categories?: {
    crop_profile: "pb1" | "1718" | "mixed" | "not_recorded";
    linked_place_count: number;
    latest_activity_kind: "registration" | "visit" | "issue" | "work" | "location" | "photo" | "attendance" | "unknown";
    coverage: {
      location_recorded: boolean;
      photo_recorded: boolean;
      visit_recorded: boolean;
      issue_recorded: boolean;
      area_recorded: boolean;
      crop_recorded: boolean;
    };
    freshness: "updated_today" | "updated_this_week" | "updated_this_month" | "earlier_activity" | "no_activity_recorded";
    workload: "no_open_tasks" | "one_to_two_open_tasks" | "three_or_more_open_tasks";
  };
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
type PlaceOperatingSummary = {
  id: string;
  place: string;
  metrics: {
    reported_farm_count: number;
    farmer_count: number;
    field_worker_count: number;
    open_task_count: number;
    visit_count: number;
    issue_report_count: number;
    location_evidence_count: number;
    photo_reference_count: number;
    latest_activity_at?: string | null;
    refreshed_at?: string | null;
  };
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
  map?: { points: Array<MapPoint>; places?: PlaceOperatingSummary[]; total_points: number; truncated: boolean };
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
  has_disease?: boolean;
  related_farm?: { id: string; name: string; place: string; farmer_name: string | null } | null;
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

type OperatingAgent = { id: string; name: string; count: number; summary: string; status: "live" };
type CustomAgent = { id: string; name: string; instruction: string; enabled: boolean; status: "in_review" | "live"; updated_at: string };
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
const FIELD_WEATHER_CACHE_PREFIX = "agro-ceo-field-weather-v1:";
const FIELD_WEATHER_CACHE_TTL_MS = 60 * 60_000;
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

function clearPrivateBrowserCache() {
  try {
    for (let index = window.sessionStorage.length - 1; index >= 0; index -= 1) {
      const key = window.sessionStorage.key(index);
      if (key === OPERATING_CACHE_KEY || key?.startsWith(DIRECTORY_CACHE_PREFIX) || key?.startsWith(PROFILE_CACHE_PREFIX)) {
        window.sessionStorage.removeItem(key);
      }
    }
  } catch { /* storage cleanup must never block a sign-out */ }
}

function endExpiredWorkspaceSession() {
  clearPrivateBrowserCache();
  void fetch("/api/v1/launch/logout", { method: "POST", credentials: "same-origin" }).catch(() => undefined);
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
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const error = new Error("The operating record is unavailable.") as Error & { status?: number; detail?: string };
    error.status = response.status;
    error.detail = typeof payload?.detail === "string" ? payload.detail : undefined;
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

function matchesRecordedEvidence(
  snapshot: OperatingSnapshot | undefined,
  filters: Array<"all" | "location" | "visit" | "photo" | "issue" | "crop">,
) {
  if (filters.includes("all")) return true;
  const coverage = snapshot?.categories?.coverage || {
    location_recorded: Boolean(snapshot?.metrics.location_evidence_count),
    photo_recorded: Boolean(snapshot?.metrics.photo_reference_count),
    visit_recorded: Boolean(snapshot?.metrics.visit_count),
    issue_recorded: Boolean((snapshot?.metrics.disease_report_count || 0) + (snapshot?.metrics.pest_report_count || 0)),
    area_recorded: snapshot?.metrics.reported_area_acres !== null && snapshot?.metrics.reported_area_acres !== undefined,
    crop_recorded: false,
  };
  return filters.includes("location") && coverage.location_recorded
    || filters.includes("visit") && coverage.visit_recorded
    || filters.includes("photo") && coverage.photo_recorded
    || filters.includes("issue") && coverage.issue_recorded
    || filters.includes("crop") && coverage.crop_recorded;
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
  const [notificationMenuOpen, setNotificationMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [profileSelection, setProfileSelection] = useState<ProfileSelection | null>(null);
  const stateRef = useRef<State>(EMPTY_STATE);
  const cachedStateRef = useRef<Partial<State> | null>(null);
  const loadRequest = useRef<Promise<void> | null>(null);
  const profileRequest = useRef(0);
  const profileOpener = useRef<string | null>(null);
  const commandToolsRef = useRef<HTMLDivElement>(null);
  const t = WORDS[language];

  useEffect(() => {
    try {
      const cached = window.sessionStorage.getItem(OPERATING_CACHE_KEY);
      if (!cached) return;
      const value = JSON.parse(cached) as Partial<State>;
      if (!value.session?.authenticated) return;
      cachedStateRef.current = value;
      // Cached records make the shell feel immediate, but they must never revive an expired sign-in.
      setState((current) => ({ ...current, ...value, session: null, loading: false, error: null }));
    } catch { /* a bad local cache should never block the operating record */ }
  }, []);

  useEffect(() => { stateRef.current = state; }, [state]);

  useEffect(() => {
    if (state.session && !state.session.authenticated) {
      cachedStateRef.current = null;
      try { window.sessionStorage.removeItem(OPERATING_CACHE_KEY); } catch { /* cache cleanup never blocks the record */ }
      return;
    }
    if (!state.session?.authenticated || !state.profile || !state.trackwick) return;
    try {
      const { session: _session, loading: _loading, error: _error, needsLaunchLogin: _needsLaunchLogin, ...cached } = state;
      const cacheValue = { ...cached, session: { authenticated: true } };
      cachedStateRef.current = cacheValue;
      window.sessionStorage.setItem(OPERATING_CACHE_KEY, JSON.stringify(cacheValue));
    } catch { /* cache is an enhancement, not a dependency */ }
  }, [state]);

  const load = useCallback((force = false) => {
    if (loadRequest.current) return loadRequest.current;
    // Always confirm access with the server. The cache is for rendering, never authorization.
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
      endExpiredWorkspaceSession();
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
      if (!(event.metaKey || event.ctrlKey) || !["f", "k"].includes(event.key.toLowerCase())) return;
      event.preventDefault();
      setNotificationMenuOpen(false);
      setProfileMenuOpen(false);
      setSearchOpen(true);
    }
    window.addEventListener("keydown", openSearch);
    return () => window.removeEventListener("keydown", openSearch);
  }, []);

  useEffect(() => {
    function dismissMenus(event: PointerEvent) {
      if (!commandToolsRef.current?.contains(event.target as Node)) {
        setNotificationMenuOpen(false);
        setProfileMenuOpen(false);
      }
    }
    function dismissWithEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setNotificationMenuOpen(false);
      setProfileMenuOpen(false);
      setSearchOpen(false);
    }
    document.addEventListener("pointerdown", dismissMenus);
    window.addEventListener("keydown", dismissWithEscape);
    return () => {
      document.removeEventListener("pointerdown", dismissMenus);
      window.removeEventListener("keydown", dismissWithEscape);
    };
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
        const reauth = requiresReauthentication(error);
        if (reauth) expireManagerSession(requiresLaunchLogin(error));
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

  const expireManagerSession = useCallback((launchLogin = false) => {
    if (launchLogin) endExpiredWorkspaceSession();
    setState((current) => ({
      ...current,
      session: launchLogin ? null : { authenticated: false },
      needsLaunchLogin: launchLogin || current.needsLaunchLogin,
    }));
  }, []);

  async function endManagerSession() {
    setManagerBusy(true);
    try {
      clearPrivateBrowserCache();
      const response = await fetch("/api/v1/launch/logout", { method: "POST", credentials: "same-origin" });
      if (!response.ok) throw new Error("Could not sign out.");
      setNotificationMenuOpen(false);
      setProfileMenuOpen(false);
      // A logout must never leave the previous private board on screen.
      setState({ ...EMPTY_STATE, session: { authenticated: false }, loading: false, needsLaunchLogin: true });
    } catch {
      setState((current) => ({ ...current, error: "We could not sign you out. Check your connection and try again." }));
    } finally {
      setManagerBusy(false);
    }
  }

  const notificationItems = (state.agents?.agents || []).filter((agent) => agent.count > 0).slice(0, 4);

  if (state.needsLaunchLogin) {
    return (
      <main className="session-wall">
        <section className="session-wall-card"><p className="eyebrow">AGRO CEO</p><h1>Your session ended.</h1><p>For your security, sign in again to continue where you left off.</p><Link href={`/login?next=/${view}&reason=session-expired`} className="primary-action">{t.signIn} <span aria-hidden="true">→</span></Link></section>
      </main>
    );
  }

  return (
    <main className={`command-shell command-shell-${view}`}>
      <header className="command-header">
        <Link className="brand-mark" href="/home"><i aria-hidden="true" /> AGRO CEO</Link>
        <nav className="command-nav" aria-label="AGRO CEO views">
          {NAV.map((item) => <Link key={item.view} href={item.href} aria-current={item.view === view ? "page" : undefined} className={item.view === view ? "nav-link active" : "nav-link"}>{t[item.view]}</Link>)}
        </nav>
        <div className="command-tools" ref={commandToolsRef}>
          <button type="button" className="tool-icon language-toggle" onClick={() => setLanguage((current) => current === "en" ? "hi" : "en")} aria-label="Switch interface language">{language === "en" ? t.hindi : t.english}</button>
          <button type="button" className="tool-icon" onClick={() => { setNotificationMenuOpen(false); setProfileMenuOpen(false); setSearchOpen(true); }} aria-label="Search farms, farmers, and workers" title="Search (⌘F)"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.8" cy="10.8" r="6.8" /><path d="m16 16 4.2 4.2" /></svg></button>
          <div className="notification-menu"><button type="button" className="tool-icon notification-toggle" onClick={() => { setNotificationMenuOpen((current) => !current); setProfileMenuOpen(false); }} aria-expanded={notificationMenuOpen} aria-controls="notification-panel" aria-label={notificationItems.length ? `Notifications: ${notificationItems.length} items need attention` : "Notifications"} title="Notifications"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></svg>{notificationItems.length ? <span className="notification-dot" aria-hidden="true" /> : null}</button>{notificationMenuOpen ? <NotificationDropdown items={notificationItems} close={() => setNotificationMenuOpen(false)} /> : null}</div>
          <div className="profile-menu"><button type="button" className="profile-avatar" onClick={() => { setProfileMenuOpen((current) => !current); setNotificationMenuOpen(false); }} aria-expanded={profileMenuOpen} aria-controls="profile-panel" aria-label="Fortune Farms menu"><img src="/favicon.png" alt="" /></button>{profileMenuOpen ? <div id="profile-panel" className="profile-dropdown"><div className="menu-heading"><strong>Fortune Farms</strong><span>Signed in</span></div><Link href="/settings" onClick={() => setProfileMenuOpen(false)}>Settings</Link><button type="button" onClick={() => void endManagerSession()} disabled={managerBusy}>{managerBusy ? "Logging out…" : "Log out"}</button></div> : null}</div>
        </div>
      </header>
      {searchOpen ? <CommandSearch items={commandSearchItems(state)} close={() => setSearchOpen(false)} refresh={() => void load(true)} /> : null}

      {view === "home" || view === "map" || view === "fields" || view === "farmers" ? <section className={`command-intro ${view !== "home" ? "command-intro-compact" : ""}`}>
        <div>
          <p className="eyebrow">{state.profile?.coverage_label || "Fortune Farms"}</p>
          {view === "home" ? <FieldMoment points={state.trackwick?.map?.points || []} /> : <h1>{headingFor(view, t)}</h1>}
        </div>
      </section> : null}

      {state.error && view !== "home" ? <div className="honest-notice honest-notice-action" role="status"><span>{state.error}</span><button type="button" onClick={() => void load(true)}>Try again</button></div> : state.stale ? <div className="honest-notice honest-notice-stale honest-notice-action" role="status"><span>Showing your last saved view while we reconnect.</span><button type="button" onClick={() => void load(true)}>Refresh</button></div> : null}
      {view === "home" ? <HomeView t={t} state={state} retry={() => void load(true)} /> : null}
      {view === "map" ? <MapView state={state} /> : null}
      {view === "fields" ? <FieldsView t={t} state={state} canOpenProfiles={Boolean(state.session?.authenticated)} accessResolved={state.session !== null} expireManagerSession={expireManagerSession} /> : null}
      {view === "farmers" ? <FarmersView farmers={state.canonicalFarmers} readiness={state.readiness} trackwick={state.trackwick} canOpenProfiles={Boolean(state.session?.authenticated)} accessResolved={state.session !== null} selection={profileSelection} openProfile={openPersonProfile} closeProfile={closeProfile} /> : null}
      {view === "actions" ? <AgentsView agents={state.agents} reload={() => void load(true)} /> : null}
      {view === "settings" ? <SettingsView state={state} managerBusy={managerBusy} logout={endManagerSession} /> : null}
      <nav className="mobile-nav" aria-label="Primary views">
        {NAV.filter((item) => item.view !== "settings").map((item) => <Link key={item.view} href={item.href} aria-current={item.view === view ? "page" : undefined} className={item.view === view ? "active" : ""}>{t[item.view]}</Link>)}
      </nav>
    </main>
  );
}

function headingFor(view: View, t: Translation) {
  return ({ home: "Today, in the field.", map: "Map", fields: languageFarmHeading(t), farmers: t.farmers, actions: t.nextMove, settings: t.settings })[view];
}

type FieldWeather = { temperature: number; code: number; fetchedAt: number };

function FieldMoment({ points }: { points: MapPoint[] }) {
  const [now, setNow] = useState<Date | null>(null);
  const [weather, setWeather] = useState<FieldWeather | null>(null);
  const fieldLocation = useMemo(() => {
    if (!points.length) return null;
    const latitude = points.reduce((total, point) => total + point.latitude, 0) / points.length;
    const longitude = points.reduce((total, point) => total + point.longitude, 0) / points.length;
    return { latitude, longitude };
  }, [points]);

  useEffect(() => {
    const updateClock = () => setNow(new Date());
    updateClock();
    const interval = window.setInterval(updateClock, 60_000);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!fieldLocation) return;
    const cacheKey = `${FIELD_WEATHER_CACHE_PREFIX}${fieldLocation.latitude.toFixed(1)}:${fieldLocation.longitude.toFixed(1)}`;
    const cached = readSessionCache<FieldWeather>(cacheKey);
    if (cached && cached.fetchedAt > Date.now() - FIELD_WEATHER_CACHE_TTL_MS) {
      setWeather(cached);
      return;
    }
    let active = true;
    const params = new URLSearchParams({
      latitude: fieldLocation.latitude.toFixed(4),
      longitude: fieldLocation.longitude.toFixed(4),
      current: "temperature_2m,weather_code",
      timezone: "auto",
    });
    void fetch(`https://api.open-meteo.com/v1/forecast?${params}`, { cache: "no-store" })
      .then((response) => response.ok ? response.json() as Promise<{ current?: { temperature_2m?: number; weather_code?: number } }> : null)
      .then((payload) => {
        const current = payload?.current;
        if (!active || typeof current?.temperature_2m !== "number" || typeof current.weather_code !== "number") return;
        const next = { temperature: current.temperature_2m, code: current.weather_code, fetchedAt: Date.now() };
        writeSessionCache(cacheKey, next);
        setWeather(next);
      }).catch(() => { /* weather is useful context, never a blocker */ });
    return () => { active = false; };
  }, [fieldLocation]);

  const date = now ? new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "long", timeZone: "Asia/Kolkata" }).format(now) : "Field briefing";
  const time = now ? new Intl.DateTimeFormat("en-IN", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: "Asia/Kolkata", timeZoneName: "short" }).format(now) : "";
  const weatherLine = weather ? `${Math.round(weather.temperature)}°C · ${weatherLabel(weather.code)}` : "Weather updating";
  return <div className="field-moment"><h1>{date}{time ? <span> · {time}</span> : null}</h1><p><i aria-hidden="true">{weather ? weatherIcon(weather.code) : "◌"}</i>{weatherLine}</p></div>;
}

function weatherIcon(code: number) {
  if (code === 0) return "☀";
  if (code <= 3) return "⛅";
  if (code <= 48) return "☁";
  if (code <= 67 || code <= 82) return "☂";
  if (code <= 86) return "❄";
  return "ϟ";
}

function weatherLabel(code: number) {
  if (code === 0) return "Clear";
  if (code <= 2) return "Partly cloudy";
  if (code === 3) return "Overcast";
  if (code <= 48) return "Foggy";
  if (code <= 57) return "Drizzle";
  if (code <= 67) return "Rain";
  if (code <= 77) return "Snow showers";
  if (code <= 82) return "Rain showers";
  if (code <= 86) return "Snow showers";
  return "Thunderstorms";
}

function commandSearchItems(state: State): CommandSearchItem[] {
  const all: CommandSearchItem[] = [
    ...(state.trackwick?.farms || []).map((farm) => ({ id: farm.id, kind: "farm" as const, name: farm.place, detail: farm.farmer_name, href: `/farms?reported_farm=${encodeURIComponent(farm.id)}` })),
    ...(state.trackwick?.farmers || []).map((farmer) => ({ id: farmer.id, kind: "farmer" as const, name: personName(farmer.name), detail: `${count(farmer.farm_candidates)} reported registrations · ${count(farmer.open_work)} open tasks`, href: `/farmers?person=${encodeURIComponent(farmer.id)}` })),
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

function HomeView({ t, state, retry }: { t: Translation; state: State; retry: () => void }) {
  const isFirstLoad = state.loading && state.updatedAt === null && !state.trackwick;
  if (isFirstLoad) return <HomeLoadingState />;
  if (state.error && !state.trackwick) return <HomeUnavailableState retry={retry} />;

  const portfolio = state.portfolio;
  const readiness = state.readiness;
  const history = state.procurementHistory?.summary;
  const trackwick = state.trackwick;
  const nextMove = portfolio?.risk_action_ledger.items[0];
  const firstTruth = readiness?.next_stage;
  const reportedFarmCount = trackwick?.counts.farm_candidates || 0;
  const mapPoints = trackwick?.map?.points || [];
  const locationCount = trackwick?.map?.total_points || trackwick?.counts.geotagged_evidence || 0;
  const hasBoard = Boolean(trackwick);
  const isEmptyBoard = hasBoard && !reportedFarmCount && !mapPoints.length;
  const title = reportedFarmCount
    ? `${count(reportedFarmCount)} farms in the field.`
    : isEmptyBoard
      ? "No field activity yet."
      : nextMove?.title || firstTruth?.title || "Field activity is ready.";
  const detail = reportedFarmCount
    ? `${count(trackwick?.counts.reported_visits)} visits · ${count(trackwick?.counts.reported_signals)} field issues · ${count(trackwick?.counts.open_work)} open tasks.`
    : isEmptyBoard
      ? "New field activity will appear here as it is recorded."
      : nextMove ? actionLine(nextMove) : history ? `${count(history.coverage.quantity_qtl)} qtl across ${count(history.coverage.villages)} villages.` : "Saved field activity will appear here when available.";
  const mapIsPreparing = state.loading && !mapPoints.length;
  return <section className="single-surface home-map-stage">
    <div className="home-map-copy"><p className="eyebrow">Fortune Farms</p><h2>{title}</h2><p>{detail}</p>{hasBoard ? <div className="home-map-metrics"><span><strong>{count(locationCount)}</strong> locations</span><span><strong>{count(trackwick?.counts.farmers)}</strong> farmers</span><span><strong>{count(trackwick?.counts.field_workers)}</strong> field workers</span></div> : null}<Link href="/map" className="primary-action">Open map <span aria-hidden="true">→</span></Link></div>
    {mapIsPreparing ? <MapLoadingState label="Loading field activity" /> : <OperatingMap points={mapPoints} preview />}
  </section>;
}

function HomeLoadingState() {
  return <section className="single-surface home-map-stage home-loading-stage" role="status" aria-live="polite" aria-busy="true">
    <div className="home-map-copy home-loading-copy"><p className="eyebrow">Fortune Farms</p><p className="home-loading-status"><span className="directory-loading-dot" aria-hidden="true" />Loading workspace</p><h2>Preparing your field view.</h2><p>Opening saved activity, then checking for updates.</p><span className="home-loading-progress" aria-hidden="true"><i /></span></div>
    <div className="home-loading-map" aria-hidden="true"><div><span className="home-loading-map-label">Field activity</span><strong>Loading the map</strong><p>Your saved view appears first.</p><span className="home-loading-map-progress"><i /></span></div></div>
  </section>;
}

function HomeUnavailableState({ retry }: { retry: () => void }) {
  return <section className="single-surface home-map-stage home-loading-stage home-unavailable" role="status">
    <div className="home-map-copy home-loading-copy"><p className="eyebrow">Fortune Farms</p><p className="home-loading-status">Connection paused</p><h2>The field workspace could not open.</h2><p>We will keep your last saved view whenever one is available. Try again when you are ready.</p><button type="button" className="primary-action" onClick={retry}>Try again <span aria-hidden="true">→</span></button></div>
    <div className="home-loading-map" aria-hidden="true"><div><span className="home-loading-map-label">Field activity</span><strong>Waiting to reconnect</strong><p>Nothing has been replaced with an empty view.</p></div></div>
  </section>;
}

function OperatingMap({ points, preview = false, selectedPoint, onSelect, emptyState, clearFilters }: { points: MapPoint[]; preview?: boolean; selectedPoint?: MapPoint | null; onSelect?: (point: MapPoint | null) => void; emptyState?: { title: string; detail: string }; clearFilters?: () => void }) {
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
          radius: active?.id === point.id ? 9 : status.tone === "disease" ? 7.2 : status.tone === "task" ? 6.6 : 5.8,
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

  if (!visible.length) return <div className="operating-map map-empty"><strong>{emptyState?.title || "No saved location activity yet"}</strong><p>{emptyState?.detail || "Location activity will appear here after a field visit is recorded."}</p>{clearFilters ? <button type="button" className="quiet-button" onClick={clearFilters}>Clear filters</button> : null}</div>;
  const area = mapAreaLabel(visible);
  return <div className={`operating-map ${preview ? "operating-map-preview" : ""}`} aria-label="Field activity map">
    <div className="leaflet-map" ref={mapElement} aria-hidden={mapHealth !== "ready"} />
    {mapHealth !== "ready" ? <CachedMapFallback points={visible} onSelect={select} /> : null}
    <div className="map-area-label"><strong>{area}</strong><span className="map-gesture-copy">Drag · scroll to zoom</span><span className="map-touch-copy">Drag · pinch to zoom</span></div>
    {!preview ? <MapLegend /> : null}
    {preview && active ? <MapGlance point={active} close={() => select(null)} /> : null}
  </div>;
}

function MapLegend() {
  return <div className="map-legend" aria-label="Map marker legend"><span className="disease"><i />Disease reported</span><span className="task"><i />Open task</span><span className="current"><i />Recently checked</span><span className="earlier"><i />Earlier activity</span></div>;
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
  const [days, setDays] = useState<"all" | "7" | "30">("30");
  const [focus, setFocus] = useState<Array<"all" | "disease" | "recent_checked" | "open_tasks">>(["all"]);
  const [selected, setSelected] = useState<MapPoint | null>(null);
  const allPoints = state.trackwick?.map?.points || [];
  const mapIsPreparing = state.loading && !allPoints.length;
  const points = useMemo(() => {
    const minimum = days === "all" ? null : Date.now() - Number(days) * 86_400_000;
    const needle = query.trim().toLocaleLowerCase();
    return allPoints.filter((point) => {
      if (kind === "reported_farm" && point.subject.kind !== kind && !point.related_farm) return false;
      if (kind !== "all" && kind !== "reported_farm" && point.subject.kind !== kind) return false;
      if (minimum && new Date(point.observed_at).valueOf() < minimum) return false;
      if (!matchesMapFocus(point, focus)) return false;
      if (!needle) return true;
      return [point.subject.name, point.subject.place, point.subject.farmer_name, point.label].filter(Boolean).some((value) => value!.toLocaleLowerCase().includes(needle));
    });
  }, [allPoints, days, focus, kind, query]);
  useEffect(() => {
    setSelected((current) => {
      if (current && points.some((point) => point.id === current.id)) return current;
      return points.find((point) => point.subject.kind === "field_worker") || points[0] || null;
    });
  }, [points]);
  const viewLabel = kind === "reported_farm" ? "farm" : kind === "field_worker" ? "worker" : kind === "farmer" ? "farmer" : "field";
  const diseaseCount = points.filter((point) => point.has_disease).length;
  const openTaskCount = points.filter((point) => point.subject.open_work > 0).length;
  const clearFilters = () => { setQuery(""); setKind("all"); setDays("all"); setFocus(["all"]); };
  const hasActiveFilters = Boolean(query.trim()) || kind !== "all" || days !== "all" || !focus.includes("all");
  return <section className={`map-workspace ${selected ? "map-workspace-selected" : ""}`}>
    <div className="map-controls" aria-label="Map filters">
      <label>Find<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Farmer, farm, village" /></label>
      <MapTabs label="View" value={kind} onChange={setKind} options={[["all", "Everything"], ["reported_farm", "Farms"], ["farmer", "Farmers"], ["field_worker", "Workers"]]} />
      <MapTabs label="Activity date" value={days} onChange={setDays} options={[["7", "Last 7 days"], ["30", "Last 30 days"], ["all", "All history"]]} />
      <MultiFilter label="Show" values={focus} options={[["all", "All points"], ["disease", "Disease reported"], ["recent_checked", "Recently checked"], ["open_tasks", "Open tasks"]]} onChange={setFocus} />
      <p className="map-summary" aria-live="polite"><strong>{count(points.length)} {viewLabel} {points.length === 1 ? "location" : "locations"}</strong>{diseaseCount || openTaskCount ? <span>{[diseaseCount ? `${count(diseaseCount)} disease-marked ${diseaseCount === 1 ? "location" : "locations"}` : null, openTaskCount ? `${count(openTaskCount)} ${openTaskCount === 1 ? "location" : "locations"} with open tasks` : null].filter(Boolean).join(" · ")}</span> : <span>No reported disease or open tasks</span>}</p>
    </div>
    <div className="map-content"><div className="map-canvas">{mapIsPreparing ? <MapLoadingState label="Loading map" /> : <OperatingMap points={points} selectedPoint={selected} onSelect={setSelected} clearFilters={allPoints.length && hasActiveFilters ? clearFilters : undefined} emptyState={allPoints.length ? { title: "No locations match this view", detail: "Try a broader activity window, another record type, or clear the map filters." } : { title: "No saved location activity yet", detail: "Location activity will appear here after a field visit is recorded." }} />}</div></div>
    {selected ? <MapInspector point={selected} state={state} viewKind={kind} close={() => setSelected(null)} /> : null}
  </section>;
}

function MapTabs<T extends string>({ label, value, onChange, options }: { label: string; value: T; onChange: (value: T) => void; options: ReadonlyArray<readonly [T, string]> }) {
  return <div className="map-type-tabs" aria-label={label}><span>{label}</span><div>{options.map(([option, title]) => <button type="button" key={option} className={value === option ? "active" : ""} aria-pressed={value === option} onClick={() => onChange(option)}>{title}</button>)}</div></div>;
}

function MapInspector({ point, state, viewKind, close }: { point: MapPoint; state: State; viewKind: "all" | MapSubjectKind; close: () => void }) {
  const relatedFarm = viewKind === "reported_farm" && point.subject.kind !== "reported_farm" ? point.related_farm : null;
  const subject = relatedFarm ? { ...point.subject, kind: "reported_farm" as const, id: relatedFarm.id, name: relatedFarm.name, place: relatedFarm.place, farmer_name: relatedFarm.farmer_name } : point.subject;
  const status = mapActivityStatus(point);
  const metrics = subject.operating?.metrics;
  const matchingActivity = (state.trackwick?.map?.points || []).filter((candidate) => subject.kind === "reported_farm"
    ? candidate.subject.kind === "reported_farm" && candidate.subject.id === subject.id || candidate.related_farm?.id === subject.id
    : candidate.subject.kind === subject.kind && candidate.subject.id === subject.id).sort((a, b) => new Date(b.observed_at).valueOf() - new Date(a.observed_at).valueOf());
  const farm = subject.kind === "reported_farm" ? state.trackwick?.farms.find((candidate) => candidate.id === subject.id) : null;
  const farmer = subject.kind === "farmer" ? state.trackwick?.farmers.find((candidate) => candidate.id === subject.id) : null;
  const worker = subject.kind === "field_worker" ? state.trackwick?.field_workers.find((candidate) => candidate.id === subject.id) : null;
  const placeSummary = subject.place
    ? (state.trackwick?.map?.places || []).find((place) => place.place === subject.place)
    : null;
  const facts = subject.kind === "reported_farm"
    ? [["Farmer", farm?.farmer_name || subject.farmer_name || "—"], ["Plots", count(farm?.reported_plot_count ?? undefined)], ["Open Tasks", count(metrics?.open_task_count ?? farm?.open_work ?? subject.open_work)], ["Field Activity", count(metrics?.location_evidence_count ?? matchingActivity.length)]]
    : subject.kind === "farmer"
      ? [["Reported registrations", count(metrics?.farm_count ?? farmer?.farm_candidates)], ["Open Tasks", count(metrics?.open_task_count ?? farmer?.open_work ?? subject.open_work)], ["Photo Evidence", count(metrics?.photo_reference_count ?? farmer?.crop_photo_references)], ["Field Activity", count(metrics?.location_evidence_count ?? matchingActivity.length)]]
      : subject.kind === "field_worker"
        ? [["Farmers Assigned", count(metrics?.farmer_count ?? worker?.reported_farmer_reach)], ["Open Tasks", count(metrics?.open_task_count ?? worker?.open_work ?? subject.open_work)], ["Completed Work", count(metrics?.completed_work_count ?? worker?.completed_work)], ["Field Activity", count(metrics?.location_evidence_count ?? matchingActivity.length)]]
        : [["Place", subject.place || "—"], ["Open Tasks", count(subject.open_work)], ["Field Activity", count(matchingActivity.length)], ["Last Activity", dateTime(point.observed_at)]];
  const placeFacts = placeSummary ? [
    ["Farms here", count(placeSummary.metrics.reported_farm_count)],
    ["Farmers here", count(placeSummary.metrics.farmer_count)],
    ["Field workers", count(placeSummary.metrics.field_worker_count)],
    ["Open farmer tasks", count(placeSummary.metrics.open_task_count)],
  ] : [];
  return <aside className="map-inspector" aria-label="Selected map record">
    <div className="map-inspector-record">
      <button type="button" className="map-glance-close" onClick={close} aria-label="Close selected record">×</button>
      <p className="eyebrow">{subject.kind === "reported_farm" ? "Farm registration" : subject.kind.replaceAll("_", " ")}</p>
      <h2>{subject.name}</h2>
      <p className="map-inspector-place">{[subject.place, subject.farmer_name].filter(Boolean).join(" · ") || "Field activity location"}<span>{updatedAgo(point.observed_at)}</span></p>
      <div className="map-record-tags"><span>{subject.kind === "reported_farm" ? "Farm registration" : subject.kind.replaceAll("_", " ")}</span><span className={status.tone}>{status.label}</span><OperatingTagChips snapshot={subject.operating} limit={2} /></div>
      <dl>{[...facts, ...placeFacts].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
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

type MapActivityTone = "disease" | "task" | "current" | "earlier";

function matchesMapFocus(point: MapPoint, focus: Array<"all" | "disease" | "recent_checked" | "open_tasks">) {
  if (focus.includes("all")) return true;
  const activityAge = Date.now() - new Date(point.observed_at).valueOf();
  const openTasks = point.subject.open_work;
  return focus.includes("disease") && Boolean(point.has_disease)
    || focus.includes("recent_checked") && activityAge <= 7 * 86_400_000
    || focus.includes("open_tasks") && openTasks > 0;
}

function mapActivityStatus(point: MapPoint): { tone: MapActivityTone; label: string } {
  const openTasks = point.subject.open_work;
  if (point.has_disease) return { tone: "disease", label: "Disease reported" };
  if (openTasks > 0) return { tone: "task", label: openTasks === 1 ? "1 open task" : `${openTasks} open tasks` };
  const age = Date.now() - new Date(point.observed_at).valueOf();
  if (age <= 7 * 86_400_000) return { tone: "current", label: "Updated this week" };
  if (age <= 30 * 86_400_000) return { tone: "current", label: "Updated this month" };
  return { tone: "earlier", label: "Earlier activity" };
}

function mapClusterStatus(points: MapPoint[]) {
  const statuses = points.map(mapActivityStatus);
  const disease = statuses.filter((status) => status.tone === "disease").length;
  const task = statuses.filter((status) => status.tone === "task").length;
  const current = statuses.filter((status) => status.tone === "current").length;
  if (disease) return { tone: "disease" as const, label: `${count(disease)} disease reports` };
  if (task) return { tone: "task" as const, label: `${count(task)} open tasks` };
  if (current) return { tone: "current" as const, label: `${count(current)} updated recently` };
  return { tone: "earlier" as const, label: "Earlier activity" };
}

function mapMarkerColor(tone: MapActivityTone) {
  return ({ disease: { stroke: "#a6574b", fill: "#f4d8d2" }, task: { stroke: "#a67a2d", fill: "#f5e7bd" }, current: { stroke: "#497054", fill: "#dcebcf" }, earlier: { stroke: "#879783", fill: "#f3f5ed" } })[tone];
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
  expireManagerSession: (launchLogin?: boolean) => void;
}) {
  const [filters, setFilters] = useState<DirectoryFilters>(EMPTY_DIRECTORY_FILTERS);
  const [draftFilters, setDraftFilters] = useState<DirectoryFilters>(EMPTY_DIRECTORY_FILTERS);
  const [filtersReady, setFiltersReady] = useState(false);
  const [directoryPage, setDirectoryPage] = useState(0);
  const [directory, setDirectory] = useState<{ items: FarmDirectory; loading: boolean; error: string | null; stale: boolean; hasMore: boolean }>({
    items: [], loading: false, error: null, stale: false, hasMore: true,
  });
  const [panel, setPanel] = useState<ContextPanel | null>(null);
  const directoryRequest = useRef(0);
  const panelRequest = useRef(0);
  const directoryOpener = useRef<string | null>(null);
  const managerAccessWasEnabled = useRef(canOpenProfiles);
  const pendingManagerExpiryFocus = useRef(false);
  const initialFarmRequest = useRef<string | null>(null);
  const initialReportedFarmRequest = useRef<string | null>(null);
  const loadMoreRef = useRef<HTMLDivElement | null>(null);
  const nextPageRequested = useRef(false);

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
      if (filtersReady && accessResolved) setDirectory({ items: [], loading: false, error: null, stale: false, hasMore: false });
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
    setDirectory((current) => ({
      items: directoryPage === 0 && cached ? cached : current.items,
      loading: true,
      error: null,
      stale: Boolean(current.items.length),
      hasMore: current.hasMore,
    }));
    void readJson<FarmDirectory>("/api/v1/farms?" + params)
      .then(({ value }) => {
        if (request === directoryRequest.current) {
          nextPageRequested.current = false;
          setDirectory((current) => {
            const items = directoryPage ? [...current.items, ...value] : value;
            try { window.sessionStorage.setItem(cacheKey, JSON.stringify(value)); } catch { /* cache is optional */ }
            return { items, loading: false, error: null, stale: false, hasMore: value.length === FARM_DIRECTORY_PAGE_SIZE };
          });
        }
      })
      .catch((error: unknown) => {
        if (request !== directoryRequest.current) return;
        nextPageRequested.current = false;
        const message = profileReadError(error);
        if (requiresReauthentication(error)) expireManagerSession(requiresLaunchLogin(error));
        setDirectory((current) => ({ items: current.items, loading: false, error: current.items.length ? null : message, stale: Boolean(current.items.length), hasMore: false }));
      });
  }, [accessResolved, canOpenProfiles, directoryPage, expireManagerSession, filters, filtersReady]);

  useEffect(() => {
    const target = loadMoreRef.current;
    if (!target || directory.loading || !directory.hasMore || !canOpenProfiles) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) loadNextPage();
    }, { rootMargin: "480px" });
    observer.observe(target);
    return () => observer.disconnect();
  }, [canOpenProfiles, directory.hasMore, directory.loading]);

  function loadNextPage() {
    if (nextPageRequested.current || directory.loading || !directory.hasMore) return;
    nextPageRequested.current = true;
    setDirectoryPage((current) => current + 1);
  }

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
    const reauth = requiresReauthentication(error);
    if (reauth) expireManagerSession(requiresLaunchLogin(error));
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

  const canLoadMore = directory.hasMore;
  return <section className="directory-workspace farm-directory">
    <div className="directory-toolbar directory-toolbar-controls"><div className="directory-title"><h1>Farms</h1><span>{count(directory.items.length)} loaded</span></div><MultiFilter label="Status" values={filters.state} options={[["all", "All records"], ["reported", "Registrations to review"], ["reviewed", "Reviewed farms"]]} onChange={(state) => updateDirectoryFilters({ state })} /><MultiFilter label="Activity" values={filters.activity} options={[["all", "All activity"], ["open_tasks", "Open tasks"], ["updated_week", "Updated this week"], ["updated_month", "Updated this month"], ["no_recent_update", "No recent update"]]} onChange={(activity) => updateDirectoryFilters({ activity })} /><SortMenu value={filters.order} onChange={(order) => updateDirectoryFilters({ order })} options={[["open_tasks", "Open tasks"], ["recently_updated", "Recently updated"], ["least_updated", "Least updated"], ["name", "Name"]]} /><label className="directory-find"><span className="sr-only">Find farms</span><input type="search" maxLength={80} value={draftFilters.query} onChange={(event) => setDraftFilters((current) => ({ ...current, query: event.target.value }))} placeholder="Find farm, farmer, or village" /></label></div>
    {!accessResolved
      ? <DirectoryLoadingState label="Opening farms" />
      : !canOpenProfiles
      ? <EmptyState focusId={MANAGER_ACCESS_BOUNDARY_ID} title="Sign in to open farms" detail="Farm records are available to named Fortune admins." action={{ href: "/login?next=/farms", label: "Sign in" }} />
      : directory.loading && !directory.items.length
        ? <DirectoryLoadingState label="Updating farms" />
        : directory.items.length
          ? <><div className="farm-card-grid">{directory.items.map((farm) => farm.state === "reported"
            ? <button id={`reported-farm-directory-${farm.id}`} type="button" className="farm-directory-card directory-card-button compact-entity-card reported-candidate-card" key={farm.id} onClick={(event) => void openReportedFarm(farm.destination.id, event.currentTarget.id)}><span className="person-initial farm-initial">{farm.name.slice(0, 1).toUpperCase()}</span><div className="farm-card-summary"><p className="entity-card-type">Farm to review</p><h3>{farm.name}</h3><p className="farm-card-context">{farm.reported_farmer_name}</p><div className="entity-card-metrics"><span><strong>{count(farm.reported_plot_count || undefined)}</strong> Plots</span><span className={farm.open_work_count ? "attention" : undefined}><strong>{count(farm.open_work_count)}</strong> Open Tasks</span></div><OperatingTags snapshot={farm.operating} limit={2} /><p className="entity-card-updated">{updatedAgo(farm.latest_update_at)}</p></div></button>
            : <button id={`farm-directory-${farm.id}`} type="button" className="farm-directory-card directory-card-button compact-entity-card" key={farm.id} onClick={(event) => void openFarm(farm.id, event.currentTarget.id)}><span className="person-initial farm-initial">{farm.name.slice(0, 1).toUpperCase()}</span><div className="farm-card-summary"><p className="entity-card-type">Reviewed farm</p><h3>{farm.name}</h3><p className="farm-card-context">{farm.crops.join(" · ") || "No active crop recorded"}</p><div className="entity-card-metrics"><span><strong>{farm.field_count ? count(farm.field_count) : "—"}</strong> {farm.field_count ? "Fields" : "Field setup pending"}</span><span className={farm.open_work_count ? "attention" : undefined}><strong>{count(farm.open_work_count)}</strong> Open Tasks</span></div><p className="entity-card-updated">{updatedAgo(farm.latest_update_at)}</p></div></button>)}</div>{canLoadMore ? <div className="directory-more" ref={loadMoreRef}><button className="quiet-button" type="button" onClick={loadNextPage} disabled={directory.loading}>{directory.loading ? "Loading farms…" : "Load more farms"}</button></div> : null}</>
        : directory.error
          ? <p className="profile-message profile-error" role="alert">{directory.error}</p>
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
        ? <p className="profile-message profile-error" role="alert">{panel.error} {panel.reauth ? <Link href="/login?next=/farms&reason=session-expired">Sign in again</Link> : null}</p>
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
          {record.now.fields.length ? record.now.fields.map((field) => <button id={`farm-field-${record.id}-${field.id}`} className="entity-chip entity-chip-link" type="button" key={field.id} onClick={(event) => openField(field.id, event.currentTarget.id)}>{field.name} <span aria-hidden="true">→</span></button>) : <span className="empty-copy">Field setup pending</span>}
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
  const farmerCount = farmers.length + sourceFarmers.length;
  return <section className="directory-workspace people-workspace">
    <div className="directory-toolbar people-toolbar"><div className="directory-title"><h1>Farmers</h1><span>{count(farmerCount)}</span></div></div>
    {!accessResolved ? <DirectoryLoadingState label="Opening farmers" /> : farmerCount ? <div className="farmer-directory-sections">
      {farmers.length ? <section><div className="surface-heading"><div><p className="eyebrow">Reviewed operating record</p><h2>Reviewed farmers</h2></div><span className="count-badge">{count(farmers.length)}</span></div><div className="people-list source-card-grid">{farmers.map((person) => <button id={`profile-reviewed-farmer-${person.id}`} type="button" className="person-row compact-entity-card" key={person.id} onClick={(event) => void openProfile(person.id, "farmer", "reviewed", event.currentTarget.id)}><span className="person-initial">{person.name.slice(0, 1).toUpperCase()}</span><div className="person-summary"><p className="entity-card-type">Reviewed farmer</p><h3>{person.name}</h3><div className="entity-card-metrics"><span><strong>{count(person.assignment_count)}</strong> Reviewed Farms</span></div></div></button>)}</div></section> : null}
      {sourceFarmers.length ? <section><div className="surface-heading"><div><p className="eyebrow">Field network</p><h2>Farmers</h2></div><span className="count-badge">{count(sourceFarmers.length)}</span></div><ReportedFarmers farmers={sourceFarmers} canOpenProfiles={canOpenProfiles} openProfile={openProfile} /></section> : null}
    </div> : <p className="empty-copy">No farmers yet.</p>}
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
  const [recorded, setRecorded] = useState<Array<"all" | "location" | "visit" | "photo" | "issue" | "crop">>(["all"]);
  const [activity, setActivity] = useState<FarmActivityFilter[]>(["all"]);
  const [order, setOrder] = useState<"open_tasks" | "recently_updated" | "least_updated" | "name">("open_tasks");
  const loadMoreRef = useRef<HTMLDivElement | null>(null);
  const nextPageRequested = useRef(false);
  const matched = farmers.filter((person) => `${person.name} ${personName(person.name)}`.toLowerCase().includes(query.trim().toLowerCase())
    && (work.includes("all") || work.includes("open_tasks") && person.open_work > 0 || work.includes("no_open_tasks") && person.open_work === 0)
    && matchesRecordedEvidence(person.operating, recorded)
    && matchesActivityFilters(person.latest_activity_at, person.open_work, activity));
  const ordered = [...matched].sort((left, right) => order === "name"
    ? personName(left.name).localeCompare(personName(right.name))
    : order === "recently_updated"
      ? activityTimestamp(right.latest_activity_at) - activityTimestamp(left.latest_activity_at) || personName(left.name).localeCompare(personName(right.name))
      : order === "least_updated"
        ? activityTimestamp(left.latest_activity_at) - activityTimestamp(right.latest_activity_at) || personName(left.name).localeCompare(personName(right.name))
        : right.open_work - left.open_work || activityTimestamp(right.latest_activity_at) - activityTimestamp(left.latest_activity_at) || personName(left.name).localeCompare(personName(right.name)));
  const visible = ordered.slice(0, visibleCount);
  function loadNextPage() {
    if (nextPageRequested.current || visible.length >= ordered.length) return;
    nextPageRequested.current = true;
    setVisibleCount((current) => current + 100);
  }
  useEffect(() => {
    nextPageRequested.current = false;
    const target = loadMoreRef.current;
    if (!target || visible.length >= ordered.length) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) loadNextPage();
    }, { rootMargin: "480px" });
    observer.observe(target);
    return () => observer.disconnect();
  }, [visible.length, ordered.length]);
  return <><div className="directory-secondary-toolbar directory-secondary-toolbar-filters"><MultiFilter label="Work" values={work} options={[["all", "All farmers"], ["open_tasks", "Open tasks"], ["no_open_tasks", "No open tasks"]]} onChange={(next) => { setWork(next); setVisibleCount(100); }} /><MultiFilter label="Recorded" values={recorded} options={[["all", "All records"], ["location", "Location"], ["visit", "Visit"], ["photo", "Photo"], ["issue", "Issue"], ["crop", "Crop"]]} onChange={(next) => { setRecorded(next); setVisibleCount(100); }} /><MultiFilter label="Activity" values={activity} options={[["all", "All activity"], ["updated_week", "Updated this week"], ["updated_month", "Updated this month"], ["no_recent_update", "No recent update"]]} onChange={(next) => { setActivity(next); setVisibleCount(100); }} /><SortMenu value={order} options={[["open_tasks", "Open tasks"], ["recently_updated", "Recently updated"], ["least_updated", "Least updated"], ["name", "Name"]]} onChange={(next) => { setOrder(next); setVisibleCount(100); }} /><label className="directory-find"><span className="sr-only">Find farmers</span><input type="search" value={query} onChange={(event) => { setQuery(event.target.value); setVisibleCount(100); }} placeholder="Find farmer" /></label></div><div className="people-list source-card-grid">{visible.map((person) => <button id={`profile-reported-farmer-${person.id}`} type="button" className="person-row compact-entity-card" key={person.id} onClick={(event) => void openProfile(person.id, "farmer", "reported", event.currentTarget.id)}><span className="person-initial">{personName(person.name).slice(0, 1).toUpperCase()}</span><div className="person-summary"><p className="person-code">{personCode(person.name)}</p><p className="entity-card-type">Reported farmer</p><h3>{personName(person.name)}</h3><div className="entity-card-metrics"><span><strong>{count(person.farm_candidates)}</strong> Reported registrations</span><span className={person.open_work ? "attention" : undefined}><strong>{count(person.open_work)}</strong> Open Tasks</span></div><OperatingTags snapshot={person.operating} limit={2} /><p className="entity-card-updated">{updatedAgo(person.latest_activity_at)}</p></div></button>)}</div>{visible.length < ordered.length ? <div className="directory-more" ref={loadMoreRef}><button type="button" className="quiet-button" onClick={loadNextPage}>Load more farmers</button></div> : null}</>;
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
      : <p className="profile-message profile-error" role="alert">{selection.error} {selection.reauth ? <Link href="/login?next=/farmers&reason=session-expired">Sign in again</Link> : null}</p>}
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
      <div><dt>Reported registrations</dt><dd>{count(profile.reported?.farm_candidates)}</dd></div>
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
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  async function createAgent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setMessage(null);
    try {
      const response = await fetch("/api/v1/agents", {
        method: "POST", credentials: "same-origin", headers: { "content-type": "application/json" },
        body: JSON.stringify({ instruction }),
      });
      const payload = await response.json().catch(() => null) as { detail?: string } | null;
      if (!response.ok) throw new Error(payload?.detail || "Your request could not be saved.");
      setInstruction(""); setMessage("Saved for review. It will not notify anyone until it is implemented and made live."); reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Your request could not be saved.");
    } finally { setBusy(false); }
  }

  return <section className="directory-workspace agents-workspace">
    <div className="directory-toolbar people-toolbar"><div className="directory-title"><h1>Agents</h1><span>{count(agents?.agents.length)} live</span></div></div>
    <div className="agent-list">
      {(agents?.agents || []).map((agent) => <article className="agent-row" key={agent.id}>
        <strong className="agent-count">{count(agent.count)}</strong>
        <AgentIcon id={agent.id} />
        <div><p className="agent-live"><i aria-hidden="true" />Live</p><h3>{agent.name}</h3><p>{agent.summary}</p></div>
        <Link href={agent.id === "disease-watch" ? "/farms?state=reported" : "/farmers"} className="text-link">Open <span aria-hidden="true">→</span></Link>
      </article>)}
      {!agents ? <DirectoryLoadingState label="Opening agents" /> : null}
    </div>
    <section className="agent-builder">
      <div><p className="eyebrow">Request an agent</p><h3>What should we watch?</h3><p>Write it plainly. We save it as-is for review, then make it live only when the data and rule are ready.</p></div>
      <form className="agent-command" onSubmit={createAgent}>
        <label className="sr-only" htmlFor="agent-command">Agent request</label>
        <input id="agent-command" value={instruction} onChange={(event) => setInstruction(event.target.value)} maxLength={500} minLength={8} placeholder="e.g. Tell me when a farm has no update for 14 days" required />
        <button className="primary-action" disabled={busy}>{busy ? "Saving…" : "Add to review"} <span aria-hidden="true">→</span></button>
      </form>
      {message ? <p className="form-error" role="status">{message}</p> : null}
      {agents?.custom_agents.length ? <div className="agent-review-list">{agents.custom_agents.map((agent) => <article className="agent-review-item" key={agent.id}><span>In review</span><p>{agent.instruction}</p></article>)}</div> : null}
    </section>
  </section>;
}

function AgentIcon({ id }: { id: string }) {
  if (id === "disease-watch") return <span className="agent-icon disease" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M5 18C5 9 10 4 19 4c0 9-5 14-14 14Z" /><path d="M7 16c3-3 6-5 10-7" /><circle cx="14.7" cy="8.6" r="1" /><circle cx="11.4" cy="12" r="1" /></svg></span>;
  if (id === "farmer-no-update-7d") return <span className="agent-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="7" /><path d="M12 8v4l2.8 1.8M6 5v3H3" /></svg></span>;
  return <span className="agent-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M6 19V8l6-4 6 4v11" /><path d="M9 19v-5h6v5M4 19h16" /></svg></span>;
}

function NotificationDropdown({ items, close }: { items: OperatingAgent[]; close: () => void }) {
  return <section id="notification-panel" className="notification-dropdown" aria-label="Notifications">
    <div className="menu-heading"><strong>Notifications</strong><span>{items.length ? `${items.length} active` : "All clear"}</span></div>
    {items.length ? <div className="notification-list">{items.map((item) => <Link href="/actions" key={item.id} onClick={close}>
      <AgentIcon id={item.id} />
      <span><strong>{item.name}</strong><small>{item.summary}</small></span>
      <b>{count(item.count)}</b>
    </Link>)}</div> : <p className="notification-empty">Nothing needs attention right now.</p>}
    <Link className="notification-footer" href="/actions" onClick={close}>Open agents <span aria-hidden="true">→</span></Link>
  </section>;
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

function SettingsView({ state, managerBusy, logout }: {
  state: State; managerBusy: boolean; logout: () => Promise<void>;
}) {
  const session = state.session;
  return <section className="directory-workspace settings-workspace">
    <div className="directory-toolbar people-toolbar"><div className="directory-title"><h1>Settings</h1></div></div>
    <section className="settings-account-card">
      <div><p className="eyebrow">Account</p><h2>Fortune Farms</h2><p>Private workspace</p></div>
      <div className="settings-account-actions"><span className="settings-session-status">Signed in</span><button className="quiet-button settings-logout" type="button" disabled={managerBusy} onClick={() => void logout()}>{managerBusy ? "Logging out…" : "Log out"}</button></div>
    </section>
    {session?.authenticated ? <div className="settings-options"><PasswordChanger /><AccountManager /></div> : null}
    <section className="settings-coming-soon" aria-disabled="true"><div><strong>WhatsApp updates</strong><em>Coming soon</em></div><span>Updates will appear here when they are ready.</span></section>
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
  const [open, setOpen] = useState(false);
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

  useEffect(() => {
    if (!open || accounts) return;
    void loadAccounts().catch((error: unknown) => setStatus(error instanceof Error ? error.message : "Accounts could not be read."));
  }, [accounts, loadAccounts, open]);

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

  return <details className="account-manager" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>Manage named sign-ins</summary>
    {open ? <><p className="surface-copy">Create access only for people you have confirmed.</p>
      <form className="account-form" onSubmit={submitAccount}>
        <label htmlFor="account-name">Name<input id="account-name" value={name} onChange={(event) => setName(event.target.value)} required /></label>
        <label htmlFor="account-id">Login ID<input id="account-id" value={loginId} onChange={(event) => setLoginId(event.target.value)} placeholder="e.g. ravi.grower" autoCapitalize="none" required /></label>
        <label htmlFor="account-role">Access<select id="account-role" value={role} onChange={(event) => setRole(event.target.value as PasswordIdentitySummary["access_role"])}><option value="field_worker">Field worker</option><option value="farmer">Farmer</option><option value="admin">Admin</option><option value="owner">Owner</option></select></label>
        <label htmlFor="account-password">Temporary password<input id="account-password" type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={12} required /></label>
        <button className="primary-action" disabled={busy}>{busy ? "Creating…" : "Create sign-in"} <span aria-hidden="true">→</span></button>
      </form>
      {status ? <p className="form-error" role="status">{status}</p> : null}
      {accounts ? <ul className="account-list">{accounts.map((account) => <li key={account.id}><span>{account.person_name}</span><span>{account.login_id}</span><span>{account.access_role.replaceAll("_", " ")}</span></li>)}</ul> : <p className="empty-copy">Reading named accounts…</p>}</> : null}
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
    <div className="map-loading-content"><span className="directory-loading-dot" aria-hidden="true" /><strong>{label}</strong><p>Loading saved field activity</p></div>
  </div>;
}

function actionLine(item: LedgerItem) {
  const when = item.due_at || item.observed_at;
  const timing = when ? ` · ${dateTime(when)} IST` : "";
  return `${item.status.replaceAll("_", " ")}${item.proof_required ? " · proof required" : ""}${timing}`;
}

function errorStatus(error: unknown) {
  return error instanceof Error ? (error as Error & { status?: number }).status : undefined;
}

function requiresLaunchLogin(error: unknown) {
  return errorStatus(error) === 401;
}

function requiresReauthentication(error: unknown) {
  const status = errorStatus(error);
  return status === 401 || status === 403;
}

function profileReadError(error: unknown) {
  const status = errorStatus(error);
  return status === 401
    ? "Your workspace sign-in has ended. Sign in again to continue."
    : status === 403
    ? "Manager access has ended. Sign in again to open this record."
    : status === 404
    ? "This profile is no longer available. Return to the list and refresh the operating record."
    : status && status >= 500
    ? "The record service is unavailable right now. Try again shortly."
    : "This profile could not be read. Check your connection and try again.";
}
