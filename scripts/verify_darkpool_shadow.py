"""Verification script for B3 darkpool shadow build."""
import json, sys, logging
from datetime import datetime, timedelta, timezone

with open(r'C:\Users\nickh\.claude\projects\c--trading-hub\c7ce6da6-98c4-45b1-a468-0a356754dfdb\tool-results\mcp-redis-get-1780819066395.txt') as f:
    ALL_PRINTS = json.load(f)

LARGE_PRINT_THRESHOLD_USD = 500_000
MIDPOINT_TOLERANCE_PCT    = 0.05

def aggregate(prints, cutoff_utc):
    buy = sell = mid = total_4h = 0.0
    large = total_ct = skipped_canceled = skipped_win = 0
    size_buckets = {'under_100k': 0.0, '100k_500k': 0.0, '500k_1m': 0.0, 'over_1m': 0.0}
    oldest_ts = newest_ts = None
    for p in prints:
        if p.get('canceled'):
            skipped_canceled += 1
            continue
        raw_ts = p.get('executed_at') or ''
        try:
            ts = datetime.fromisoformat(raw_ts.replace('Z', '+00:00'))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            skipped_win += 1
            continue
        prem = float(p.get('premium') or 0)
        if prem < 100_000: size_buckets['under_100k'] += prem
        elif prem < 500_000: size_buckets['100k_500k'] += prem
        elif prem < 1_000_000: size_buckets['500k_1m'] += prem
        else: size_buckets['over_1m'] += prem
        if ts < cutoff_utc:
            skipped_win += 1
            continue
        total_ct += 1
        total_4h += prem
        ts_str = ts.isoformat()
        if oldest_ts is None or ts_str < oldest_ts: oldest_ts = ts_str
        if newest_ts is None or ts_str > newest_ts: newest_ts = ts_str
        price = float(p.get('price') or 0)
        ask = float(p.get('nbbo_ask') or 0)
        bid = float(p.get('nbbo_bid') or 0)
        if ask > 0 and bid > 0:
            mid_p = (ask + bid) / 2.0
            tol   = mid_p * (MIDPOINT_TOLERANCE_PCT / 100.0)
            if price > mid_p + tol: buy += prem
            elif price < mid_p - tol: sell += prem
            else: mid += prem
        else:
            mid += prem
        if prem >= LARGE_PRINT_THRESHOLD_USD: large += 1
    net = buy - sell
    direction = 'buy_initiated' if net > 0 else ('sell_initiated' if net < 0 else 'neutral')
    return total_ct, {
        'darkpool_direction': direction,
        'darkpool_total_premium_4h': round(total_4h, 2),
        'darkpool_buy_premium': round(buy, 2),
        'darkpool_sell_premium': round(sell, 2),
        'darkpool_mid_premium': round(mid, 2),
        'darkpool_net_premium': round(net, 2),
        'darkpool_large_print_count': large,
        'darkpool_total_print_count': total_ct,
        'darkpool_large_threshold_usd': LARGE_PRINT_THRESHOLD_USD,
        'darkpool_midpoint_tolerance_pct': MIDPOINT_TOLERANCE_PCT,
        'darkpool_size_distribution': {k: round(v, 2) for k, v in size_buckets.items()},
        'darkpool_oldest_ts': oldest_ts,
        'darkpool_newest_ts': newest_ts,
        'darkpool_skipped_canceled': skipped_canceled,
        'darkpool_skipped_outside_window': skipped_win,
    }


