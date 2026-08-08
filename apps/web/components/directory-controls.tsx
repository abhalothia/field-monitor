"use client";

/** Shared, URL-backed controls for the operating directories. */
export type FarmStateFilter = "all" | "reviewed" | "reported";
export type FarmActivityFilter = "all" | "open_tasks" | "disease_reported" | "updated_week" | "updated_month" | "no_recent_update";
export type FarmOrder = "open_tasks" | "recently_updated" | "least_updated" | "name";

function toggleFilterValue<T extends string>(values: T[], next: T): T[] {
  if (next === "all") return [next];
  const selected = new Set(values.filter((value) => value !== "all"));
  if (selected.has(next)) selected.delete(next); else selected.add(next);
  return selected.size ? [...selected] : ["all" as T];
}

/** A compact multi-select that avoids browser-native select styling. */
export function MultiFilter<T extends string>({ label, values, options, onChange }: {
  label: string;
  values: T[];
  options: ReadonlyArray<readonly [T, string]>;
  onChange: (values: T[]) => void;
}) {
  const all = values.includes("all" as T);
  const selectedLabel = all ? options[0]?.[1] || "All" : `${values.length} selected`;
  return <details className="filter-menu"><summary><span>{label}</span><strong>{selectedLabel}</strong></summary><div className="filter-menu-options">{options.map(([value, title]) => <label key={value}><input type="checkbox" checked={value === "all" ? all : values.includes(value)} onChange={() => onChange(toggleFilterValue(values, value))} /><span>{title}</span></label>)}</div></details>;
}

/** A matching sort menu; selection closes the popover immediately. */
export function SortMenu<T extends string>({ value, options, onChange }: {
  value: T;
  options: ReadonlyArray<readonly [T, string]>;
  onChange: (value: T) => void;
}) {
  const selectedLabel = options.find(([option]) => option === value)?.[1] || "Sort";
  return <details className="filter-menu sort-menu"><summary><span>Sort</span><strong>{selectedLabel}</strong></summary><div className="filter-menu-options">{options.map(([option, title]) => <button type="button" className={option === value ? "active" : ""} key={option} onClick={(event) => { onChange(option); event.currentTarget.closest("details")?.removeAttribute("open"); }}>{title}{option === value ? <span aria-hidden="true">✓</span> : null}</button>)}</div></details>;
}
