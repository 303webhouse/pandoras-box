"""TA-161: the cut verdict is computed from the GATED MARK — R-IV.983(b), ordered by 988(f).

    cut_pnl = orientation x (mark_gated - entry_basis_per_unit) x multiplier x open_quantity

The two live B2 rows are the worked examples, and `max_loss` -- written by a DIFFERENT writer --
independently confirms each multiplier:

    IBIT  put_debit_spread  0.19       x 2  x 100 = 38.00    == max_loss 38
    TSLQ  stock             18.968875  x 80 x   1 = 1517.51  == max_loss 1517.51

That cross-check is the whole reason the structure map is allowed to stand in for a multiplier
column this book does not have.
"""
from __future__ import annotations

import ast
import inspect
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from models import b2_cut_alert as b2

ET = ZoneInfo("America/New_York")


def _post_close(cut: date) -> datetime:
    return datetime(cut.year, cut.month, cut.day, 16, 1, tzinfo=ET)


def _row(**kw):
    """A row that PASSES every gate, so each test changes exactly one thing."""
    cut = b2.alert_first_deploy_session() + timedelta(days=7)
    base = {"position_id": "POS_TEST", "bucket": "B2", "structure": "put_debit_spread",
            "entry_price": "0.19", "open_quantity": 2, "quantity": 2,
            "mark": "0.03", "mark_integrity": "ok",
            "mark_as_of": _post_close(cut), "expiry": cut + timedelta(days=60),
            "realized_pnl": None, "unrealized_pnl": None, "b2_cut_alerted_at": None}
    base.update(kw)
    return base


def _entry_for_cut(cut: date) -> date:
    """An entry date whose 3rd trading session is `cut`.

    BOUNDED. The first version searched backwards without a limit, so when `cut` was handed a
    WEEKEND -- which `add_trading_days` can never return -- it walked back to year 1 and died
    of OverflowError. An unbounded search that fails by arithmetic overflow tells you nothing;
    this one names the actual problem.
    """
    from stable_engine.market_calendar import add_trading_days
    d = cut
    for _ in range(30):
        d -= timedelta(days=1)
        try:
            if add_trading_days(d, b2.SESSIONS_TO_CUT) == cut:
                return d
        except Exception:                                           # noqa: BLE001
            continue
    raise AssertionError(
        "%s is not reachable as a 3rd trading session -- it is probably not a trading day "
        "(weekday %d)" % (cut, cut.weekday()))


# -- the seventh verdict ---------------------------------------------------------------

def test_there_are_exactly_seven_verdicts_and_they_are_distinct():
    assert len(b2.VERDICTS) == 7, b2.VERDICTS
    assert len(set(b2.VERDICTS)) == 7
    assert b2.NOT_EVALUABLE in b2.VERDICTS
    # NOT_EVALUABLE and UNDETERMINED are different answers and must not collapse.
    assert b2.NOT_EVALUABLE != b2.UNDETERMINED


# -- the formula ------------------------------------------------------------------------

def test_ibit_worked_example_matches_max_loss_cross_check():
    """IBIT: 1 x (0.03 - 0.19) x 100 x 2 = -32.00, and the basis leg is max_loss 38."""
    pnl, why, w = b2.cut_pnl(_row(), "0.03")
    assert why is None, why
    assert pnl == Decimal("-32.00"), pnl
    assert w["multiplier"] == 100
    assert w["orientation"] == 1
    # The independent confirmation: basis x multiplier x qty is the recorded max_loss.
    assert Decimal(w["entry_basis_per_unit"]) * 100 * 2 == Decimal("38.00")


def test_tslq_worked_example_is_shares_with_multiplier_one():
    # `position_orientation` supplied explicitly: since R-IV.1010(d) `stock` is NOT on the
    # closed DEBIT whitelist, so the arithmetic is exercised through the column that will
    # eventually carry orientation for real, not through a structure guess.
    row = _row(structure="stock", entry_price="18.968875", open_quantity=80, mark="17.19",
               position_orientation="DEBIT")
    pnl, why, w = b2.cut_pnl(row, "17.19")
    assert why is None, why
    assert w["multiplier"] == 1, w
    # 1 x (17.19 - 18.968875) x 1 x 80 = -142.31, HALF-UP to the cent (convention #27).
    assert pnl == Decimal("-142.31"), pnl
    assert Decimal(w["entry_basis_per_unit"]) * 1 * 80 == Decimal("1517.51000")


