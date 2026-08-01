from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _requirement_names(filename: str) -> set[str]:
    return {
        line.split("=", 1)[0].split("<", 1)[0].split(">", 1)[0].strip().lower()
        for line in (PROJECT_ROOT / filename).read_text().splitlines()
        if line.strip() and not line.startswith("#") and not line.startswith("-r ")
    }


def test_ffl_runtime_requirements_exclude_archived_heavy_packages():
    runtime = _requirement_names("requirements.txt")

    assert runtime == {"fastapi", "uvicorn", "httpx"}
    assert runtime.isdisjoint({"numpy", "pandas", "scipy", "streamlit", "plotly", "folium"})


def test_legacy_and_dev_requirements_keep_their_explicit_opt_ins():
    legacy_split_lines = (
        PROJECT_ROOT / "requirements-legacy.txt"
    ).read_text().splitlines()
    legacy_packages = _requirement_names("requirements-legacy.txt")
    dev_split_lines = (PROJECT_ROOT / "requirements-dev.txt").read_text().splitlines()
    dev_packages = _requirement_names("requirements-dev.txt")

    assert legacy_split_lines[0] == "-r requirements.txt"
    assert {"numpy", "pandas", "scipy", "streamlit", "plotly", "folium"} <= legacy_packages
    assert dev_split_lines[0] == "-r requirements.txt"
    assert {"pytest", "pytest-cov", "responses"} <= dev_packages
