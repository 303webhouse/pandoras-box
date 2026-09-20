"""R-IV.465(f) -- reading a sensitive document uses a field parser, not a mask.

FAIL-FIRST against the pre-R-IV.465 practice: the document was read whole (grep, or a PDF dump)
and what the reader had not anticipated reached the transcript -- a live credential line
(SECURITY-DEFERRED S13) and a name with an identifier (R-IV.465(f)). The fixture below puts both
kinds of thing beside the figures being read, and the test is that they never come back.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))

from read_pdf_fields import extract_fields, main, parse_field  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]

PAGES = ["""
    BROKERAGE STATEMENT                     Prepared for NICK HERTZOG
    Account 123-456789          SSN ***-**-1234        Advisor: Jane Rivera (555) 010-9988
    Total Account Value      $12,217.86
    Cash Available to Trade  $1,043.05
    Confirmation Number      26259-MCQGWD
    Trade Date  07/17/2026     Settlement Date 07/21/2026
    Notes: client called about the transfer; see attached correspondence.
""", """
    Total Account Value      $12,940.11
    Confirmation Number      31007-KKQPLX
    Margin Interest Rate     8.25 %
"""]

FIELDS = [("Total Account Value", "money"), ("Confirmation Number", "ref"),
          ("Trade Date", "date"), ("Margin Interest Rate", "percent")]


def test_every_whitelisted_figure_is_reproduced_in_document_order():
    rows = extract_fields(PAGES, FIELDS)
    got = [(r["field"], r["page"], r["value"]) for r in rows]
    assert ("Total Account Value", 1, "$12,217.86") in got
    assert ("Total Account Value", 2, "$12,940.11") in got
    assert ("Confirmation Number", 1, "26259-MCQGWD") in got
    assert ("Confirmation Number", 2, "31007-KKQPLX") in got
    assert ("Trade Date", 1, "07/17/2026") in got
    assert ("Margin Interest Rate", 2, "8.25 %") in got


def test_nothing_that_was_not_asked_for_comes_back(capsys):
    rows = extract_fields(PAGES, FIELDS)
    blob = json.dumps(rows)
    for secret in ("NICK", "HERTZOG", "123-456789", "1234", "Jane", "Rivera", "555",
                   "correspondence", "SSN", "Advisor"):
        assert secret not in blob, f"{secret!r} reached the output"


def test_the_printed_form_carries_the_same_discipline(capsys):
    from read_pdf_fields import _emit
    _emit(extract_fields(PAGES, FIELDS), as_json=False)
    printed = capsys.readouterr().out
    assert "$12,217.86" in printed and "26259-MCQGWD" in printed
    for secret in ("NICK", "HERTZOG", "123-456789", "Jane", "Advisor", "correspondence"):
        assert secret not in printed


def test_a_label_that_is_not_whitelisted_is_never_read():
    rows = extract_fields(PAGES, [("Total Account Value", "money")])
    assert {r["field"] for r in rows} == {"Total Account Value"}


def test_a_value_that_is_not_of_the_declared_type_is_reported_absent_not_returned():
    rows = extract_fields(["Advisor: Jane Rivera (555) 010-9988\nNotes: none"],
                          [("Advisor", "money")])
    assert rows[0]["value"] is None and "no money value" in rows[0]["note"]


def test_a_label_that_does_not_occur_says_so():
    rows = extract_fields(PAGES, [("Dividend Total", "money")])
    assert rows[0]["value"] is None and rows[0]["note"].startswith("ABSENT")


def test_a_field_must_declare_its_type():
    assert parse_field("Total Value::money") == ("Total Value", "money")
    for bad in ("Total Value", "Total Value::text", "::money"):
        with pytest.raises(ValueError):
            parse_field(bad)


def test_no_path_in_the_reader_prints_the_document():
    src = (ROOT / "scripts" / "read_pdf_fields.py").read_text(encoding="utf-8")
    # two in the one emitter (json and line form), two refusals to stderr that print no
    # document content -- and nothing else anywhere.
    assert src.count("print(") == 4
    assert src.count("file=sys.stderr") == 2
    assert "print(text" not in src and "--raw" not in src and "--dump" not in src


def test_naming_no_fields_refuses_rather_than_reading_everything(tmp_path, capsys):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    assert main([str(pdf)]) == 2
    assert "only fields you whitelist" in capsys.readouterr().err


def test_it_runs_as_a_script_end_to_end(tmp_path):
    """The reader is a script the lanes run, so it is tested as one -- through pypdf, on a real
    PDF written for this test."""
    pypdf = pytest.importorskip("pypdf")
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    out = tmp_path / "empty.pdf"
    with open(out, "wb") as fh:
        writer.write(fh)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "read_pdf_fields.py"), str(out),
         "--field", "Total Account Value::money"],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert "Total Account Value [money] -: ABSENT" in proc.stdout
    assert proc.stdout.count("\n") == 1, "one line per whitelisted field, and nothing else"