def test_a_profitable_mark_gives_a_positive_pnl():
    """THE SIGN CONTROL. Without it every assertion above passes for a formula that always
    returns a loss."""
    pnl, why, _ = b2.cut_pnl(_row(), "0.40")
    assert why is None, why
    assert pnl == Decimal("42.00"), pnl


def test_money_is_half_up_to_the_cent_not_bankers_rounding():
    row = _row(structure="stock", entry_price="0", open_quantity=1,
               position_orientation="DEBIT")      # `stock` is held without it (R-IV.1010(d))
    pnl, why, _ = b2.cut_pnl(row, "0.125")
    assert why is None, why
    assert pnl == Decimal("0.13"), pnl        # HALF-UP; bankers' rounding gives 0.12


# -- open_quantity, never quantity (convention #29) ------------------------------------

def test_the_size_is_open_quantity_and_never_quantity():
    """A partially exited row: opened 5, 3 still held. Sizing off `quantity` would overstate
    the cut P&L by two thirds -- exactly what HYG's row is for."""
    row = _row(entry_price="0.136", quantity=5, open_quantity=3, mark="0.29")
    pnl, why, w = b2.cut_pnl(row, "0.29")
    assert why is None, why
    assert w["open_quantity"] == "3"
    assert pnl == Decimal("46.20"), pnl       # 1 x 0.154 x 100 x 3; off `quantity` it is 77.00


def test_a_null_open_quantity_is_unknown_not_flat():
    pnl, why, _ = b2.cut_pnl(_row(open_quantity=None), "0.03")
    assert pnl is None
    assert "unknown size" in why, why


def test_cut_pnl_source_never_mentions_quantity_on_its_own():
    """A PARSED check, prose stripped: the docstring names `quantity` while explaining why it
    is the wrong field, so a substring scan of the raw source fails on its own explanation.
    Fourth time this trap has been hit here -- including once by this very assertion."""
    src = inspect.getsource(b2.cut_pnl)
    fn = ast.parse(src).body[0]
    doc = fn.body[0].value if fn.body and isinstance(fn.body[0], ast.Expr) else None
    code = chr(10).join(ast.unparse(n) for n in fn.body
                        if not (isinstance(n, ast.Expr) and n.value is doc))
    assert len(code) > 400, "the docstring stripper ate the body"
    assert "'quantity'" not in code, "cut_pnl reads `quantity`"
    assert "open_quantity" in code
    # THE CENTRAL INVARIANT OF TA-161.
    assert "unrealized" not in code, "cut_pnl reads unrealized_pnl"


# -- orientation ------------------------------------------------------------------------

def test_orientation_comes_from_an_explicit_field_not_a_price_sign():
    assert b2.orientation({"position_orientation": "CREDIT"})[0] == -1
    assert b2.orientation({"position_orientation": "DEBIT"})[0] == 1
    # The explicit column WINS over the structure, so this function stops being the author
    # the moment the column arrives.
    sign, why = b2.orientation({"position_orientation": "CREDIT",
                                "structure": "put_debit_spread"})
    assert sign == -1, why


def test_credit_structures_are_not_evaluated_yet():
    """R-IV.983(b): DEBIT-opened rows only until a position_orientation column exists."""
    pnl, why, _ = b2.cut_pnl(_row(structure="put_credit_spread"), "0.03")
    assert pnl is None
    assert "credit-opened" in why, why


def test_an_unknown_structure_is_not_given_a_default_orientation():
    pnl, why, _ = b2.cut_pnl(_row(structure="iron_condor_butterfly_thing"), "0.03")
    assert pnl is None
    assert "orientation" in why or "contract map" in why, why


# -- the multiplier ---------------------------------------------------------------------

