import logging
from datetime import datetime, timezone
import yfinance as yf
from config import INDICES

logger = logging.getLogger(__name__)

# Tickers used solely for news — broad market coverage across regions
NEWS_TICKERS = ["^GSPC", "^FTSE", "^GDAXI", "^N225", "^HSI", "NVDA", "MSFT", "BP.L", "SIE.DE"]


def fetch_market_data():
    data = {"indices": [], "errors": []}
    for ticker, name in INDICES:
        entry = _fetch_ticker(ticker, name)
        if entry:
            data["indices"].append(entry)
        else:
            data["errors"].append(f"Could not fetch {name} ({ticker})")
    return data


def fetch_news_headlines(max_per_ticker=3, max_total=30):
    """Fetch recent financial headlines via yfinance — free, no API key needed."""
    seen = set()
    headlines = []
    now = datetime.now(timezone.utc).timestamp()
    cutoff = now - 48 * 3600  # last 48 hours only

    for ticker in NEWS_TICKERS:
        try:
            news = yf.Ticker(ticker).news or []
            for item in news:
                title = item.get("title", "").strip()
                publisher = item.get("publisher", "")
                published = item.get("providerPublishTime", 0)
                if not title or title in seen:
                    continue
                if published and published < cutoff:
                    continue
                seen.add(title)
                age_h = int((now - published) / 3600) if published else 0
                headlines.append({
                    "title": title,
                    "publisher": publisher,
                    "age_h": age_h,
                })
                if len([h for h in headlines if h]) >= max_total:
                    break
        except Exception as e:
            logger.warning(f"News fetch failed for {ticker}: {e}")

        if len(headlines) >= max_total:
            break

    # Sort by recency
    headlines.sort(key=lambda x: x["age_h"])
    return headlines[:max_total]


def _fetch_ticker(ticker, name):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if hist.empty:
            logger.warning(f"No data returned for {ticker}")
            return None
        last_close = float(hist["Close"].iloc[-1])
        change_pct = 0.0
        if len(hist) >= 2:
            prev_close = float(hist["Close"].iloc[-2])
            change_pct = ((last_close - prev_close) / prev_close) * 100
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
        lines.append("DATA UNAVAILABLE:")
        for err in data["errors"]:
            lines.append(f"  - {err}")
    lines.append("\n=== END INDEX DATA ===")
    return "\n".join(lines)


def format_headlines_for_prompt(headlines):
    if not headlines:
        return ""
    lines = ["=== TODAY'S MARKET HEADLINES (use these as your news source) ===", ""]
    for h in headlines:
        age = f"{h['age_h']}h ago" if h["age_h"] else "recent"
        lines.append(f"  [{age}] {h['title']}  — {h['publisher']}")
    lines.append("\n=== END HEADLINES ===")
    return "\n".join(lines)
