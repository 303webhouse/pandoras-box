"""R-IV.546(a) — the principal's two cash inputs, at the HTTP boundary.

He types these on the page, so the tests are about what the page can and cannot get
away with: auth, validation, and the refusals. Convention #30 throughout — every
refusal is paired with a request that must SUCCEED, because a route that 400s on
everything would pass every negative test and accept no deposit at all.
"""

import importlib
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
    """A real signed cookie, minted the way the dashboard mints one."""
    monkeypatch.setenv("DASHBOARD_SESSION_SECRET", "test-session-secret-for-cash-entry")
    import utils.session as session

    importlib.reload(session)
    import utils.pivot_auth as pivot_auth

    importlib.reload(pivot_auth)
    token = session.issue_session("test")
    assert token, "the session helper produced no cookie"
    yield session.COOKIE_NAME, token
    monkeypatch.delenv("DASHBOARD_SESSION_SECRET", raising=False)
    importlib.reload(session)
    importlib.reload(pivot_auth)


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
