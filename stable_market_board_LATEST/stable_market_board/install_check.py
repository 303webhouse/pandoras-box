"""Install check for Stable Market Board.

Verifies Python version, installed packages, .env file, universe.csv, and
tests the Polygon API key. Run with: python install_check.py

Designed to be friendly. Prints exactly what's wrong and how to fix it.
"""

from __future__ import annotations

import sys
from pathlib import Path


# ANSI colors (work on modern Windows terminals)
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


def ok(msg: str) -> None:
    print(f"  {GREEN}OK{RESET}  {msg}")


def fail(msg: str, fix: str = "") -> None:
    print(f"  {RED}FAIL{RESET}  {msg}")
    if fix:
        print(f"        {YELLOW}Fix:{RESET} {fix}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}WARN{RESET}  {msg}")


def section(title: str) -> None:
    print()
    print(f"{BOLD}{CYAN}{title}{RESET}")


def check_python_version() -> bool:
    section("[1/6] Python version")
    major, minor = sys.version_info[:2]
    version = f"{major}.{minor}.{sys.version_info.micro}"
    if major < 3 or (major == 3 and minor < 11):
        fail(
            f"Python {version} is too old (need 3.11 or newer)",
            "Install Python 3.11+ from python.org and re-run."
        )
        return False
    ok(f"Python {version}")
    return True


def check_dependencies() -> bool:
    section("[2/6] Python dependencies")
    required = [
        ("duckdb", "duckdb"),
        ("pandas", "pandas"),
        ("numpy", "numpy"),
        ("requests", "requests"),
        ("dotenv", "python-dotenv"),
        ("tenacity", "tenacity"),
        ("rich", "rich"),
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
    ]
    missing = []
    for import_name, install_name in required:
        try:
            __import__(import_name)
            ok(install_name)
        except ImportError:
            fail(f"{install_name} not installed")
            missing.append(install_name)

    if missing:
        print()
        fail(
            f"{len(missing)} packages missing",
            "Run: pip install -r requirements.txt"
        )
        return False
    return True


def check_env_file() -> tuple[bool, dict]:
    section("[3/6] .env file and API key")
    env_path = Path(".env")
    if not env_path.exists():
        fail(
            ".env file not found in project root",
            "Create .env per the README instructions, then re-run."
        )
        return False, {}

    # Parse .env manually so we don't depend on python-dotenv loading
    config = {}
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            config[key.strip()] = val.strip().strip('"').strip("'")

    api_key = config.get("POLYGON_API_KEY", "")
    if not api_key:
        fail(".env exists but POLYGON_API_KEY is missing or empty",
             "Add your Polygon API key to .env")
        return False, config
    if api_key in ("your_actual_polygon_key_here", "PASTE_YOUR_KEY_HERE", "fake", "test"):
        fail(".env has a placeholder API key, not the real one",
             "Replace the placeholder in .env with your actual Polygon API key")
        return False, config
    if len(api_key) < 20:
        warn(f"API key looks short ({len(api_key)} chars). Polygon keys are usually 32+ chars.")
    ok(f"POLYGON_API_KEY present ({len(api_key)} chars)")

    for key in ("HISTORY_YEARS", "DB_PATH", "UNIVERSE_PATH"):
        if key not in config:
            warn(f"{key} not in .env (will use default)")
        else:
            ok(f"{key}={config[key]}")

    return True, config


def check_universe() -> bool:
    section("[4/6] Universe file")
    path = Path("data/universe.csv")
    if not path.exists():
        fail("data/universe.csv missing",
             "This file ships with the project. Re-extract the zip.")
        return False

    try:
        with open(path) as f:
            lines = f.readlines()
    except Exception as e:
        fail(f"Could not read universe.csv: {e}")
        return False

    n_lines = len(lines)
    if n_lines < 50:
        fail(f"universe.csv has only {n_lines} lines - looks truncated or wrong",
             "Re-extract the zip.")
        return False

    header = lines[0].strip().lower()
    required_cols = {"ticker", "theme", "liquidity_tier"}
    if not all(col in header for col in required_cols):
        fail("universe.csv missing required columns",
             "Header should include: ticker, name, sector, industry, theme, subtheme, liquidity_tier")
        return False

    ok(f"universe.csv loaded ({n_lines - 1} tickers)")
    return True


