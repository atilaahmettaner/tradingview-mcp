"""Cross-check calc_supertrend against pandas-ta, a third-party reference.

The rest of the Supertrend tests assert properties we chose ourselves, which
cannot catch a misreading of the indicator's definition. This file compares
our output against an implementation nobody here wrote.

Skipped unless pandas-ta is installed, so it never blocks the default run:

    uv run --with pandas --with pandas-ta python -m pytest \\
        tests/unit/services/test_supertrend_reference.py

Measured on real 4h candles (BTC, ETH, SOL; ~1,090 bars each) the two agree
on 97.9-99.4% of bars, and every disagreement falls in the warm-up run before
the first band penetration, where direction is only the seed guess:
pandas-ta and Pine seed +1, we seed from close-vs-SMA. From the first flip
onward the two match bar for bar, which is the property pinned below.
"""
import pytest

pd = pytest.importorskip("pandas")
ta = pytest.importorskip("pandas_ta")

from tradingview_mcp.core.services.indicators_calc import calc_supertrend

_LENGTH = 10
_MULTIPLIER = 3.0


def _synthetic(n=400):
    """A deterministic series with several real reversals.

    Synthetic rather than live so the test cannot fail because a venue was
    unreachable; the live comparison is documented in the module docstring.
    """
    out, px, step = [], 100.0, 1.0
    for i in range(n):
        if i and i % 80 == 0:
            step = -step * 1.6          # reversal sharp enough to cross a band
        rng = 1.0 + (i % 7) * 0.25      # varying bar range -> varying ATR
        out.append({"high": px + rng, "low": px - rng, "close": px})
        px += step
        if px < 10:
            px, step = 10.0, abs(step)
    return out


def _ours(candles):
    st = calc_supertrend(
        [c["high"] for c in candles],
        [c["low"] for c in candles],
        [c["close"] for c in candles],
        _LENGTH,
        _MULTIPLIER,
    )
    return st["direction"]


def _reference(candles):
    df = pd.DataFrame(candles)
    st = ta.supertrend(df["high"], df["low"], df["close"],
                       length=_LENGTH, multiplier=_MULTIPLIER)
    col = next(k for k in st.columns if k.startswith("SUPERTd"))
    return st[col].tolist()


def _comparable(mine, ref):
    return [
        (i, m, r) for i, (m, r) in enumerate(zip(mine, ref))
        if m is not None and not pd.isna(r)
    ]


def _first_flip(mine):
    known = [i for i, d in enumerate(mine) if d is not None]
    for pos, i in enumerate(known[1:], 1):
        if mine[i] != mine[known[pos - 1]]:
            return i
    return None


def test_matches_reference_from_the_first_flip_onward():
    candles = _synthetic()
    mine, ref = _ours(candles), _reference(candles)
    pairs = _comparable(mine, ref)
    assert pairs, "nothing comparable — check the reference column name"

    flip = _first_flip(mine)
    assert flip is not None, "series must contain a reversal to be meaningful"

    mismatched = [(i, m, r) for i, m, r in pairs if i >= flip and m != r]
    assert mismatched == [], (
        "calc_supertrend diverges from pandas-ta after direction is confirmed: "
        f"{mismatched[:5]}"
    )


def test_overall_agreement_is_high():
    candles = _synthetic()
    mine, ref = _ours(candles), _reference(candles)
    pairs = _comparable(mine, ref)
    agree = sum(1 for _, m, r in pairs if m == r)
    ratio = agree / len(pairs)
    # Pre-flip seed bars are allowed to differ; everything else must not.
    assert ratio > 0.90, f"only {ratio:.1%} of bars agree with pandas-ta"


def test_both_implementations_find_the_same_flip_bars_after_warmup():
    candles = _synthetic()
    mine, ref = _ours(candles), _reference(candles)
    flip = _first_flip(mine)

    def flips(series, lo):
        out = []
        prev = None
        for i, d in enumerate(series):
            if d is None or (isinstance(d, float) and pd.isna(d)):
                continue
            if prev is not None and d != prev and i >= lo:
                out.append(i)
            prev = d
        return out

    assert flips(mine, flip) == flips(ref, flip)
