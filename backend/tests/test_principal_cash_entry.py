"""R-IV.546(a) — the principal's two cash inputs, at the HTTP boundary.

He types these on the page, so the tests are about what the page can and cannot get
away with: auth, validation, and the refusals. Convention #30 throughout — every
refusal is paired with a request that must SUCCEED, because a route that 400s on
everything would pass every negative test and accept no deposit at all.
"""

import uuid

import pytest

ENTRY = "/api/portfolio/cash-entry"
REANCHOR = "/api/portfolio/cash-reanchor"


def key():
    return str(uuid.uuid4())


def entry_body(**kw):
    return dict({"account_name": "FIDELITY_ROTH", "kind": "DEPOSIT", "amount": 88.15,
                 "event_date": "2026-09-24", "idempotency_key": key(),
                 "note": "auto deposit"}, **kw)


def reanchor_body(**kw):
    return dict({"account_name": "ROBINHOOD", "cash": 439.39,
                 "as_of": "2026-09-24T14:30:00-04:00", "idempotency_key": key(),
                 "note": "what the app shows"}, **kw)


def hdr(test_api_key):
    return {"X-API-Key": test_api_key}


# -- auth ---------------------------------------------------------------------

@pytest.mark.parametrize("path,body", [(ENTRY, entry_body()), (REANCHOR, reanchor_body())])
def test_no_credential_is_refused(client, path, body):
    assert client.post(path, json=body).status_code == 401


@pytest.mark.parametrize("path,body", [(ENTRY, entry_body()), (REANCHOR, reanchor_body())])
def test_a_wrong_key_is_refused(client, path, body):
    r = client.post(path, json=body, headers={"X-API-Key": "not-the-key"})
    assert r.status_code == 401


@pytest.mark.parametrize("path,body", [(ENTRY, entry_body()), (REANCHOR, reanchor_body())])
def test_the_right_key_is_accepted(client, test_api_key, path, body):
    """POSITIVE CONTROL. Without this the 401 tests above would pass on a route that
    refuses everyone."""
    r = client.post(path, json=body, headers=hdr(test_api_key))
    assert r.status_code == 200, r.text


# -- the session cookie, which is how the principal actually arrives ----------

@pytest.fixture
def session_cookie(monkeypatch):
    """A real signed cookie, minted the way the dashboard mints one.

    The secret is monkeypatched ON THE MODULE, not reloaded into it. Reloading
    `utils.session` and `utils.pivot_auth` worked in isolation and silently broke
    other files under random ordering: the reload rebinds `require_api_key` to a new
    function object while the FastAPI app still holds the old one, so the app and the
    module drift apart for the rest of the session. Caught by running these tests
    beside their neighbours -- 69 passing alone, 24 failing together.
    """
    import utils.session as session

    monkeypatch.setattr(session, "SESSION_SECRET",
                        "test-session-secret-for-cash-entry")
    token = session.issue_session("test")
    assert token, "the session helper produced no cookie"
    return session.COOKIE_NAME, token


def test_a_session_mutation_without_the_csrf_header_is_refused(client, session_cookie):
    """`require_api_key`'s own rule, not a new one: a session-authed mutation must
    carry X-Requested-With. The form has to send it, which is why it is in the relay."""
    name, token = session_cookie
    client.cookies.set(name, token)
    try:
        r = client.post(ENTRY, json=entry_body())
        assert r.status_code == 403
        assert "CSRF" in r.text
    finally:
        client.cookies.clear()


def test_a_session_mutation_with_the_csrf_header_is_accepted(client, session_cookie):
    """POSITIVE CONTROL for the cookie path — the principal's actual route in."""
    name, token = session_cookie
    client.cookies.set(name, token)
    try:
        r = client.post(ENTRY, json=entry_body(),
                        headers={"X-Requested-With": "XMLHttpRequest"})
        assert r.status_code == 200, r.text
    finally:
        client.cookies.clear()


# -- validation: the entry ----------------------------------------------------

@pytest.mark.parametrize("kind", ["", "TRANSFER", "gift", "ANCHOR", "DIVIDEND"])
def test_an_unknown_kind_is_refused(client, test_api_key, kind):
    r = client.post(ENTRY, json=entry_body(kind=kind), headers=hdr(test_api_key))
    assert r.status_code == 400
    assert "DEPOSIT, WITHDRAWAL or OTHER" in r.text