def test_an_unrecognised_structure_yields_no_multiplier_rather_than_100():
    """A guessed multiplier is wrong by 100x in one direction or the other."""
    m, why = b2.contract_multiplier({"structure": "wheat_future"})
    assert m is None, (m, why)


def test_a_multiplier_column_would_win_if_it_existed():
    m, why = b2.contract_multiplier({"structure": "stock", "multiplier": 50})
    assert m == 50, why
    assert "multiplier column" in why


def test_a_structure_mixing_shares_and_contracts_is_refused():
    m, why = b2.contract_multiplier({"structure": "stock+long_call"})
    assert m is None
    assert "different" in why, why


# -- composites -------------------------------------------------------------------------

def test_a_composite_needs_a_single_net_mark():
    pnl, why, _ = b2.cut_pnl(_row(structure="put_debit_spread+long_put"), "0.08")
    assert pnl is None
    assert "net mark" in why, why


def test_a_composite_with_a_net_mark_is_evaluated():
    """THE CONTROL for the test above: the refusal must be about the MARK, not about
    composites being unsupported outright."""
    # Every part whitelisted: `put_debit_spread+long_put` is HELD since R-IV.1010(d), so the
    # composite rule is now exercised with a composite that can actually reach it.
    row = _row(structure="put_debit_spread+call_debit_spread", entry_price="0.14",
               open_quantity=5, mark_is_net=True)
    pnl, why, _ = b2.cut_pnl(row, "0.08")
    assert why is None, why
    assert pnl == Decimal("-30.00"), pnl


# -- divergence -------------------------------------------------------------------------

def test_divergence_records_both_figures_and_both_timestamps():
    t1 = datetime(2026, 10, 13, 20, 15, 1, tzinfo=ET)
    t2 = datetime(2026, 10, 13, 16, 47, 0, tzinfo=ET)
    d = b2.pnl_divergence(Decimal("-32.00"), "-13.00", t1, t2)
    assert d is not None
    assert d["cut_pnl"] == "-32.00"
    assert d["unrealized_pnl"] == "-13.00"
    assert d["cut_pnl_as_of"] == t1.isoformat()
    assert d["unrealized_pnl_as_of"] == t2.isoformat()
    assert d["difference"] == "-19.00"


def test_agreement_within_a_cent_records_nothing():
    """IBIT's two writers agreed on 2026-10-13 and disagreed on 10-12. Agreement must not
    manufacture a divergence record, or every row would carry one."""
    assert b2.pnl_divergence(Decimal("-32.00"), "-32.00", None, None) is None
    assert b2.pnl_divergence(Decimal("-32.00"), "-32.01", None, None) is None
    assert b2.pnl_divergence(Decimal("-32.00"), "-32.02", None, None) is not None


# -- S10 --------------------------------------------------------------------------------

def test_s10_holds_back_a_cut_that_precedes_the_deploy():
    """TSLQ's case: a cut session of 2026-10-05 fired on 10-12 under the old path."""
    cut = date(2026, 10, 5)          # TSLQ's actual cut session, a Monday
    assert cut < b2.alert_first_deploy_session()
    row = _row(entry_price="18.968875", structure="stock", open_quantity=80,
               mark="17.19", mark_as_of=_post_close(cut),
               expiry=None)
    row["entry_date"] = _entry_for_cut(cut)
    out = b2.decide(row, now=_post_close(cut) + timedelta(days=1))
    # R-IV.1005(b): S10 is its own VERDICT now, not a stop_code riding on NOT_EVALUABLE --
    # "I cannot evaluate this" and "this predates the alert" are different answers.
    assert out["verdict"] == b2.CUT_SESSION_PRECEDES_DEPLOY, out
    # The mark is still carried, because an S10 row is exactly the one someone audits.
    assert out["mark"] == "17.19"


def test_s10_does_NOT_hold_back_a_cut_on_or_after_the_deploy():
    """THE CONTROL. An S10 that fired on everything would pass the test above while silencing
    the alert entirely."""
    cut = b2.alert_first_deploy_session() + timedelta(days=7)
    row = _row(mark_as_of=_post_close(cut))
    row["entry_date"] = _entry_for_cut(cut)
    out = b2.decide(row, now=_post_close(cut))
    assert out["verdict"] in (b2.PROFITABLE, b2.NOT_PROFITABLE), out


