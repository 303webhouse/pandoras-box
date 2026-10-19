"""Statistics shared by the R-IV.1238 studies (HYPNOS-LELEDC v1, regime-filter v1). Pure numpy.

No scipy / statsmodels: QUERY runs these scripts in its own interpreter, so nothing here needs a
package beyond numpy and pandas. Every function is self-tested in the scripts that import it.

    diff_t_clustered  y = a + b*D, b = mean(y | D=1) - mean(y | D=0), CR1 cluster-robust SE
                      (clusters = signal dates). The "date-clustered t" of a difference.
    diff_t_hac        the same b, with a time-distance Bartlett HAC: observations whose bar
                      indices are within L of each other are correlated with weight 1 - d/(L+1).
                      With one observation per bar this IS Newey-West with L lags; same-bar
                      observations (BTC and ETH on one day) get weight 1.
    t_sf_two_sided    two-sided p of Student's t (regularised incomplete beta, Lentz CF).
    holm              Holm-Bonferroni step-down adjusted p-values.
"""
import math

import numpy as np


BETA_MIN_VALID = 50              # skill §3.3: >= 50 valid sessions in the 60
BETA_RAW_LO, BETA_RAW_HI = 0.0, 4.0   # R-IV.1245(c): raw beta <= 0 or > 4 is not a usable hedge ratio


def guard_beta(b_raw, n_valid, min_valid=BETA_MIN_VALID):
    """(beta_adj, flagged) from a raw OLS beta series and its valid-session counts.
    flagged = too few valid sessions (skill §3.3) OR no estimate OR raw beta <= 0 OR raw beta > 4
    (R-IV.1245(c): QUERY found shrunk betas from -13.3 to +70.7 with nothing flagged, because the old
    guard checked the session count and never the value). A flagged row uses beta = 1.
    beta_adj = 0.67 * beta + 0.33."""
    flagged = ~(n_valid >= min_valid) | b_raw.isna() | (b_raw <= BETA_RAW_LO) | (b_raw > BETA_RAW_HI)
    b = b_raw.where(~flagged, 1.0)
    return 0.67 * b + 0.33, flagged


def _ols_diff(y, d):
    y = np.asarray(y, float)
    d = np.asarray(d, float)
    X = np.column_stack([np.ones_like(y), d])
    xtx_inv = np.linalg.inv(X.T @ X)
    beta = xtx_inv @ X.T @ y
    return X, xtx_inv, beta, y - X @ beta


def diff_t_clustered(y, d, clusters):
    """(b, se, t, G). G = number of clusters; df for the t is G - 1."""
    y = np.asarray(y, float)
    d = np.asarray(d, float)
    if len(y) < 3 or d.min() == d.max():
        return None
    X, xtx_inv, beta, e = _ols_diff(y, d)
    cl = np.asarray(clusters)
    _, inv = np.unique(cl, return_inverse=True)
    G = inv.max() + 1
    if G < 2:
        return None
    scores = np.zeros((G, 2))
    np.add.at(scores, inv, X * e[:, None])
    meat = scores.T @ scores
    n, k = X.shape
    adj = (G / (G - 1)) * ((n - 1) / (n - k))
    V = adj * xtx_inv @ meat @ xtx_inv
    se = math.sqrt(V[1, 1]) if V[1, 1] > 0 else float("nan")
    return float(beta[1]), se, float(beta[1] / se) if se == se and se > 0 else float("nan"), int(G)


def diff_t_hac(y, d, bar_index, lags):
    """(b, se, t, n). Time-distance Bartlett HAC with bandwidth `lags` (in bars)."""
    y = np.asarray(y, float)
    d = np.asarray(d, float)
    if len(y) < 3 or d.min() == d.max():
        return None
    X, xtx_inv, beta, e = _ols_diff(y, d)
    s = X * e[:, None]
    bi = np.asarray(bar_index, np.int64)
    order = np.argsort(bi, kind="stable")
    bi, s = bi[order], s[order]
    meat = np.zeros((2, 2))
    n = len(bi)
    for i in range(n):
        j = i
        while j < n and bi[j] - bi[i] <= lags:
            w = 1.0 - (bi[j] - bi[i]) / (lags + 1.0)
            if j == i:
                meat += np.outer(s[i], s[i])
            else:
                o = np.outer(s[i], s[j])
                meat += w * (o + o.T)
            j += 1
    V = xtx_inv @ meat @ xtx_inv * (n / (n - 2))
    se = math.sqrt(V[1, 1]) if V[1, 1] > 0 else float("nan")
    return float(beta[1]), se, float(beta[1] / se) if se == se and se > 0 else float("nan"), int(n)


def _betacf(a, b, x):
    tiny, eps = 1e-300, 3e-16
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, dd = 1.0, 1.0 - qab * x / qap
    dd = tiny if abs(dd) < tiny else dd
    dd = 1.0 / dd
    h = dd
    for m in range(1, 400):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        dd = 1.0 + aa * dd
        dd = tiny if abs(dd) < tiny else dd
        c = 1.0 + aa / c
        c = tiny if abs(c) < tiny else c
        dd = 1.0 / dd
        h *= dd * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        dd = 1.0 + aa * dd
        dd = tiny if abs(dd) < tiny else dd
        c = 1.0 + aa / c
        c = tiny if abs(c) < tiny else c
        dd = 1.0 / dd
        delta = dd * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def betainc_reg(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_sf_two_sided(t, df):
    if t != t or df is None or df <= 0:
        return float("nan")
    x = df / (df + t * t)
    return betainc_reg(df / 2.0, 0.5, x)


def holm(pvals):
    """Holm step-down adjusted p-values, same order as the input. NaN p counts as 1."""
    p = np.array([1.0 if (q is None or q != q) else float(q) for q in pvals])
    m = len(p)
    order = np.argsort(p, kind="stable")
    adj = np.empty(m)
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (m - rank) * p[i]))
        adj[i] = run
    return adj.tolist()