def check_polygon_api(config: dict) -> bool:
    section("[5/6] Polygon API connectivity")
    api_key = config.get("POLYGON_API_KEY")
    if not api_key:
        warn("Skipping API test (no key)")
        return False

    try:
        import requests
    except ImportError:
        warn("Skipping API test (requests not installed)")
        return False

    # Hit Polygon with a known-good single-day single-ticker request
    url = (
        "https://api.polygon.io/v2/aggs/ticker/AAPL/range/1/day/"
        "2024-01-02/2024-01-03"
    )
    try:
        r = requests.get(url, params={"apiKey": api_key}, timeout=15)
    except requests.RequestException as e:
        fail(f"Could not reach Polygon: {e}",
             "Check your internet connection.")
        return False

    if r.status_code == 401:
        fail("Polygon returned 401 Unauthorized",
             "Your API key is wrong or your subscription is inactive. "
             "Check polygon.io/dashboard/keys and verify your Stocks Starter plan is active.")
        return False
    if r.status_code == 403:
        fail("Polygon returned 403 Forbidden",
             "Your subscription plan may not include this endpoint. "
             "Make sure you're on Stocks Starter or higher.")
        return False
    if r.status_code != 200:
        fail(f"Polygon returned HTTP {r.status_code}",
             f"Response: {r.text[:200]}")
        return False

    body = r.json()
    if body.get("resultsCount", 0) == 0:
        warn("Polygon returned no results for AAPL test. Strange but not necessarily broken.")
    else:
        ok(f"Polygon API responding (test returned {body['resultsCount']} bars for AAPL)")
    return True


def check_data_folder() -> bool:
    section("[6/6] Data folder writable")
    data_dir = Path("data")
    if not data_dir.exists():
        try:
            data_dir.mkdir(parents=True)
            ok("Created data/ folder")
        except Exception as e:
            fail(f"Could not create data/ folder: {e}",
                 "Check folder permissions.")
            return False

    # Try writing a probe file
    probe = data_dir / ".probe"
    try:
        probe.write_text("ok")
        probe.unlink()
        ok("data/ folder is writable")
        return True
    except Exception as e:
        fail(f"data/ folder is not writable: {e}",
             "Check folder permissions or pick a project location with write access.")
        return False


def main() -> int:
    print()
    print(f"{BOLD}{CYAN}Stable Market Board - Install Check{RESET}")
    print("=" * 60)

    results = []
    results.append(("Python", check_python_version()))
    if not results[-1][1]:
        # No point continuing without Python
        return 1
    results.append(("Dependencies", check_dependencies()))
    env_ok, config = check_env_file()
    results.append((".env", env_ok))
    results.append(("Universe", check_universe()))
    results.append(("Polygon API", check_polygon_api(config) if env_ok else False))
    results.append(("Data folder", check_data_folder()))

    print()
    print("=" * 60)
    print(f"{BOLD}Summary:{RESET}")
    n_pass = sum(1 for _, p in results if p)
    n_total = len(results)
    for name, passed in results:
        mark = f"{GREEN}OK{RESET}" if passed else f"{RED}FAIL{RESET}"
        print(f"  {mark}  {name}")
    print()
    if n_pass == n_total:
        print(f"{GREEN}{BOLD}All checks passed.{RESET} You're ready to run:")
        print()
        print(f"  python -m stable.ingest    {YELLOW}# first time, ~5 min{RESET}")
        print(f"  python -m stable.metrics   {YELLOW}# ~30 sec{RESET}")
        print(f"  python -m stable.server    {YELLOW}# opens dashboard on localhost:8000{RESET}")
        print()
        return 0
    else:
        print(f"{RED}{BOLD}{n_total - n_pass} check(s) failed.{RESET} Fix the issues above, then re-run install_check.py")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
