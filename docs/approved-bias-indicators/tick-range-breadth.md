# TICK Range Breadth Model (Raschke Method)

## Indicator Required
- **NYSE TICK ($TICK)** – Daily high and daily low values
- **Moving Average** of TICK high and TICK low (optional smoothing, 10-period SMA suggested)

## Core Logic

### Daily Bias:

| Condition | Bias |
|-----------|------|
| TICK high > +1000 OR TICK low < -1000 (wide range) | Bullish |
| TICK high < +500 AND TICK low > -500 (narrow range) | Bearish/Short |
| Mixed (one extreme, one compressed) | Neutral/No bias |

### Weekly Bias:
- Count the number of "wide range" days vs "narrow range" days over the trailing 5 sessions
- **3+ wide range days** → Bullish weekly bias
- **3+ narrow range days** → Bearish weekly bias
- **Mixed** → Neutral

## Signal Interpretation

- **Wide TICK range** = Strong breadth participation, institutions actively buying/selling across many stocks → favors long continuation
- **Narrow TICK range** = Low conviction, weak participation, market vulnerable to selling → favors short bias or caution

## Thresholds (Adjustable)

| Parameter | Default Value |
|-----------|---------------|
| Wide range: TICK high above | +1000 |
| Wide range: TICK low below | -1000 |
| Narrow range: TICK high below | +500 |
| Narrow range: TICK low above | -500 |
| Weekly lookback | 5 days |
| MA smoothing (optional) | 10-period SMA |

## Usage
- **Daily:** Check previous day's TICK range before the open to set directional bias
- **Weekly:** Review Friday's count or Monday pre-market to set weekly bias
- **Layer with execution strategies** (e.g., Triple Line Trend Retracement) for filtered entries

## Bias Level Mapping
- **Toro Major**: 4+ wide days in past week + current day wide range
- **Toro Minor**: 3 wide days OR bullish daily but mixed weekly
- **Neutral**: Mixed signals or mid-range TICK
- **Ursa Minor**: 3 narrow days OR bearish daily but mixed weekly
- **Ursa Major**: 4+ narrow days in past week + current day narrow range

## Not Recommended For
- Quarterly bias (too noisy when aggregated over 60+ days)
