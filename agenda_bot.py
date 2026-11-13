#!/usr/bin/env python3
"""Agenda macro su Telegram.

- 07:30 (Roma): agenda del giorno + briefing IA (se ANTHROPIC_API_KEY è impostata)
- 15 minuti prima di ogni evento ad alto impatto: avviso
- Dati: feed pubblico ForexFactory (previsione e precedente; niente dato reale)

Uso:
  export TELEGRAM_TOKEN="..."          # token di BotFather
  export ANTHROPIC_API_KEY="..."       # opzionale, per il briefing
  python3 agenda_bot.py --test         # invia subito l'agenda di oggi ed esce
  python3 agenda_bot.py                # resta in esecuzione
"""
import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
CLAUDE_KEY = os.environ.get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = "claude-sonnet-5-5"

FEED = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
TZ = ZoneInfo("Europe/Rome")
CURRENCIES = {"USD", "EUR", "GBP"}      # aggiungi "JPY", "CNY"... se ti servono
IMPACTS = {"High", "Medium"}
DAILY_HOUR, DAILY_MIN = 7, 30
ALERT_MINUTES = 15
REFRESH_SECONDS = 3600                  # il feed ha limiti di richieste: non scendere sotto

ICON = {"High": "🔴", "Medium": "🟠"}


def send(text):
    r = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text[:4000]},
        timeout=20,
    )
    r.raise_for_status()


CACHE = "feed_cache.json"


def load_feed():
    """Usa la copia locale se ha meno di ~55 minuti, per non stressare il feed."""
    if os.path.exists(CACHE) and time.time() - os.path.getmtime(CACHE) < 3300:
        with open(CACHE) as f:
            return json.load(f)
    try:
        r = requests.get(FEED, timeout=20, headers={"User-Agent": "agenda-macro/1.0"})
        r.raise_for_status()
        data = r.json()
        with open(CACHE, "w") as f:
            json.dump(data, f)
        return data
    except Exception:
        if os.path.exists(CACHE):
            with open(CACHE) as f:
                return json.load(f)
        raise


def fetch_events():
    out = []
    for e in load_feed():
        if e.get("country") not in CURRENCIES or e.get("impact") not in IMPACTS:
            continue
        try:
            dt = datetime.fromisoformat(e["date"]).astimezone(TZ)
        except (KeyError, ValueError):
            continue
        out.append({
            "dt": dt,
            "cur": e["country"],
            "title": e.get("title", "?"),
            "impact": e["impact"],
            "forecast": e.get("forecast") or "",
            "previous": e.get("previous") or "",
        })
    return sorted(out, key=lambda x: x["dt"])


def fmt(e):
    line = f"{e['dt']:%H:%M} {ICON[e['impact']]} {e['cur']} {e['title']}"
    extra = []
    if e["forecast"]:
        extra.append(f"att. {e['forecast']}")
    if e["previous"]:
        extra.append(f"prec. {e['previous']}")
    return line + (f" ({', '.join(extra)})" if extra else "")


def today_events(events, day):
    return [e for e in events if e["dt"].date() == day]


def briefing(evs):
    if not CLAUDE_KEY or not evs:
        return ""
    data = "\n".join(fmt(e) for e in evs)
    prompt = (
        "Sei un analista macro per un trader retail italiano che opera su indici USA, "
        "oro, petrolio e forex. Usa SOLO gli eventi qui sotto, senza inventare valori. "
        "In italiano, massimo 100 parole, elenco breve: gli eventi che contano di più, "
        "e come una sorpresa potrebbe muovere indici, oro e dollaro. "
        "Chiudi con: non è consulenza finanziaria.\n\n" + data
    )
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": CLAUDE_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={"model": CLAUDE_MODEL, "max_tokens": 500,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=60,
        )
        r.raise_for_status()
        return "\n\n🤖 " + "".join(
            b.get("text", "") for b in r.json()["content"]
        ).strip()
    except Exception as ex:  # il briefing è opzionale
        print("Briefing non disponibile:", ex)
        return ""


def daily_message(events, day):
    evs = today_events(events, day)
    if not evs:
        return f"📅 {day:%d/%m}: nessun evento rilevante in agenda."
    return f"📅 Agenda {day:%d/%m} (ora di Roma)\n\n" + "\n".join(fmt(e) for e in evs) + briefing(evs)


def main():
    now = datetime.now(TZ)
    if "--test" in sys.argv:
        send(daily_message(fetch_events(), now.date()))
        print("Inviato.")
        return

    if "--once" in sys.argv:  # modalità senza stato, per GitHub Actions (ogni 10 minuti)
        events = fetch_events()
        if (DAILY_HOUR, DAILY_MIN) <= (now.hour, now.minute) < (DAILY_HOUR, DAILY_MIN + 10):
            send(daily_message(events, now.date()))
        for e in events:
            if e["impact"] == "High" and timedelta(minutes=10) < e["dt"] - now <= timedelta(minutes=20):
                send("⏰ Tra circa 15 minuti:\n" + fmt(e))
        return

    events, last_fetch = [], 0.0
    sent_daily, alerted = None, set()
    print("Bot avviato.")
    while True:
        now = datetime.now(TZ)
        if time.time() - last_fetch > REFRESH_SECONDS:
            try:
                events = fetch_events()
                last_fetch = time.time()
            except Exception as ex:
                print("Errore feed:", ex)
                last_fetch = time.time() - REFRESH_SECONDS + 600  # riprova tra 10 minuti
        try:
            if sent_daily != now.date() and (now.hour, now.minute) >= (DAILY_HOUR, DAILY_MIN):
                send(daily_message(events, now.date()))
                sent_daily = now.date()
            for e in events:
                key = (e["dt"], e["title"], e["cur"])
                if e["impact"] == "High" and key not in alerted \
                        and timedelta(0) < e["dt"] - now <= timedelta(minutes=ALERT_MINUTES):
                    send("⏰ Tra 15 minuti:\n" + fmt(e))
                    alerted.add(key)
        except Exception as ex:
            print("Errore invio:", ex)
        time.sleep(30)


if __name__ == "__main__":
    main()
          
