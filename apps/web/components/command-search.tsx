"use client";

import { useEffect, useMemo, useRef, useState } from "react";

/** A safe, already-cached operating record that can be opened from command search. */
export type CommandSearchItem = {
  id: string;
  kind: "farm" | "farmer" | "field_worker";
  name: string;
  detail: string;
  href: string;
};

/** Cache-first global search. It intentionally never asks the network while a person types. */
export function CommandSearch({ items, close, refresh }: {
  items: CommandSearchItem[];
  close: () => void;
  refresh: () => void;
}) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const needle = query.trim().toLowerCase();
  const results = useMemo(() => {
    if (!needle) return [];
    return items.filter((item) => [item.name, item.detail].join(" ").toLowerCase().includes(needle)).slice(0, 12);
  }, [items, needle]);
  useEffect(() => { inputRef.current?.focus(); }, []);
  useEffect(() => { setActiveIndex(0); }, [query]);
  function move(result: CommandSearchItem) { window.location.assign(result.href); }
  return <div className="global-search-backdrop" role="presentation" onMouseDown={close}>
    <section className="global-search" role="dialog" aria-modal="true" aria-label="Search operating records" onMouseDown={(event) => event.stopPropagation()}>
      <div className="global-search-input"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.8" cy="10.8" r="6.8" /><path d="m16 16 4.2 4.2" /></svg><input ref={inputRef} value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Escape") { event.preventDefault(); close(); } if (event.key === "ArrowDown" && results.length) { event.preventDefault(); setActiveIndex((current) => Math.min(current + 1, results.length - 1)); } if (event.key === "ArrowUp" && results.length) { event.preventDefault(); setActiveIndex((current) => Math.max(current - 1, 0)); } if (event.key === "Enter" && results[activeIndex]) { event.preventDefault(); move(results[activeIndex]); } }} placeholder="Search farms, farmers, workers…" /></div>
      {needle ? <div className="global-search-results">{results.length ? results.map((result, index) => <button type="button" className={index === activeIndex ? "active" : ""} key={`${result.kind}:${result.id}`} onMouseEnter={() => setActiveIndex(index)} onClick={() => move(result)}><span className="global-search-kind">{result.kind === "field_worker" ? "Worker" : result.kind}</span><strong>{result.name}</strong><small>{result.detail}</small></button>) : <p className="empty-copy">No saved record matches that search.</p>}</div> : <div className="global-search-empty"><span>⌘F</span><p>Search is instant because it uses the operating record already on this device.</p></div>}
      <footer><button type="button" onClick={refresh}>Refresh now</button><span>↑↓ move · Enter open · Esc close</span></footer>
    </section>
  </div>;
}
