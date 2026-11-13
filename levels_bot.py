import os, sys, json, requests
from datetime import datetime, timezone
import yfinance as yf

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
ASSETS = {
    # Indici
    "NQ=F": "US100 (Nasdaq 100)", "^GDAXI": "Germania (DAX)",
    # Metalli
    "GC=F": "Gold", "SI=F": "Silver",
    # Forex: major
    "EURUSD=X": "EUR/USD", "GBPUSD=X": "GBP/USD", "USDJPY=X": "USD/JPY",
    "USDCHF=X": "USD/CHF", "AUDUSD=X": "AUD/USD", "USDCAD=X": "USD/CAD",
    "NZDUSD=X": "NZD/USD",
    # Forex: cross principali
    "EURGBP=X": "EUR/GBP", "EURJPY=X