@pytest.mark.parametrize("kind", ["DEPOSIT", "deposit", "WithDrawal", "other"])
def test_the_three_kinds_are_accepted_in_any_case(client, test_api_key, kind):
    """POSITIVE CONTROL for the kind check."""
    amount = -10.0 if kind.upper() == "WITHDRAWAL" else 10.0
    r = client.post(ENTRY, json=entry_body(kind=kind, amount=amount),
                    headers=hdr(test_api_key))
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == kind.upper()


@pytest.mark.parametrize("missing", ["", "   ", None])
def test_an_entry_without_an_idempotency_key_is_refused(client, test_api_key, missing):
    """Without one a double-click books the deposit twice, and only the client knows
    the two clicks were one intent."""
    body = entry_body()
    body["idempotency_key"] = missing if missing is not None else ""
    r = client.post(ENTRY, json=body, headers=hdr(test_api_key))
    assert r.status_code == 400
    assert "idempotency_key is required" in r.text


def test_a_zero_amount_is_refused(client, test_api_key):
    r = client.post(ENTRY, json=entry_body(amount=0), headers=hdr(test_api_key))
    assert r.status_code == 400


def test_a_deposit_may_not_be_negative(client, test_api_key):
    """A DEPOSIT of -88.15 is two statements contradicting each other. Guessing which
    the principal meant is how money goes missing in the direction nobody checks."""
    r = client.post(ENTRY, json=entry_body(kind="DEPOSIT", amount=-88.15),
                    headers=hdr(test_api_key))
    assert r.status_code == 400
    assert "a DEPOSIT is positive" in r.text


def test_a_withdrawal_may_not_be_positive(client, test_api_key):
    r = client.post(ENTRY, json=entry_body(kind="WITHDRAWAL", amount=50.0),
                    headers=hdr(test_api_key))
    assert r.status_code == 400
    assert "a WITHDRAWAL is negative" in r.text


@pytest.mark.parametrize("amount", [25.0, -25.0])
def test_other_takes_either_sign(client, test_api_key, amount):
    """POSITIVE CONTROL for the sign rule: it constrains the two kinds that have a
    direction and lets the one that does not through."""
    r = client.post(ENTRY, json=entry_body(kind="OTHER", amount=amount),
                    headers=hdr(test_api_key))
    assert r.status_code == 200, r.text
    assert r.json()["ledger_type"] == "OTHER"


@pytest.mark.parametrize("bad", ["", "24/09/2026", "yesterday", "2026-13-01"])
def test_a_malformed_event_date_is_refused(client, test_api_key, bad):
    r = client.post(ENTRY, json=entry_body(event_date=bad), headers=hdr(test_api_key))
    assert r.status_code == 400
    assert "ISO date" in r.text


def test_the_entry_records_the_actor_and_the_ledger_type(client, test_api_key):
    r = client.post(ENTRY, json=entry_body(), headers=hdr(test_api_key))
    out = r.json()
    assert out["actor"] == "principal"
    assert out["ledger_type"] == "TRANSFER_IN"
    assert out["event_date"] == "2026-09-24"


# -- validation: the re-anchor ------------------------------------------------

def test_a_reanchor_without_an_idempotency_key_is_refused(client, test_api_key):
    r = client.post(REANCHOR, json=reanchor_body(idempotency_key="  "),
                    headers=hdr(test_api_key))
    assert r.status_code == 400
    assert "two anchors" in r.text


@pytest.mark.parametrize("bad", ["now", "14:30", "24-09-2026T10:00"])
def test_a_reanchor_with_an_unparseable_instant_is_refused(client, test_api_key, bad):
    r = client.post(REANCHOR, json=reanchor_body(as_of=bad), headers=hdr(test_api_key))
    assert r.status_code == 400
    assert "ISO instant" in r.text


def test_a_bare_date_is_refused_as_an_anchor_instant(client, test_api_key):
    """fromisoformat("2026-09-24") succeeds and hands back MIDNIGHT. Every event that
    same day would then count as after the anchor, including the ones already inside
    the broker's figure -- a double-count nobody asked for."""
    r = client.post(REANCHOR, json=reanchor_body(as_of="2026-09-24"),
                    headers=hdr(test_api_key))
    assert r.status_code == 400
    assert "bare date" in r.text
    # POSITIVE CONTROL: the same day WITH a time is fine.
    ok = client.post(REANCHOR, json=reanchor_body(as_of="2026-09-24T14:30:00-04:00"),
                     headers=hdr(test_api_key))
    assert ok.status_code == 200, ok.text