# -- the verdict comes from the mark ----------------------------------------------------

def test_the_verdict_follows_the_MARK_not_the_stored_unrealized_pnl():
    """THE POINT OF TA-161. The stored figure says +500; the gated mark says the position is
    down. The verdict must follow the mark, and must RECORD the disagreement."""
    cut = b2.alert_first_deploy_session() + timedelta(days=7)
    row = _row(mark="0.03", unrealized_pnl="500.00", mark_as_of=_post_close(cut))
    row["entry_date"] = _entry_for_cut(cut)
    out = b2.decide(row, now=_post_close(cut))
    assert out["verdict"] == b2.NOT_PROFITABLE, out
    assert out["cut_pnl"] == "-32.00", out
    assert out["pnl_divergence"] is not None
    assert out["pnl_divergence"]["unrealized_pnl"] == "500.00"


def test_and_the_reverse_a_stored_loss_does_not_force_a_fire():
    """The mirror control: stored says -500, the mark says the position is up. PROFITABLE."""
    cut = b2.alert_first_deploy_session() + timedelta(days=7)
    row = _row(mark="0.40", unrealized_pnl="-500.00", mark_as_of=_post_close(cut))
    row["entry_date"] = _entry_for_cut(cut)
    out = b2.decide(row, now=_post_close(cut))
    assert out["verdict"] == b2.PROFITABLE, out
    assert out["cut_pnl"] == "42.00", out


def test_flat_still_fires_on_the_computed_figure():
    cut = b2.alert_first_deploy_session() + timedelta(days=7)
    row = _row(mark="0.19", mark_as_of=_post_close(cut))     # exactly the entry basis
    row["entry_date"] = _entry_for_cut(cut)
    out = b2.decide(row, now=_post_close(cut))
    assert out["cut_pnl"] == "0.00", out
    assert out["verdict"] == b2.NOT_PROFITABLE, out


def test_the_mark_gate_still_runs_before_any_pnl_is_computed():
    """A mark from BEFORE the cut close must not reach the arithmetic at all (TA-152)."""
    cut = b2.alert_first_deploy_session() + timedelta(days=7)
    morning = datetime(cut.year, cut.month, cut.day, 9, 17, tzinfo=ET)
    row = _row(mark_as_of=morning)
    row["entry_date"] = _entry_for_cut(cut)
    out = b2.decide(row, now=_post_close(cut))
    assert out["verdict"] == b2.UNDETERMINED, out
    assert out["cut_pnl"] is None, out


def test_an_already_alerted_row_still_reports_its_OWN_verdict():
    """R-IV.1005(b). `ALREADY_FIRED` used to be returned INSTEAD of the P&L verdict, so a row
    that had been alerted on reported its alert history where its answer belonged -- which is
    why IBIT 980 read ALREADY_FIRED when the truth was NOT_PROFITABLE.

    The verdict now describes the POSITION, and `already_alerted` carries the history beside
    it. Alerting is the job's decision, not a verdict."""
    cut = b2.alert_first_deploy_session() + timedelta(days=7)
    row = _row(mark="0.03", mark_as_of=_post_close(cut),
               b2_cut_alerted_at="2026-10-12T20:15:00Z")
    row["entry_date"] = _entry_for_cut(cut)
    out = b2.decide(row, now=_post_close(cut))
    assert out["verdict"] == b2.NOT_PROFITABLE, out
    assert out["cut_pnl"] == "-32.00", out
    assert out["already_alerted"] is True, out
    assert out["b2_cut_alerted_at"] == "2026-10-12T20:15:00Z", out


def test_a_never_alerted_row_says_so():
    """THE CONTROL. A field hardcoded True would pass the test above."""
    cut = b2.alert_first_deploy_session() + timedelta(days=7)
    row = _row(mark_as_of=_post_close(cut))
    row["entry_date"] = _entry_for_cut(cut)
    out = b2.decide(row, now=_post_close(cut))
    assert out["already_alerted"] is False, out
    assert out["b2_cut_alerted_at"] is None, out


