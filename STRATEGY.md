# Strategy confluence filters (summary)

Base: EMA9/21 + RSI14 on 15m.

Required (default on):
1. Fib lookback 80: LONG near 0.382/0.5/0.618 support of upswing; SHORT near resistance of downswing. Tol = max(0.25% price, 0.5*ATR14).
2. MACD 12/26/9 agrees with EMA side (hist > 0 long / < 0 short).
3. ATR% >= 0.15 (chop filter). ATR_MAX_PCT=0 disables extreme cap.
4. **HTF bias** (`FILTER_HTF=1`): 4h EMA20 > EMA50 for LONG; opposite for SHORT. Skip if HTF disagrees. (Backtest resamples 15m→4h; live fetches 4h klines.)
5. **Supertrend** (`FILTER_SUPERTREND=1`): ATR Supertrend period 10, multiplier 3. LONG only if bullish / price above ST; SHORT only if bearish.

Off by default (code kept): Volume, OBV, SMC, ADX.
Prior Volume+SMC stack worsened expectancy vs Fib+MACD+ATR alone.
Ablation (~120d): HTF alone helped most; Supertrend alone hurt; HTF+ST ~flat vs baseline.

Honest caveat: indicators alone may not create a durable edge. Treat backtests as exploratory.

Optional: FILTER_ADX=1, ADX_MIN=25; FILTER_VOLUME/OBV/SMC=1 to re-test.

Signal format unchanged: 4 entries / 5 TPs / 10x / 1 SL.
