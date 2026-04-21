import os
import re
import logging
from datetime import datetime

import anthropic
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

SECTORS = [
    "Defense & Aerospace",
    "Tech & AI Infra",
    "Industrials & Automation",
    "Energy & Commodities",
    "Banks & Financials",
    "Consumer & Retail",
]


def build_system_prompt():
    """Static portion of the prompt — eligible for prompt caching."""
    sectors_list = "\n".join(f"- {s}" for s in SECTORS)
    return f"""You are a global equity analyst writing a daily trading newsletter covering European and US equities.

Your edge is finding stocks that are NOT in the mainstream conversation — overlooked mid-caps, under-covered names on LSE, XETRA, or Euronext, companies benefiting from a structural shift before the crowd notices.

IMPORTANT CONSTRAINT: Only recommend stocks available on Trading 212 — US (NYSE/NASDAQ), UK (LSE), and European (XETRA, Euronext) exchanges only. Do NOT pick ASX, TSE, HKEX, Korean, or Chinese stocks.

You will be given:
1. Live index prices (verified facts — do not contradict)
2. Today's market headlines fetched from financial news feeds

Use the provided headlines as your primary news source. Base all catalyst claims on the headlines given — do not invent news.

Produce EXACTLY these sections with EXACTLY these markdown headers:

## The Macro Pulse
3 sentences on today's global market sentiment based on the headlines and index moves provided. End with exactly one of:
**SENTIMENT: BULLISH**
**SENTIMENT: BEARISH**
**SENTIMENT: NEUTRAL**

## 48-Hour Catalyst Calendar
Exactly 3 specific events from the headlines happening today or tomorrow that will move markets:
- **[EVENT NAME]** — [date/time + timezone if known] — [why it moves prices]

## The Watchlist — 3 High-Conviction Trades
Find 3 stocks with a clear catalyst from the headlines provided. STRICT: only NYSE/NASDAQ, LSE, XETRA, or Euronext. Aim for at least one European name. Prioritise under-covered mid-caps over mega-caps.

**Trade 1: [COMPANY NAME] ([TICKER])**
- **Catalyst:** [specific news from the headlines provided]
- **The Play:** [long or short, thesis in one sentence]
- **Entry Zone:** [price range with context]
- **Upside Trigger:** [what confirms the trade]
- **Confidence Score:** [X/10] — [one-line rationale]
- **Risk:** [one specific downside scenario]

**Trade 2: [COMPANY NAME] ([TICKER])**
[same structure]

**Trade 3: [COMPANY NAME] ([TICKER])**
[same structure]

## Sector Snapshots
For each sector below, write exactly 2 sentences: current momentum + the key catalyst or risk to watch. Reference specific companies or data points from the headlines.

{sectors_list}

Format each as:
**[SECTOR NAME]:** [2-sentence snapshot]

## Contradiction Check
Check each trade against the macro sentiment. Flag conflicts explicitly. If all align, write: "All trade ideas align with the macro sentiment."

Rules:
- Every catalyst claim must reference the headlines provided — no invented news
- Anchor entry zones to real prices where available
- No padding — every sentence must contain a specific, actionable insight"""


def extract_sentiment(content):
    match = re.search(r"SENTIMENT:\s*(BULLISH|BEARISH|NEUTRAL)", content, re.IGNORECASE)
    return match.group(1).upper() if match else "NEUTRAL"


def extract_picks(content):
    picks = []
    for match in re.finditer(r"\*\*Trade \d+:\s*([^\(\*]+)\(([^\)]+)\)\*\*", content):
        company = match.group(1).strip().rstrip(": ")
        ticker  = match.group(2).strip()
        picks.append({"company": company, "ticker": ticker})
    return picks[:3]


def generate_newsletter(market_data_text, headlines_text, scorecard_text=""):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set in the environment.")

    client = anthropic.Anthropic(api_key=api_key)

    today = datetime.now().strftime("%A, %B %d, %Y")
    scorecard_section = f"\nSCORECARD FROM PREVIOUS NEWSLETTER:\n{scorecard_text}\n" if scorecard_text else ""

    user_message = (
        f"Today is {today}.{scorecard_section}\n\n"
        f"{market_data_text}\n\n"
        f"{headlines_text}\n\n"
        "Based on the index data and headlines above, write the full newsletter now."
    )

    logger.info("Calling Claude API (claude-sonnet-4-5, prompt caching enabled) …")
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=3000,
        temperature=0.1,
        system=[
            {
                "type": "text",
                "text": build_system_prompt(),
                "cache_control": {"type": "ephemeral"},  # cache the static system prompt
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )

    cache_info = getattr(response.usage, "cache_read_input_tokens", 0)
    logger.info(f"Cache read tokens: {cache_info} | Total input: {response.usage.input_tokens}")

    content_parts = [
        block.text for block in response.content
        if hasattr(block, "type") and block.type == "text"
    ]
    full_content = "\n".join(content_parts).strip()
    if not full_content:
        raise RuntimeError("Claude returned an empty response.")
    return full_content
