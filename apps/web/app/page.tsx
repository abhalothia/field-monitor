import Link from "next/link";

export default function LandingPage() {
  return (
    <main className="landing-shell">
      <nav className="landing-nav" aria-label="Primary">
        <span className="brand-mark"><i aria-hidden="true" /> Fortune Farms</span>
        <Link href="/login" className="text-link">Private access <span aria-hidden="true">→</span></Link>
      </nav>
      <section className="landing-hero">
        <p className="eyebrow">Fortune Farms · operating system</p>
        <h1>AGRO CEO</h1>
        <p>Know what changed.<br />Know who owns the next move.</p>
        <Link href="/login" className="primary-action">Open AGRO CEO <span aria-hidden="true">→</span></Link>
      </section>
      <footer className="landing-footer">Evidence begins in the field.</footer>
    </main>
  );
}
