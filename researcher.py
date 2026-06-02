"""
researcher.py — competitive research for each deal using Claude + web search.

For each deal:
  1. Competitor pricing in the same city
  2. Merchant reputation (Yelp/Google rating + review themes)
  3. Deal value assessment (Groupon price vs. direct / competitors)
  4. Content gaps (what's missing from the deal page)

Outputs per deal:
  output/<slug>/research.json
  output/<slug>/research_report.md

All results stored in DuckDB (deals.db).

Usage:
    python3 researcher.py                  # all deals with audit.json
    python3 researcher.py --slug renew-cozy-spa
    python3 researcher.py --limit 5
    python3 researcher.py --force          # re-research already done deals
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

import db

load_dotenv()

OUTPUT_DIR   = Path(os.getenv("OUTPUT_DIR", "output"))
CONCURRENCY  = 1   # sequential — web_search calls are token-heavy; 4 parallel hits 30k TPM limit
MODEL        = "claude-sonnet-4-6"
MAX_SEARCHES = 5   # web searches per deal


# ── City / category inference from slug + audit data ─────────────────────────

CITY_HINTS = {
    "nyc": "New York City", "new-york": "New York City",
    "chicago": "Chicago", "chi": "Chicago",
    "dc": "Washington DC", "washington": "Washington DC",
    "laurel": "Washington DC area", "alexandria": "Washington DC area",
}

# Slug → city lookup for deals that don't match keyword hints
SLUG_CITY_MAP = {
    "renew-cozy-spa": "New York City",
    "the-spa-club-3": "New York City",
    "zeno-hair-studio-18": "New York City",
    "harumi-salon-1-3": "New York City",
    "nieves-latin-dance-studio-4": "New York City",
    "body-pole-3": "New York City",
    "merrick-tire-center-1": "New York City",
    "wu-couple-spa-1": "Chicago",
    "heavenly-massage-12": "Chicago",
    "salon-1181llc-5": "Chicago",
    "xex-hair-gallery-11": "Chicago",
    "latin-rhythms-dance": "Chicago",
    "desarge-danceworld": "Chicago",
    "super-shine-car-wash-12": "Chicago",
    "illa-spa-13-17": "Washington DC",
    "black-bella-dc-body-sculpting-24": "Washington DC",
    "refills-health-goods": "Washington DC",
    "climbzone-laurel": "Washington DC area (Laurel, MD)",
    "arthur-murray-alexandria-7": "Washington DC area (Alexandria, VA)",
    "shine-my-ride-8": "Washington DC",
}

CATEGORY_HINTS = {
    "spa": "spa/wellness", "massage": "spa/wellness", "cozy": "spa/wellness",
    "salon": "health & beauty", "hair": "health & beauty", "beauty": "health & beauty",
    "sculpting": "health & beauty", "refill": "health & beauty",
    "dance": "activities", "pole": "activities", "climb": "activities", "murray": "activities",
    "tire": "automotive", "car-wash": "automotive", "shine": "automotive", "auto": "automotive",
}


def infer_city(slug: str, audit: dict) -> str:
    if slug in SLUG_CITY_MAP:
        return SLUG_CITY_MAP[slug]
    s = slug.lower()
    for hint, city in CITY_HINTS.items():
        if hint in s:
            return city
    return "the city"


def infer_category(slug: str) -> str:
    s = slug.lower()
    for hint, cat in CATEGORY_HINTS.items():
        if hint in s:
            return cat
    return "local services"


# ── Prompt ────────────────────────────────────────────────────────────────────

def build_prompt(slug: str, audit: dict, city: str, category: str) -> str:
    merchant  = audit.get("merchant_name") or slug
    title     = audit.get("title") or merchant
    rating    = audit.get("avg_rating")
    reviews   = audit.get("review_count")
    bought    = audit.get("urgency_bought")
    highlights = audit.get("highlights_text") or ""
    fine_print = "; ".join(audit.get("fine_print") or [])

    # Pricing summary
    options = audit.get("pricing_options") or []
    pricing_lines = []
    for o in options[:4]:
        orig  = o.get("original_price")
        deal  = o.get("deal_price")
        disc  = o.get("discount_pct")
        label = o.get("label", "Option")
        if orig and deal:
            pricing_lines.append(f"  - {label}: ${orig} → ${deal} ({disc}% off)")
    pricing_summary = "\n".join(pricing_lines) or "  (no pricing data)"

    return f"""You are a market research analyst helping optimize Groupon deal pages.

