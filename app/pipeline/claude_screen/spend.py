# -*- coding: utf-8 -*-
"""What this app has spent on Claude, counted from the tokens the API reports back.

Anthropic does not tell an ordinary API key what the account's balance is -- that lives
behind the organisation Admin API, which needs a different kind of key the user does not have.
What can be known exactly is what THIS app spent, because every response says how many tokens
it used. So the app keeps its own ledger: every call adds its tokens and their price to
claude_spend.json, and the Health Check reads the total back.

Written the way the Jooble counter is (sources_apis._record_jooble_usage): best-effort, never
raising into a search. A failure to write the ledger must not cost a filter run.

Prices are per million tokens, from Anthropic's published rates. Batch requests are half
price, cache writes cost 25% more than fresh input, and cache reads cost a tenth -- which is
why the batch path exists at all, and why the ledger has to keep them apart to be honest.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime

# model name -> (input, output) US dollars per million tokens
_PRICES = {
    'claude-haiku-4-5': (1.00, 5.00),
    'claude-haiku-4': (0.80, 4.00),
    'claude-3-5-haiku': (0.80, 4.00),
    'claude-sonnet-5': (3.00, 15.00),
    'claude-sonnet-4': (3.00, 15.00),
    'claude-opus-5': (15.00, 75.00),
    'claude-opus-4': (15.00, 75.00),
}
_FALLBACK_PRICE = (1.00, 5.00)

_CACHE_WRITE_MULTIPLIER = 1.25
_CACHE_READ_MULTIPLIER = 0.10
_BATCH_MULTIPLIER = 0.50

_LOCK = threading.Lock()


def _price_for(model: str) -> tuple:
    name = str(model or '').lower()
    for prefix, price in _PRICES.items():
        if name.startswith(prefix):
            return price
    return _FALLBACK_PRICE


def _path():
    from app import storage
    return storage.DATA_DIR / 'claude_spend.json'


def _read() -> dict:
    try:
        path = _path()
        if not path.exists():
            return {}
        loaded = json.loads(path.read_text(encoding='utf-8'))
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def cost_of(model: str, usage, batch: bool = False) -> float:
    """Dollars for one response, from its own usage object. 0.0 if it says nothing."""
    if usage is None:
        return 0.0
    read = lambda name: int(getattr(usage, name, 0) or 0)  # noqa: E731
    input_price, output_price = _price_for(model)
    fresh_input = read('input_tokens')
    cache_write = read('cache_creation_input_tokens')
    cache_read = read('cache_read_input_tokens')
    output = read('output_tokens')
    dollars = (
        fresh_input * input_price
        + cache_write * input_price * _CACHE_WRITE_MULTIPLIER
        + cache_read * input_price * _CACHE_READ_MULTIPLIER
        + output * output_price
    ) / 1_000_000.0
    return dollars * (_BATCH_MULTIPLIER if batch else 1.0)


def record(model: str, usage, batch: bool = False, listings: int = 0) -> float:
    """Adds one response to the ledger. Returns what it cost. Never raises."""
    try:
        dollars = cost_of(model, usage, batch)
        if not dollars:
            return 0.0
        month = datetime.now().strftime('%Y-%m')
        with _LOCK:
            ledger = _read()
            ledger['total_usd'] = round(float(ledger.get('total_usd') or 0.0) + dollars, 6)
            ledger['calls'] = int(ledger.get('calls') or 0) + 1
            ledger['listings'] = int(ledger.get('listings') or 0) + max(listings, 0)
            months = ledger.setdefault('by_month', {})
            months[month] = round(float(months.get(month) or 0.0) + dollars, 6)
            # The most recent Filter run, so the Health Check can say what one costs now
            # rather than only what everything has cost since the app was installed.
            run = ledger.setdefault('current_run', {'usd': 0.0, 'listings': 0, 'calls': 0})
            run['usd'] = round(float(run.get('usd') or 0.0) + dollars, 6)
            run['listings'] = int(run.get('listings') or 0) + max(listings, 0)
            run['calls'] = int(run.get('calls') or 0) + 1
            run['at'] = datetime.now().isoformat(timespec='seconds')
            path = _path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(ledger, indent=2), encoding='utf-8')
        return dollars
    except Exception:
        return 0.0


def start_run() -> None:
    """Called when a Filter begins, so `current_run` measures this run and not the last."""
    try:
        with _LOCK:
            ledger = _read()
            previous = ledger.get('current_run')
            if previous and previous.get('usd'):
                ledger['last_run'] = previous
            ledger['current_run'] = {'usd': 0.0, 'listings': 0, 'calls': 0,
                                     'at': datetime.now().isoformat(timespec='seconds')}
            path = _path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(ledger, indent=2), encoding='utf-8')
    except Exception:
        pass


def summary() -> dict:
    """What the Health Check reports: lifetime, this month, and the last finished run."""
    ledger = _read()
    month = datetime.now().strftime('%Y-%m')
    last = ledger.get('last_run') or ledger.get('current_run') or {}
    per_listing = 0.0
    if last.get('listings'):
        per_listing = float(last.get('usd') or 0.0) / float(last['listings'])
    return {
        'total_usd': float(ledger.get('total_usd') or 0.0),
        'month_usd': float((ledger.get('by_month') or {}).get(month) or 0.0),
        'calls': int(ledger.get('calls') or 0),
        'listings': int(ledger.get('listings') or 0),
        'last_run_usd': float(last.get('usd') or 0.0),
        'last_run_listings': int(last.get('listings') or 0),
        'per_listing_usd': per_listing,
    }
