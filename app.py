import logging
import os
import threading
from datetime import datetime

import yfinance as yf
from flask import Flask, jsonify, render_template, request

from data_fetcher import fetch_market_data, fetch_news_headlines, format_market_data_for_prompt, format_headlines_for_prompt
from database import (
    get_last_scored_picks,
    get_latest_newsletter,
    get_newsletter_picks,
    get_newsletters,
    get_unscored_picks,
    init_db,
    save_newsletter,
    score_pick,
)
from newsletter_generator import extract_picks, extract_sentiment, generate_newsletter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

_pipeline_state = {"running": False, "step": "", "error": "", "done": False}
_pipeline_lock  = threading.Lock()

NEWSLETTERS_DIR = "newsletters"
os.makedirs(NEWSLETTERS_DIR, exist_ok=True)


def _set_state(step="", error="", running=True, done=False):
    with _pipeline_lock:
        _pipeline_state.update(step=step, error=error, running=running, done=done)


def _build_scorecard_text(picks):
    if not picks:
        return ""
    lines = []
    for p in picks:
        entry = p.get("entry_price")
        exit_p = p.get("exit_price")
        pnl   = p.get("pnl_pct")
        lines.append(
            f"  {p['company']} ({p['ticker']}) | "
            f"entry {f'{entry:.2f}' if entry else 'N/A'} → "
            f"exit {f'{exit_p:.2f}' if exit_p else 'N/A'} | "
            f"P&L: {f'{pnl:+.2f}%' if pnl is not None else 'pending'}"
        )
    return "\n".join(lines)


def _score_unscored_picks():
    for pick in get_unscored_picks():
        try:
            hist = yf.Ticker(pick["ticker"]).history(period="2d")
            if hist.empty:
                continue
            current = float(hist["Close"].iloc[-1])
            entry   = pick.get("entry_price")
            pnl_pct = ((current - entry) / entry * 100) if (entry and entry > 0) else 0.0
            score_pick(pick["id"], current, pnl_pct)
            logger.info(f"Scored {pick['ticker']}: {pnl_pct:+.2f}%")
        except Exception as e:
            logger.warning(f"Could not score {pick['ticker']}: {e}")


def run_pipeline():
    try:
        _set_state("Scoring previous picks…")
        _score_unscored_picks()

        _set_state("Fetching live index data…")
        market_data = fetch_market_data()
        market_data_text = format_market_data_for_prompt(market_data)

        _set_state("Fetching news headlines…")
        headlines = fetch_news_headlines()
        headlines_text = format_headlines_for_prompt(headlines)
        logger.info(f"Fetched {len(headlines)} headlines")

        _set_state("Preparing scorecard…")
        scorecard_text = _build_scorecard_text(get_last_scored_picks())

        _set_state("Calling Claude API (generating newsletter)…")
        content = generate_newsletter(market_data_text, headlines_text, scorecard_text)

        _set_state("Saving newsletter…")
        sentiment = extract_sentiment(content)
        picks     = extract_picks(content)

        newsletter_id = save_newsletter(content, sentiment, None, None, picks)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        path = f"{NEWSLETTERS_DIR}/newsletter_{timestamp}.md"
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Trading Newsletter — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n\n{content}")

        logger.info(f"Newsletter saved: {path} (id={newsletter_id})")
        _set_state("Done", running=False, done=True)

    except Exception as e:
        logger.exception("Pipeline error")
        _set_state(step="", error=str(e), running=False, done=False)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    with _pipeline_lock:
        if _pipeline_state["running"]:
            return jsonify({"error": "Pipeline already running"}), 409
    _set_state("Starting…", running=True, done=False, error="")
    threading.Thread(target=run_pipeline, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/status")
def status():
    with _pipeline_lock:
        return jsonify(dict(_pipeline_state))


@app.route("/latest")
def latest():
    newsletter = get_latest_newsletter()
    if not newsletter:
        return jsonify({"newsletter": None})
    newsletter["picks"] = get_newsletter_picks(newsletter["id"])
    return jsonify({"newsletter": newsletter})


@app.route("/history")
def history():
    newsletters = get_newsletters(limit=30)
    for n in newsletters:
        n["picks"] = get_newsletter_picks(n["id"])
    return jsonify({"newsletters": newsletters})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8080, debug=False, threaded=True)
