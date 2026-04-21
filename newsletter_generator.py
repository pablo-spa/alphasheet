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


def build_system_prompt(scorecard_text=""):
    today = datetime.now().strftime("%A, %B %d, %Y")
    scorecard_section = ""
    if scorecard_text:
        scorecard_section = f"\nSCORECARD FROM PREVIOUS NEWSLETTER:\n{scorecard_text}\n"

    sectors_list = "\n".join(f"- {s}" for s in SECTORS)

    return f"""You are a global equity analyst writing a daily trading newsletter. Today is {today}.

Your edge is finding stocks that are NOT in the mainstream conversation — overlooked mid-caps, under-covered names on European or Asian exchanges, companies benefiting from a structural shift before the crowd notices. Avoid obvious mega-caps unless the catalyst is genuinely exceptional and non-consensus.

IMPORTANT: Use web_search extensively — search for today's earnings surprises, analyst upgrades, unusual volume, M&A rumors, policy shifts, and macro catalysts. Prioritise fresh, actionable intelligence over well-known narratives.

Markets macro context: DAX, FTSE 100, CAC 40, S&P 500, NASDAQ, Nikkei 225, Hang Seng, Shanghai, KOSPI, ASX 200.
{scorecard_section}
Produce EXACTLY these sections with EXACTLY these markdown headers:

## The Macro Pulse
3 sentences covering global sentiment today — include Western and Asian dynamics. End with exactly one of:
**SENTIMENT: BULLISH**
**SENTIMENT: BEARISH**
**SENTIMENT: NEUTRAL**

## 48-Hour Catalyst Calendar
Exactly 3 specific events today or tomorrow that will move markets:
- **[EVENT NAME]** — [date/time + timezone] — [why it moves prices]

## The Watchlist — 3 High-Conviction Trades
Find 3 stocks with a clear catalyst discovered via web search. Prioritise:
- Under-covered names on LSE, XETRA, Euronext, TSE, HKEX, ASX, or mid-cap US
- Names reacting to a fresh catalyst (earnings, upgrade, policy, M&A) that isn't yet widely priced in
- Diverse geographies — do not pick 3 US stocks

**Trade 1: [COMPANY NAME] ([TICKER])**
- **Catalyst:** [specific news + source]
- **The Play:** [long or short, thesis in one sentence]
- **Entry Zone:** [price range with current price context]
- **Upside Trigger:** [what confirms the trade]
- **Confidence Score:** [X/10] — [one-line rationale]
- **Risk:** [one specific downside scenario]

**Trade 2: [COMPANY NAME] ([TICKER])**
[same structure]

**Trade 3: [COMPANY NAME] ([TICKER])**
[same structure]

## Sector Snapshots
For each sector below, write exactly 2 sentences: current momentum + the key catalyst or risk to watch. Name specific companies, events, or data points — no vague statements.

{sectors_list}

Format each as:
**[SECTOR NAME]:** [2-sentence snapshot]

## Contradiction Check
Check each trade against the macro sentiment. Flag conflicts explicitly. If all align, write: "All trade ideas align with the macro sentiment."

Rules:
- No padding — every sentence must contain a specific, actionable insight
- Anchor entry zones to real prices (use live index data as context; for individual stocks use web search to get current prices)
- The best ideas are the ones other newsletters aren't writing about today"""


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


def generate_newsletter(market_data_text, scorecard_text=""):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set in the environment.")

    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = build_system_prompt(scorecard_text)

    user_message = (
        "Today's live index data — treat these as verified facts:\n\n"
        f"{market_data_text}\n\n"
        "Use web_search to find today's best overlooked opportunities, breaking news, and macro catalysts. "
        "Then write the full newsletter. Prioritise non-obvious, under-covered stocks with fresh catalysts."
    )

    logger.info("Calling Claude API (claude-sonnet-4-5) …")
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4096,
        temperature=0.1,
        system=system_prompt,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": user_message}],
    )

    content_parts = [
        block.text for block in response.content
        if hasattr(block, "type") and block.type == "text"
    ]
    full_content = "\n".join(content_parts).strip()
    if not full_content:
        raise RuntimeError("Claude returned an empty response.")
    return full_content
