# Strategy confluence filters (summary)

Base: EMA9/21 + RSI14 on 15m.

Required (default on):
1. Fib lookback 80: LONG near 0.382/0.5/0.618 support of upswing; SHORT near resistance of downswing. Tol = max(0.25% price, 0.5*ATR14).
2. MACD 12/26/9 agrees with EMA side (hist > 0 long / < 0 short).
3. ATR% >= 0.15 (chop filter). ATR_MAX_PCT=0 disables extreme cap.

Optional: FILTER_ADX=1, ADX_MIN=20.

Signal format unchanged: 4 entries / 5 TPs / 10x / 1 SL.