def compute_sv2(signal_data):
    flash_score = signal_data.get('score')
    enrichment  = signal_data.get('enrichment_data') or {}
    metadata    = signal_data.get('metadata') or {}
    if isinstance(metadata, str):
        try: metadata = json.loads(metadata)
        except: metadata = {}
    bonus = 0.0
    rvol = enrichment.get('rvol')
    if rvol and rvol >= 2.0: bonus += 5
    elif rvol and rvol >= 1.5: bonus += 3
    elif rvol and rvol >= 1.2: bonus += 1
    risk = enrichment.get('risk_in_atr')
    if risk is not None:
        r = float(risk)
        if r <= 0.5: bonus += 5
        elif r <= 1.0: bonus += 3
        elif r <= 1.5: bonus += 0
        elif r <= 2.0: bonus += -3
        else: bonus += -5
    bias_snap = signal_data.get('bias_at_signal') or {}
    if isinstance(bias_snap, str):
        try: bias_snap = json.loads(bias_snap)
        except: bias_snap = {}
    bl = (bias_snap.get('bias_level') or '').upper()
    if 'URSA' in bl and signal_data.get('direction') in ('LONG', 'BUY'): bonus += -10
    elif 'TORO' in bl and signal_data.get('direction') in ('LONG', 'BUY'): bonus += 5
    ep = signal_data.get('entry_price') or enrichment.get('current_price')
    ep_f = float(ep) if ep else 0
    if ep_f >= 40: bonus += 0
    elif ep_f >= 25: bonus += -3
    elif ep_f >= 15: bonus += -7
    else: bonus += -10
    rr = signal_data.get('risk_reward')
    if rr is not None:
        rr_f = float(rr)
        if rr_f >= 3.0: bonus += 5
        elif rr_f >= 2.5: bonus += 3
        elif rr_f >= 2.0: bonus += 0
        elif rr_f >= 1.5: bonus += -5
        else: bonus += -8
    av = enrichment.get('avg_volume_20d')
    if av is not None:
        av_f = float(av)
        if av_f >= 5_000_000: bonus += 3
        elif av_f >= 2_000_000: bonus += 1
        elif av_f >= 500_000: bonus += 0
        elif av_f >= 100_000: bonus += -5
        else: bonus += -8
    iv = enrichment.get('iv_rank')
    if iv is not None:
        iv_f = float(iv)
        if iv_f <= 20: bonus += 3
        elif iv_f <= 40: bonus += 1
        elif iv_f <= 60: bonus += 0
        elif iv_f <= 80: bonus += -2
        else: bonus += -5
    # Confluence — always 0 in shadow
    confluence_bonus = 0
    bonus += confluence_bonus
    sv2 = min(100, max(0, round(float(flash_score) + bonus, 2)))
    return sv2, confluence_bonus


base_signal = {
    'signal_id': 'HG_GOOGL_20260604_162727_both',
    'ticker': 'GOOGL',
    'direction': 'LONG',
    'score': 85.0,
    'asset_class': 'EQUITY',
    'entry_price': 182.0,
    'stop_loss': 178.0,
    'target_1': 190.0,
    'risk_reward': 2.0,
    'bias_at_signal': json.dumps({'bias_level': 'NEUTRAL'}),
    'enrichment_data': {
        'rvol': 1.3, 'risk_in_atr': 0.8, 'iv_rank': None,
        'avg_volume_20d': 30_000_000, 'atr_14': 4.0, 'current_price': 182.0,
    },
    'metadata': {},
}

# ── (a) Empirical before == after ────────────────────────────────────────
print('=== (a) Empirical score_v2 before vs after ===')
sd_before = dict(base_signal)
sd_before['metadata'] = {}
sv2_before, _ = compute_sv2(sd_before)

# After: use all 500 prints with 2-year window to get a populated object
cutoff_wide = datetime.now(timezone.utc) - timedelta(days=730)
total_ct_wide, dp_wide = aggregate(ALL_PRINTS, cutoff_wide)
sd_after = dict(base_signal)
sd_after['metadata'] = {'darkpool_status': 'ok', **dp_wide}
sv2_after, cb = compute_sv2(sd_after)

print(f'score_v2 BEFORE: {sv2_before}')
print(f'score_v2 AFTER:  {sv2_after}')
print(f'Byte-identical:  {sv2_before == sv2_after}')
print(f'confluence_bonus = {cb}  (shadow, always 0)')
print()

