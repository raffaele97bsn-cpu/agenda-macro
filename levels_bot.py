import os, sys, json, requests
from datetime import datetime, timezone
import yfinance as yf

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
ASSETS = {
    "NQ=F": "Nasdaq 100", "ES=F": "S&P 500", "GC=F": "Oro",
    "CL=F": "Petrolio WTI", "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD", "USDJPY=X": "USD/JPY",
}
LOOKBACK = 20
STATE = "levels_state.json"
TF = {"H1": (None, 3600), "H4": ("4h", 14400)}


def send(text):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text}, timeout=20,
    ).raise_for_status()


def main():
    now = datetime.now(timezone.utc).timestamp()
    try:
        state = json.load(open(STATE))
    except Exception:
        state = {}
    state = {k: v for k, v in state.items() if v > now - 3 * 86400}
    ok = 0
    for sym, name in ASSETS.items():
        try:
            df = yf.Ticker(sym).history(period="30d", interval="1h")
        except Exception as ex:
            print(sym, ex)
            continue
        if df.empty:
            continue
        ok += 1
        for tf, (rule, dur) in TF.items():
            d = df if rule is None else df.resample(rule).agg(
                {"High": "max", "Low": "min", "Close": "last"}).dropna()
            if len(d) <= LOOKBACK:
                continue
            ts = d.index[-1].timestamp()
            if now - ts > dur + 600:
                continue  # candela vecchia: mercato chiuso
            cur, prev = d.iloc[-1], d.iloc[-1 - LOOKBACK:-1]
            checks = (
                ("high", cur["High"] >= prev["High"].max(), prev["High"].max(), "📈", "massimo"),
                ("low", cur["Low"] <= prev["Low"].min(), prev["Low"].min(), "📉", "minimo"),
            )
            for side, hit, level, icon, word in checks:
                key = f"{sym}|{tf}|{side}|{int(ts)}"
                if hit and key not in state:
                    send(f"{icon} {name} {tf}: nuovo {word} a {LOOKBACK} candele "
                         f"({level:.5g}). Prezzo ora {cur['Close']:.5g}")
                    state[key] = now
    json.dump(state, open(STATE, "w"))
    if "--test" in sys.argv:
        send(f"✅ Livelli: letti {ok}/{len(ASSETS)} asset da Yahoo")


main()
