from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_next_manager_entry_retains_the_full_legacy_farm_truth_surface():
    config = (ROOT / "apps/web/next.config.ts").read_text(encoding="utf-8")
    command_centre = (ROOT / "apps/web/components/command-centre.tsx").read_text(
        encoding="utf-8"
    )

    redirects = config.split("async redirects()", 1)[1].split("async rewrites()", 1)[0]
    rewrites = config.split("async rewrites()", 1)[1]
    assert 'source: "/manager"' not in redirects
    assert '{ source: "/manager", destination: `${apiOrigin}/manager` }' in rewrites
    assert '{ source: "/assets/manager.css", destination: `${apiOrigin}/assets/manager.css` }' in rewrites
    assert '{ source: "/assets/manager.js", destination: `${apiOrigin}/assets/manager.js` }' in rewrites

    # The old header-level Farm Truth control was deliberately removed from the
    # operating workspace. The deep review links remain available where a
    # record actually needs review, without reintroducing obsolete UI copy.
    assert 'farmTruth: "Farm Truth"' not in command_centre
    assert 'farmTruth: "खेत सत्य"' not in command_centre
    assert 'href="/manager"' in command_centre
    assert 'href="/manager?review=farm-truth"' in command_centre
    assert "state.session?.authenticated" in command_centre