Research this deal and return a structured JSON report. Use web search to find REAL, CURRENT data — not guesses.

## Deal Info
- Merchant: {merchant}
- Title: {title}
- City: {city}
- Category: {category}
- Groupon Rating: {rating} ({reviews} reviews on Groupon)
- Units Sold Signal: {bought}
- Highlights on page: {highlights or "(none)"}
- Fine print: {fine_print or "(none)"}

## Pricing
{pricing_summary}

## Your Research Tasks

Search the web for each of the following. Use multiple searches as needed.

### 1. Competitor Pricing
Search for the same or equivalent service in {city}. Examples: "{category} {city} price", "{merchant} competitors {city}".
Find at least 2–3 real competitor prices. Note whether Groupon price is above/below market.

### 2. Merchant Reputation
Search for "{merchant} reviews", "{merchant} Yelp", "{merchant} Google reviews".
Extract: Yelp rating, Google rating, common positive themes (what customers love), common negative themes (complaints).
Include 1–2 direct review quotes per theme if available.

### 3. Deal Value Assessment
Based on competitor prices and direct booking price (if findable):
- Is the Groupon price actually a good deal vs booking direct?
- vs. competitors?
- Flag if the "original price" looks inflated (common Groupon issue).

### 4. Content Gaps
Based on what you found in research, what information is MISSING from the deal page that customers would want before purchasing?
Think: location details, parking, what to bring, staff credentials, before/after photos, cancellation policy, exact service inclusions, etc.

## Output Format

Return ONLY valid JSON with this exact structure (no markdown, no explanation outside the JSON):