def test_a_reanchor_without_as_of_defaults_to_now(client, test_api_key):
    """POSITIVE CONTROL: the field is optional, and omitting it is not a refusal."""
    body = reanchor_body()
    body.pop("as_of")
    r = client.post(REANCHOR, json=body, headers=hdr(test_api_key))
    assert r.status_code == 200, r.text
    assert r.json()["as_of"]


def test_the_reanchor_names_the_principal_entry_as_its_evidence(client, test_api_key):
    """R-IV.546(a)2. There is no file here, so the reference says so plainly rather
    than borrowing the shape of a hash it does not have."""
    r = client.post(REANCHOR, json=reanchor_body(), headers=hdr(test_api_key))
    out = r.json()
    assert out["evidence_ref"].startswith("principal-entry@")
    assert "2026-09-24T14:30:00-04:00" in out["evidence_ref"]
    assert out["actor"] == "principal"


def test_the_reanchor_reports_the_difference_rather_than_absorbing_it(client, test_api_key):
    """The difference IS the product: it is what the periodic CSV cleanup goes
    looking for. Absorbing it silently would make a re-anchor a way of hiding the
    drift it exists to surface."""
    r = client.post(REANCHOR, json=reanchor_body(), headers=hdr(test_api_key))
    out = r.json()
    assert "difference" in out and "derived_before" in out
    assert out["difference_note"]


def test_a_first_anchor_reports_no_difference_rather_than_zero(client, test_api_key):
    """Robinhood's first anchor (R-IV.546(c)) has nothing to differ FROM. Zero would
    claim the hub and the broker agreed, which is a different statement entirely."""
    r = client.post(REANCHOR, json=reanchor_body(), headers=hdr(test_api_key))
    out = r.json()
    assert out["derived_before"] is None
    assert out["difference"] is None
    assert "first anchor, not a correction" in out["difference_note"]


def test_the_reanchor_touches_no_stored_balance(client, test_api_key):
    r = client.post(REANCHOR, json=reanchor_body(), headers=hdr(test_api_key))
    assert r.json()["stored_balance_untouched"] is True


# -- R-IV.548(c): the evidence-backed ledger event ---------------------------
#
# POSITIONS had to write the Roth's six events by audited SQL, because no route took
# a dated event with a source_ref. A lane reaching for raw SQL to record money is the
# signal that the route it needed does not exist.

EVENT = "/api/portfolio/cash-event"


def event_body(**kw):
    return dict({"account_name": "FIDELITY_ROTH", "event_type": "TRANSFER_IN",
                 "amount": 88.15, "event_date": "2026-08-31",
                 "source_ref": "74436e3c08a3", "actor": "CC-POSITIONS",
                 "note": "TRANSFERRED FROM TO BROKERAGE OPTION"}, **kw)


def test_the_evidence_route_needs_a_credential(client):
    assert client.post(EVENT, json=event_body()).status_code == 401


def test_the_evidence_route_accepts_a_typed_dated_sourced_event(client, test_api_key):
    """POSITIVE CONTROL for everything below."""
    r = client.post(EVENT, json=event_body(), headers=hdr(test_api_key))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["event_type"] == "TRANSFER_IN"
    assert out["source_ref"] == "74436e3c08a3"
    assert out["actor"] == "CC-POSITIONS"
    assert out["stored_balance_untouched"] is True


@pytest.mark.parametrize("ref", ["", "   "])
def test_an_event_without_a_source_ref_is_refused(client, test_api_key, ref):
    """It names the document it was read out of, or it is not evidence."""
    r = client.post(EVENT, json=event_body(source_ref=ref), headers=hdr(test_api_key))
    assert r.status_code == 400
    assert "source_ref is required" in r.text


@pytest.mark.parametrize("actor", ["", " "])
def test_an_event_with_no_actor_is_refused(client, test_api_key, actor):
    """A movement recorded by nobody cannot be asked about later."""
    r = client.post(EVENT, json=event_body(actor=actor), headers=hdr(test_api_key))
    assert r.status_code == 400
    assert "actor is required" in r.text


def test_an_opening_balance_may_not_be_written_here(client, test_api_key):
    """An anchor has its own evidence rules and its own two routes."""
    r = client.post(EVENT, json=event_body(event_type="OPENING_BALANCE"),
                    headers=hdr(test_api_key))
    assert r.status_code == 400
    assert "/cash-anchor" in r.text


@pytest.mark.parametrize("bad", ["", "GIFT", "REBATE", "deposit-ish"])
def test_an_event_type_outside_the_vocabulary_is_refused(client, test_api_key, bad):
    r = client.post(EVENT, json=event_body(event_type=bad), headers=hdr(test_api_key))
    assert r.status_code == 400
    assert "event_type must be one of" in r.text


