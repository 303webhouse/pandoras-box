"""The rejection line carries the discriminator, never the value (R-IV.331(a))."""

import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "webhooks" / "pythia_events.py"


def test_rejection_logs_length_and_presence():
    t = SRC.read_text(encoding="utf-8")
    assert "secret_len=%d present=%s" in t
    assert "len(supplied), bool(supplied)" in t


def test_rejection_never_logs_the_value():
    """The one assertion that matters. `supplied` must never reach a log call as a
    value — only len() and bool() of it."""
    t = SRC.read_text(encoding="utf-8")
    for line in t.split("\n"):
        s = line.strip()
        if s.startswith("#"):
            continue
        if "supplied" in s and ("logger." in s or "%s" in s):
            assert "len(supplied)" in s or "bool(supplied)" in s, s
        # never interpolated bare
        assert "%s\" % supplied" not in s
        assert "{supplied}" not in s