def test_the_verdict_set_is_exactly_ta161s():
    """R-IV.1005(b): no other labels. Names that were verdicts and are not any more must be
    GONE from the module, not merely unused -- an importable PASS invites a new caller."""
    assert set(b2.VERDICTS) == {
        "NOT_YET", "NOT_EVALUABLE", "UNDETERMINED", "EXPIRY_STOPPED",
        "CUT_SESSION_PRECEDES_DEPLOY", "NOT_PROFITABLE", "PROFITABLE"}, b2.VERDICTS
    for gone in ("PASS", "FIRE", "ALREADY_FIRED", "S10_CUT_SESSION_PRECEDES_DEPLOY"):
        assert not hasattr(b2, gone), "%s is still importable" % gone


def test_every_path_carries_the_ta161_keys():
    """NOT_YET is read by people too. A payload whose shape depends on the verdict makes a
    reader check whether a key is absent or the value is null."""
    cut = b2.alert_first_deploy_session() + timedelta(days=30)
    row = _row(mark_as_of=None)
    row["entry_date"] = _entry_for_cut(cut)
    out = b2.decide(row, now=datetime(cut.year, cut.month, cut.day, 9, 0, tzinfo=ET))
    assert out["verdict"] == b2.NOT_YET, out
    for key in ("cut_pnl", "pnl_divergence", "workings", "already_alerted",
                "b2_cut_alerted_at", "mark", "mark_as_of", "mark_integrity", "cut_session"):
        assert key in out, key

# -- R-IV.1001(c): the anchor and its clock --------------------------------------------

def test_the_anchor_is_the_FIRST_deploy_and_does_not_move():
    """R-IV.1001(c)2. The old anchor was the day TA-161 shipped, so it advanced with the work
    and would have re-excluded another day's cuts on every later deploy."""
    assert b2.alert_first_deploy_session() == date(2026, 10, 12), b2.ALERT_FIRST_DEPLOY_UTC
    # The module must no longer carry the moving anchor at all -- one author, one value.
    assert not hasattr(b2, "TA161_DEPLOYED_ON")


def test_the_anchor_is_converted_to_new_york_not_read_off_utc():
    """R-IV.1001(c)1 + convention #39. Taking .date() off the UTC instant is right for THIS
    anchor by luck (03:32 ET) and wrong for any deploy between 20:00 and 24:00 ET -- which is
    when four of five deploys on 2026-10-13 landed. The pair below is the proof: a 23:30 ET
    instant is the NEXT day in UTC."""
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    late = datetime(2026, 10, 13, 23, 30, tzinfo=et)       # 2026-10-14 03:30Z
    assert late.astimezone(timezone.utc).date() == date(2026, 10, 14)
    assert late.astimezone(et).date() == date(2026, 10, 13)
    # And the real anchor carries a timezone, so no reader has to assume one.
    assert b2.ALERT_FIRST_DEPLOY_UTC.tzinfo is not None
    assert b2.ALERT_FIRST_DEPLOY_UTC.astimezone(et).date() == b2.alert_first_deploy_session()


def test_the_s10_reason_states_the_clock():
    """Convention #39: a comparison between two fields states their common basis."""
    cut = date(2026, 10, 5)          # a Monday, and before the anchor
    assert cut < b2.alert_first_deploy_session()
    row = _row(structure="stock", entry_price="18.97", open_quantity=80, mark="17.19",
               mark_as_of=_post_close(cut), expiry=None)
    row["entry_date"] = _entry_for_cut(cut)
    out = b2.decide(row, now=_post_close(cut) + timedelta(days=1))
    assert out["verdict"] == b2.CUT_SESSION_PRECEDES_DEPLOY
    assert "America/New_York" in out["reason"], out["reason"]