@pytest.mark.parametrize("etype,amount", [
    ("TRANSFER_IN", 88.15), ("TRANSFER_OUT", -88.15), ("DIVIDEND", 0.64),
    ("FEE", -1.25), ("ADJUSTMENT", -22.79), ("OTHER", 5.0), ("ACH", 60.93),
])
def test_the_vocabulary_including_the_legacy_words_is_accepted(client, test_api_key,
                                                               etype, amount):
    """POSITIVE CONTROL for the type check, and the legacy `ACH` resolves by sign."""
    r = client.post(EVENT, json=event_body(event_type=etype, amount=amount),
                    headers=hdr(test_api_key))
    assert r.status_code == 200, r.text


def test_a_zero_amount_event_is_refused(client, test_api_key):
    r = client.post(EVENT, json=event_body(amount=0), headers=hdr(test_api_key))
    assert r.status_code == 400


@pytest.mark.parametrize("bad", ["", "31/08/2026", "last tuesday"])
def test_an_event_with_a_bad_date_is_refused(client, test_api_key, bad):
    r = client.post(EVENT, json=event_body(event_date=bad), headers=hdr(test_api_key))
    assert r.status_code == 400
    assert "ISO date" in r.text


# -- R-IV.548(c): the legacy route no longer edits the quarantined total ------

def test_cash_flows_defaults_to_no_mutation():
    """The default is the whole point: an old caller that says nothing now mutates
    nothing."""
    from api.portfolio import CashFlowCreate

    assert CashFlowCreate(amount=10.0).adjust_balance is False


def test_cash_flows_answers_an_explicit_request_rather_than_obeying_it():
    """Ignoring the flag without saying so would be a different kind of lie from
    mutating the total, so the route still answers it -- in the response body."""
    import inspect

    from api import portfolio

    src = inspect.getsource(portfolio.log_cash_flow)
    assert "balance_adjusted" in src
    assert "NOT applied" in src
    assert "cash-balance" in src


def test_cash_flows_says_so_when_the_row_did_not_land():
    """An INSERT ... RETURNING that returns nothing is not a success with an empty
    body. It used to raise a TypeError three lines later on a None."""
    import inspect

    from api import portfolio

    assert "returned no row" in inspect.getsource(portfolio.log_cash_flow)


def test_the_legacy_route_writes_no_account_balances_update():
    """Source-level, because the mocked pool would swallow the UPDATE silently."""
    import ast
    import inspect

    from api import portfolio

    tree = ast.parse(inspect.getsource(portfolio.log_cash_flow).lstrip())
    docs = {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef))
            and getattr(n, "body", None) and isinstance(n.body[0], ast.Expr)
            and isinstance(n.body[0].value, ast.Constant)}
    live = " ".join(n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and id(n) not in docs).upper()
    assert "UPDATE ACCOUNT_BALANCES" not in live
    assert "INSERT INTO CASH_FLOWS" in live        # positive control


# -- R-IV.548(d): status is a vocabulary, and the column says so -------------

def test_the_status_constraint_is_generated_from_the_one_vocabulary():
    """Two copies of a vocabulary is how the second one gets forgotten."""
    import inspect

    from database import postgres_client as pc
    from models.position_status import STATUSES

    assert pc._POSITION_STATUSES is STATUSES
    src = inspect.getsource(pc)
    assert "unified_positions_status_check" in src
    # The list is generated, not retyped beside the constraint.
    assert '"\'%s\'" % s for s in _POSITION_STATUSES' in src


def test_the_vocabulary_is_exactly_what_the_census_found():
    """Census 2026-09-24 over 489 rows: CLOSED 408, EXPIRED 34, DUPLICATE_OF 24,
    OPEN 23, and nothing else. A fifth word here without a census is the defect."""
    from models.position_status import STATUSES

    assert set(STATUSES) == {"OPEN", "CLOSED", "EXPIRED", "DUPLICATE_OF"}


def test_no_query_filters_positions_on_a_lowercase_status():
    """Found during the census: ticker_profile asked for status = 'open' against a
    column that only ever holds uppercase, so it matched nothing, silently, forever."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for path in root.rglob("*.py"):
        if "tests" in path.parts or ".venv" in str(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "unified_positions" not in text:
            continue
        for bad in ("status = 'open'", "status='open'", 'status = "open"'):
            if bad in text:
                offenders.append("%s: %s" % (path.name, bad))
    assert not offenders, offenders