{{
  "merchant_name": "{merchant}",
  "city": "{city}",
  "category": "{category}",
  "competitor_pricing": {{
    "low": <float or null>,
    "high": <float or null>,
    "currency": "USD",
    "notes": "<1-2 sentence summary of what competitors charge>",
    "competitors": [
      {{"name": "<business>", "price_range": "<e.g. $60-$90>", "source": "<url or site>", "notes": "<what's included>"}}
    ]
  }},
  "merchant_reputation": {{
    "yelp_rating": <float or null>,
    "yelp_review_count": <int or null>,
    "google_rating": <float or null>,
    "google_review_count": <int or null>,
    "positive_themes": ["<theme with evidence>"],
    "negative_themes": ["<theme with evidence>"],
    "representative_quotes": [
      {{"sentiment": "positive|negative", "quote": "<text>", "source": "<yelp|google|other>"}}
    ]
  }},
  "deal_value": {{
    "groupon_price": <float — lowest deal price>,
    "direct_booking_price": <float or null>,
    "competitor_avg_price": <float or null>,
    "is_good_deal": <true|false|null>,
    "discount_vs_direct": <float percentage or null>,
    "discount_vs_competitors": <float percentage or null>,
    "original_price_credibility": "credible|inflated|unknown",
    "assessment": "<2-3 sentence verdict with evidence>"
  }},
  "content_gaps": [
    {{"gap": "<what's missing>", "why_it_matters": "<customer impact>", "priority": "high|medium|low"}}
  ],
  "sources": [
    {{"title": "<page title>", "url": "<url>", "accessed_for": "<competitor|reputation|pricing>"}}
  ],
  "research_confidence": "high|medium|low",
  "research_notes": "<any caveats or limitations in the research>"
}}"""


# ── Claude call with web search ───────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """Extract the largest valid JSON object from text, handling truncation."""
    # Try full match first
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError(f"No JSON object found in response: {text[:300]}")
    raw = m.group()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Truncated JSON — try progressively shorter substrings
        for end in range(len(raw) - 1, len(raw) // 2, -1):
            candidate = raw[:end]
            # Close any open brackets
            opens   = candidate.count("{") - candidate.count("}")
            closes  = candidate.count("[") - candidate.count("]")
            patched = candidate + ("]" * max(closes, 0)) + ("}" * max(opens, 0))
            try:
                return json.loads(patched)
            except json.JSONDecodeError:
                continue
        raise ValueError("Could not recover valid JSON from truncated response")


def run_research(slug: str, audit: dict, city: str, category: str) -> dict:
    """Synchronous Claude call with exponential-backoff retry on rate limits."""
    from dotenv import dotenv_values
    api_key = os.getenv("ANTHROPIC_API_KEY") or dotenv_values(".env").get("ANTHROPIC_API_KEY")
    client  = anthropic.Anthropic(api_key=api_key)
    prompt  = build_prompt(slug, audit, city, category)
    tools   = [{"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_SEARCHES}]

    for attempt in range(1, 5):
        try:
            messages = [{"role": "user", "content": prompt}]

            # Agentic loop: keep going until Claude stops using tools
            while True:
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=4096,
                    tools=tools,
                    messages=messages,
                )
                messages.append({"role": "assistant", "content": response.content})

                if response.stop_reason != "tool_use":
                    break

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "Search completed.",
                        })
                if tool_results:
                    messages.append({"role": "user", "content": tool_results})

            final_text = "".join(
                block.text for block in response.content if hasattr(block, "text")
            )
            return _extract_json(final_text)

        except anthropic.RateLimitError as e:
            wait = 60 * attempt
            print(f"  [{slug}] rate limit hit (attempt {attempt}) — waiting {wait}s...")
            time.sleep(wait)
        except anthropic.APIStatusError as e:
            if e.status_code == 529:  # overloaded
                wait = 30 * attempt
                print(f"  [{slug}] API overloaded (attempt {attempt}) — waiting {wait}s...")
                time.sleep(wait)
            else:
                raise

    raise RuntimeError(f"All retry attempts exhausted for {slug}")


# ── Report writer ─────────────────────────────────────────────────────────────

def write_research_report(slug: str, data: dict, out_dir: Path):
    merchant = data.get("merchant_name", slug)
    city     = data.get("city", "")
    cat      = data.get("category", "")
    comp     = data.get("competitor_pricing", {})
    rep      = data.get("merchant_reputation", {})
    val      = data.get("deal_value", {})
    gaps     = data.get("content_gaps", [])
    sources  = data.get("sources", [])

    lines = [
        f"# Research Report: {merchant}",
        f"_{city} · {cat}_",
        "",
        "## Competitor Pricing",
        "",
        comp.get("notes", ""),
        "",
    ]

    for c in comp.get("competitors", []):
        lines.append(f"- **{c.get('name')}** — {c.get('price_range')} ({c.get('notes', '')})")
        if c.get("source"):
            lines.append(f"  Source: {c.get('source')}")

    lines += [
        "",
        "## Merchant Reputation",
        "",
        f"- Yelp: {rep.get('yelp_rating')} ({rep.get('yelp_review_count')} reviews)",
        f"- Google: {rep.get('google_rating')} ({rep.get('google_review_count')} reviews)",
        "",
        "**What customers love:**",
    ]
    for t in rep.get("positive_themes", []):
        lines.append(f"- {t}")

    lines += ["", "**Common complaints:**"]
    for t in rep.get("negative_themes", []):
        lines.append(f"- {t}")

    quotes = rep.get("representative_quotes", [])
    if quotes:
        lines += ["", "**Sample reviews:**"]
        for q in quotes:
            sentiment = q.get("sentiment", "")
            lines.append(f'> "{q.get("quote")}" _({sentiment}, {q.get("source")})_')

    lines += [
        "",
        "## Deal Value Assessment",
        "",
        f"- **Groupon price:** ${val.get('groupon_price')}",
        f"- **Direct booking price:** ${val.get('direct_booking_price') or 'N/A'}",
        f"- **Competitor avg:** ${val.get('competitor_avg_price') or 'N/A'}",
        f"- **Good deal?** {'✅ Yes' if val.get('is_good_deal') else '❌ No' if val.get('is_good_deal') is False else '❓ Unknown'}",
        f"- **Original price credibility:** {val.get('original_price_credibility', 'unknown')}",
        "",
        val.get("assessment", ""),
        "",
        "## Content Gaps",
        "",
    ]

    high = [g for g in gaps if g.get("priority") == "high"]
    med  = [g for g in gaps if g.get("priority") == "medium"]
    low  = [g for g in gaps if g.get("priority") == "low"]
    for priority_group, label in [(high, "🔴 High"), (med, "🟡 Medium"), (low, "⚪ Low")]:
        if priority_group:
            lines.append(f"### {label} Priority")
            for g in priority_group:
                lines.append(f"- **{g.get('gap')}** — {g.get('why_it_matters')}")
            lines.append("")

    if sources:
        lines += ["## Sources", ""]
        for s in sources:
            url = s.get("url", "")
            title = s.get("title", url)
            lines.append(f"- [{title}]({url}) _{s.get('accessed_for', '')}_")

    confidence = data.get("research_confidence", "unknown")
    notes      = data.get("research_notes", "")
    lines += [
        "",
        f"_Research confidence: **{confidence}**. {notes}_",
    ]

    (out_dir / "research_report.md").write_text("\n".join(lines))
    (out_dir / "research.json").write_text(json.dumps(data, indent=2))


# ── Per-deal orchestrator ─────────────────────────────────────────────────────

async def research_deal(slug: str, force: bool, semaphore: asyncio.Semaphore, i: int, total: int):
    out_dir      = OUTPUT_DIR / slug
    audit_path   = out_dir / "audit.json"
    research_path = out_dir / "research.json"

    if not audit_path.exists():
        print(f"[{i}/{total}] {slug}: SKIP — no audit.json (run main.py first)")
        return

    if research_path.exists() and not force:
        print(f"[{i}/{total}] {slug}: already researched — skipping (--force to redo)")
        return

    audit    = json.loads(audit_path.read_text())
    city     = infer_city(slug, audit)
    category = infer_category(slug)

    async with semaphore:
        print(f"[{i}/{total}] {slug}: researching ({city}, {category})...")
        t0 = time.time()
        try:
            # Run blocking Claude call in thread pool
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, run_research, slug, audit, city, category)
            elapsed = round(time.time() - t0, 1)

            write_research_report(slug, data, out_dir)
            db.upsert_research(slug, data)
            print(f"[{i}/{total}] {slug}: done in {elapsed}s → research.json")

        except json.JSONDecodeError as e:
            print(f"[{i}/{total}] {slug}: JSON parse error — {e}")
        except Exception as e:
            print(f"[{i}/{total}] {slug}: ERROR — {e}")


# ── Entrypoint ────────────────────────────────────────────────────────────────

async def run(slugs: list[str], force: bool):
    semaphore = asyncio.Semaphore(CONCURRENCY)
    total     = len(slugs)
    print(f"\nResearching {total} deal(s) · {CONCURRENCY} parallel · model={MODEL}\n")

    tasks = [
        research_deal(slug, force, semaphore, i, total)
        for i, slug in enumerate(slugs, 1)
    ]
    await asyncio.gather(*tasks)
    print(f"\nDone. Results in {OUTPUT_DIR}/ and deals.db")


def main():
    parser = argparse.ArgumentParser(description="Research Groupon deals")
    parser.add_argument("--slug",  help="Research a single deal by slug")
    parser.add_argument("--limit", type=int, help="Process first N deals only")
    parser.add_argument("--force", action="store_true", help="Re-research already-done deals")
    args = parser.parse_args()

    from dotenv import dotenv_values
    api_key = os.getenv("ANTHROPIC_API_KEY") or dotenv_values(".env").get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set. Add it to .env or export it.")
        sys.exit(1)

    if args.slug:
        slugs = [args.slug]
    else:
        slugs = sorted([d.name for d in OUTPUT_DIR.iterdir() if (d / "audit.json").exists()])

    if args.limit:
        slugs = slugs[: args.limit]

    asyncio.run(run(slugs, force=args.force))


if __name__ == "__main__":
    main()