def test_a_cut_ON_the_anchor_date_evaluates():
    """The boundary is inclusive: the alert was live that session, so it judges it. Without
    this pair an off-by-one that excluded the anchor day would pass every test above."""
    cut = b2.alert_first_deploy_session()
    row = _row(mark_as_of=_post_close(cut))
    row["entry_date"] = _entry_for_cut(cut)
    out = b2.decide(row, now=_post_close(cut))
    assert out["verdict"] in (b2.PROFITABLE, b2.NOT_PROFITABLE), out


# -- R-IV.1010(d): orientation by CLOSED whitelist, exact match ------------------------

def test_orientation_is_a_closed_whitelist_of_exactly_two_values():
    """TA-161 §1.5 as amended. Measured over the book's 688 positions, narrowing from the
    previous wider set moves 430 rows to UNDETERMINED, 326 of them `stock`."""
    assert b2.ORIENTATION_WHITELIST_DEBIT == {"put_debit_spread", "call_debit_spread"}
    assert not hasattr(b2, "_DEBIT_STRUCTURES"), "the wider set is still importable"


def test_the_two_whitelisted_values_are_debit():
    assert b2.orientation({"structure": "put_debit_spread"})[0] == 1
    assert b2.orientation({"structure": "call_debit_spread"})[0] == 1


def test_every_other_structure_in_the_book_is_held():
    """The real census, from hub_get_positions status=ALL: 17 distinct values over 688 rows.
    Each one outside the whitelist must be UNDETERMINED -- including `stock`, which the
    previous set admitted and which is 326 of the book."""
    held = ["stock", "vertical", "long_put", "long_call", "long_single", "call_spread",
            "put_spread", "three_leg", "iron_condor", "put", "put_credit_spread",
            "put_debit_spread+long_put", "call_debit_spread+long_call"]
    for structure in held:
        sign, why = b2.orientation({"structure": structure})
        assert sign is None, "%s was classified %s: %s" % (structure, sign, why)
    # POSITIVE CONTROL: composites made ONLY of whitelisted parts still read DEBIT, so the
    # test above is not passing because everything is held.
    for structure in ("put_debit_spread+call_debit_spread", "put_debit_spread+put_debit_spread"):
        assert b2.orientation({"structure": structure})[0] == 1, structure


def test_matching_is_EXACT_never_a_substring():
    """`put_debit_spread+long_put` CONTAINS "debit" and is not whitelisted. A substring test
    would have passed it -- which is the question TA asked."""
    sign, why = b2.orientation({"structure": "put_debit_spread+long_put"})
    assert sign is None, why
    assert "whitelist" in why, why
    for invented in ("put_debit_spread_v2", "xput_debit_spread", "debit"):
        assert b2.orientation({"structure": invented})[0] is None, invented
    # Case and surrounding whitespace ARE normalised, and that is not a substring match --
    # `_structure_parts` lowercases and strips. Asserted so the distinction stays deliberate.
    assert b2.orientation({"structure": "  PUT_DEBIT_SPREAD "})[0] == 1


def test_a_held_structure_is_still_PRICEABLE():
    """The multiplier map is separate from the orientation whitelist on purpose: a long_put's
    multiplier is knowable even though its orientation is held. Collapsing the two would make
    "I cannot say which way this points" mean "I cannot price it"."""
    assert b2.contract_multiplier({"structure": "long_put"})[0] == 100
    assert b2.contract_multiplier({"structure": "stock"})[0] == 1


def test_the_explicit_column_still_overrides_the_whitelist():
    """So the whitelist stops being the author the moment position_orientation arrives."""
    assert b2.orientation({"structure": "stock", "position_orientation": "DEBIT"})[0] == 1
    assert b2.orientation({"structure": "put_debit_spread",
                           "position_orientation": "CREDIT"})[0] == -1


def test_a_held_row_is_NOT_EVALUABLE_and_names_the_rule():
    cut = b2.alert_first_deploy_session() + timedelta(days=7)
    row = _row(structure="stock", entry_price="18.97", open_quantity=80, mark="17.19",
               mark_as_of=_post_close(cut))
    row["entry_date"] = _entry_for_cut(cut)
    out = b2.decide(row, now=_post_close(cut))
    assert out["verdict"] == b2.NOT_EVALUABLE, out
    assert "whitelist" in out["reason"], out["reason"]
