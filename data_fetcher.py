import logging
import yfinance as yf
from config import INDICES

logger = logging.getLogger(__name__)


def fetch_market_data():
    data = {"indices": [], "errors": []}

    for ticker, name in INDICES:
        entry = _fetch_ticker(ticker, name)
        if entry:
            data["indices"].append(entry)
        else:
            data["errors"].append(f"Could not fetch {name} ({ticker})")

    return data


def _fetch_ticker(ticker, name):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if hist.empty:
            logger.warning(f"No data returned for {ticker}")
            return None
        last_close = float(hist["Close"].iloc[-1])
        if len(hist) >= 2:
            prev_close = float(hist["Close"].iloc[-2])
            change_pct = ((last_close - prev_close) / prev_close) * 100
        else:
            change_pct = 0.0
        return {
            "ticker": ticker,
            "name": name,
            "price": round(last_close, 2),
            "change_pct": round(change_pct, 2),
        }
    except Exception as e:
        logger.warning(f"Failed to fetch {ticker}: {e}")
        return None


def format_market_data_for_prompt(data):
    lines = ["=== LIVE INDEX DATA (verified facts — do not contradict) ===", ""]

    for item in data["indices"]:
        arrow = "▲" if item["change_pct"] >= 0 else "▼"
        lines.append(
            f"  {item['name']} ({item['ticker']}): {item['price']:,.2f}  {arrow}{abs(item['change_pct']):.2f}%"
        )

    if data["errors"]:
        lines.append("")
        lines.append("DATA UNAVAILABLE (use web search):")
        for err in data["errors"]:
            lines.append(f"  - {err}")

    lines.append("")
    lines.append("=== END INDEX DATA ===")
    return "\n".join(lines)