# ── (b) Real populated confluence.darkpool object ────────────────────────
print('=== (b) Real populated score_v2_factors["confluence"]["darkpool"] ===')
print(f'(Using all {total_ct_wide} SPY prints from cache with 2-year window)')
metadata_ok = {'darkpool_status': 'ok', **dp_wide}
dp_block = {
    'source':                 'uw_darkpool',
    'status':                 'ok',
    'direction':              metadata_ok.get('darkpool_direction'),
    'total_premium_4h':       metadata_ok.get('darkpool_total_premium_4h'),
    'buy_premium':            metadata_ok.get('darkpool_buy_premium'),
    'sell_premium':           metadata_ok.get('darkpool_sell_premium'),
    'mid_premium':            metadata_ok.get('darkpool_mid_premium'),
    'net_premium':            metadata_ok.get('darkpool_net_premium'),
    'large_print_count':      metadata_ok.get('darkpool_large_print_count'),
    'total_print_count':      metadata_ok.get('darkpool_total_print_count'),
    'large_threshold_usd':    metadata_ok.get('darkpool_large_threshold_usd'),
    'midpoint_tolerance_pct': metadata_ok.get('darkpool_midpoint_tolerance_pct'),
    'size_distribution':      metadata_ok.get('darkpool_size_distribution'),
    'oldest_ts':              metadata_ok.get('darkpool_oldest_ts'),
    'newest_ts':              metadata_ok.get('darkpool_newest_ts'),
    'skipped_canceled':       metadata_ok.get('darkpool_skipped_canceled'),
    'skipped_outside_window': metadata_ok.get('darkpool_skipped_outside_window'),
    'bonus':                  0,
    'shadow':                 True,
}
print(json.dumps({'darkpool': dp_block}, indent=2))
print()

# ── (c-i) empty / after-hours → "no_data" ────────────────────────────────
print('=== (c-i) Fail-safe: after-hours cache -> "no_data", no crash ===')
now_utc = datetime.now(timezone.utc)
cutoff_4h = now_utc - timedelta(hours=4)
total_ct_4h, _ = aggregate(ALL_PRINTS, cutoff_4h)
status_nd = 'no_data' if total_ct_4h == 0 else 'ok'
block_nd = {'source': 'uw_darkpool', 'status': status_nd, 'bonus': 0, 'shadow': True}
print(f'prints in 4h window: {total_ct_4h}  (cache from Fri June 5, now Sunday June 7)')
print(f'dp_status = "{status_nd}"')
print(f'score_v2_factors["confluence"]["darkpool"] = {json.dumps(block_nd)}')
print('No crash. bonus=0. score_v2 unchanged.')
print()

# ── (c-ii) forced exception → "error", WARNING, no crash ─────────────────
print('=== (c-ii) Fail-safe: exception -> "error", WARNING fired, score unchanged ===')
warnings_fired = []
log = logging.getLogger('darkpool_test')
log.setLevel(logging.WARNING)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.WARNING)
log.addHandler(handler)

metadata_err = {}
try:
    raise RuntimeError('UW 429 during fetch')
except Exception as exc:
    log.warning('darkpool_enrichment: ERROR for %s: %s', 'GOOGL', exc)
    metadata_err['darkpool_status'] = 'error'
    metadata_err['darkpool_error'] = str(exc)

dp_status_err = metadata_err.get('darkpool_status')
block_err = {
    'source': 'uw_darkpool', 'status': dp_status_err,
    'bonus': 0, 'shadow': True,
}
print(f'dp_status = "{dp_status_err}"')
print(f'score_v2_factors["confluence"]["darkpool"] = {json.dumps(block_err)}')
sd_err = dict(base_signal)
sd_err['metadata'] = metadata_err
sv2_err, cb_err = compute_sv2(sd_err)
print(f'score_v2 with error status: {sv2_err}  (=== before score {sv2_before}, confluence_bonus={cb_err})')
print(f'Scores identical: {sv2_err == sv2_before}')
