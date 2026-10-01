"""The secret scan — R-IV.605(d)4.

Two tracked files carried a production database URL with its password, and one carried a Discord
webhook token, in a repo public for a week. **GitHub's own push protection stopped neither.** So
these tests exist to keep this repo's own control honest, and the first of them is that the
scanner can still fail.
"""

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import secret_scan as ss  # noqa: E402


# ── the shapes that actually leaked here ──────────────────────────────────────────────────

@pytest.mark.parametrize("line,label", [
    ('db = "postgresql://user:hunter2hunter2hunter2@h:5432/d"', "database URL"),
    ('u = "postgres://postgres:sioMAUjhdgNYWwZMZbkbcSya@trolley.proxy.rlwy.net:25012/railway"',
     "the exact shape that leaked"),
    ('h = "https://discord.com/api/webhooks/123456789012345678/'
     'abcdefghijklmnopqrstuvwxyz0123456789"', "Discord webhook"),
    ('curl -H "X-API-Key: abcdefghijklmnopqrstuvwxyz0123456789ABC"', "a curl header"),
    ('    "password": "sioMAUjhdgNYWwZMZbkbcSyaAcwdJMty",', "a QUOTED key"),
    ('API_KEY = "abcdefghijklmnopqrstuvwxyz0123456789ABC"', "a bare assignment"),
    ('key = "AKIAZZ7TQ4MNBVCXQWER"', "an AWS id"),
    ('t = "ghp_abcdefghijklmnopqrstuvwxyz01"', "a GitHub token"),
    ('x = "xoxb-1234567890-abcdefghij"', "a Slack token"),
    ('-----BEGIN RSA PRIVATE KEY-----', "a private key block"),
])
def test_it_refuses_what_has_actually_leaked(line, label):
    assert ss.scan_text(line), label


def test_the_quoted_key_gap_that_hid_ten_scripts(self=None):
    """`"password": "value"` has a quote BETWEEN the name and the colon, so a pattern requiring
    `name\\s*[:=]` never matched it. Ten migration scripts went unreported on the first run
    because of exactly that, and were only found by hashing against known-dead values."""
    assert ss.scan_text('    "password": "sioMAUjhdgNYWwZMZbkbcSyaAcwdJMty",')
    assert ss.scan_text("  'api_key': 'abcdefghijklmnopqrstuvwxyz0123456789',")


# ── what it must NOT cry wolf on ──────────────────────────────────────────────────────────
#
# A scanner that cries wolf gets bypassed, and a bypassed scanner is worse than none.

@pytest.mark.parametrize("line,why", [
    ('redis_url = f"rediss://default:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"',
     "an f-string template"),
    ('return f"postgresql://{user}:{pw}@{host}:{port}/{name}"', "a DSN built from variables"),
    ('return "postgresql://%s:%s@%s:%s/%s" % (u, p, h, po, n)', "percent formatting"),
    ('token = _extract_bearer_from_scope(scope)', "a function CALL, not a value"),
    ('password = os.getenv("DB_PASSWORD")', "an environment read"),
    ('db = "postgresql://<user>:<REDACTED>@<host>:<port>/<db>"', "a redacted placeholder"),
    ('key = "AKIAIOSFODNN7EXAMPLE"', "the canonical AWS EXAMPLE key — documentation"),
    ('api_key = "your-api-key-here-goes-something"', "a your- placeholder"),
    ('api_key = "${PIVOT_API_KEY}"', "a shell interpolation"),
    ('secret = "{{ vault_password }}"', "a template variable"),
    ('sha = "a3f5c1e9b7d2486fa0c4e8b1d9376254af0b2c8e"', "a git sha — no secret-shaped name"),
])
def test_it_stays_quiet_on_what_is_not_a_credential(line, why):
    assert not ss.scan_text(line), why


# ── the exemption must cost something ─────────────────────────────────────────────────────

def test_an_allow_marker_needs_a_reason():
    """An exemption nobody justified is how six ungated routes stayed hidden for months."""
    leak = 'API_KEY = "abcdefghijklmnopqrstuvwxyz0123456789ABC"'
    assert ss.scan_text(leak)
    assert not ss.scan_text(leak + "  # secret-scan: allow a documented test fixture")
    # A BARE marker does not excuse it — the regex requires text after `allow`.
    assert ss.scan_text(leak + "  # secret-scan: allow")
    assert ss.scan_text(leak + "  # secret-scan: allow   ")


# ── the scanner must be able to fail ──────────────────────────────────────────────────────

def test_the_planted_fake_is_refused_end_to_end(tmp_path):
    """A scan that cannot fail is a scan that passes. CI plants this same fake on every run."""
    p = tmp_path / "planted.py"
    p.write_text('DSN = "postgresql://u:hunter2hunter2hunter2@h:5432/d"\n', encoding="utf-8")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "secret_scan.py"),
                        "--path", str(p)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "database URL with an inline password" in r.stdout


def test_it_never_prints_the_value_it_found(tmp_path):
    """A scanner that echoes the secret has copied it into a terminal history, a CI transcript
    and a log. The path and the SHAPE are enough to fix it."""
    needle = "hunter2hunter2hunter2"
    p = tmp_path / "planted.py"
    p.write_text('DSN = "postgresql://u:%s@h:5432/d"\n' % needle, encoding="utf-8")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "secret_scan.py"),
                        "--path", str(p)], capture_output=True, text=True, cwd=ROOT)
    assert needle not in r.stdout
    assert needle not in r.stderr


def test_the_repo_is_clean_right_now():
    """The regression guard. If this fails, something credential-shaped was committed."""
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "secret_scan.py"), "--all"],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout


# ── it must scan what is being committed, not what is on disk ─────────────────────────────

def test_the_hook_scans_the_staged_blob():
    """Scanning the working tree while committing the index is how a scanner passes on content
    that is not what is being committed."""
    import inspect
    src = inspect.getsource(ss._content)
    assert 'git", "show", ":"' in src or "git\", \"show\", \":\"" in src

    hook = os.path.join(ROOT, "scripts", "install_git_hooks.py")
    text = open(hook, encoding="utf-8").read()
    assert "--staged" in text
    assert "pre-commit" in text


def test_ci_runs_with_no_path_filter():
    """A path filter is how a credential in a file nobody listed slips through."""
    wf = open(os.path.join(ROOT, ".github", "workflows", "secret-scan.yml"),
              encoding="utf-8").read()
    assert "--all" in wf
    assert "paths:" not in wf
    # ...and CI proves the scanner can still fail, on every run.
    assert "planted" in wf
