"""
proposer.py — generates optimization proposals for each deal using Claude.

Inputs per deal:  output/<slug>/audit.json + research.json
Output per deal:  output/<slug>/proposal.md

Usage:
    python3 proposer.py                    # all deals with both audit + research
    python3 proposer.py --slug renew-cozy-spa
    python3 proposer.py --force            # regenerate already-done proposals
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
from dotenv import dotenv_values

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output"))
MODEL      = "claude-sonnet-4-6"


# ── Prompt ────────────────────────────────────────────────────────────────────

def build_prompt(slug: str, audit: dict, research: dict) -> str:
    # Audit digest
    merchant  = audit.get("merchant_name") or slug
    title     = audit.get("title") or ""
    city      = research.get("city") or "the city"
    category  = research.get("category") or "local services"
    rating    = audit.get("avg_rating")
    reviews   = audit.get("review_count")
    bought    = audit.get("urgency_bought")
    badges    = ", ".join(audit.get("badges") or []) or "none"
    amenities = ", ".join(audit.get("amenities") or []) or "none"
    highlights_text = audit.get("highlights_text") or "(none)"
    about_text = (audit.get("about_deal_text") or "")[:400]
    fine_print = "; ".join(audit.get("fine_print") or []) or "(none)"
    has_faqs   = len(audit.get("faqs") or []) > 0
    image_count = audit.get("image_count") or 0
    script_count = audit.get("script_count") or 0
    is_giftable = audit.get("is_giftable")
    urgency_msg = audit.get("urgency_message") or "(none)"

    seo = audit.get("seo") or {}
    meta_title = seo.get("meta_title") or "(none)"
    meta_desc  = seo.get("meta_description") or "(none)"
    h1         = seo.get("h1") or "(none)"
    h2s        = ", ".join(seo.get("h2s") or [])
    schema     = ", ".join(seo.get("schema_types") or [])
    noindex    = seo.get("noindex", False)

    review_dist = audit.get("review_distribution") or {}
    five_pct  = review_dist.get("five_star_pct", "?")
    one_pct   = review_dist.get("one_star_pct", "?")

    options = audit.get("pricing_options") or []
    pricing_lines = []
    for o in options[:6]:
        orig = o.get("original_price")
        deal = o.get("deal_price")
        disc = o.get("discount_pct")
        sold = o.get("sold_quantity") or ""
        pricing_lines.append(f"  - {o['label']}: ~~${orig}~~ → ${deal} ({disc}% off) {sold}")
    pricing_summary = "\n".join(pricing_lines)

    quotes = audit.get("review_quotes") or []
    quote_lines = [f"  - [{q.get('rating')}★] \"{q.get('text','')[:150]}\"" for q in quotes[:5]]
    quotes_summary = "\n".join(quote_lines) or "  (none)"

    # Research digest
    comp      = research.get("competitor_pricing") or {}
    rep       = research.get("merchant_reputation") or {}
    val       = research.get("deal_value") or {}
    gaps      = research.get("content_gaps") or []
    sources   = research.get("sources") or []

    comp_notes = comp.get("notes") or ""
    comp_list  = "\n".join(
        f"  - {c.get('name')}: {c.get('price_range')} — {c.get('notes','')}"
        for c in (comp.get("competitors") or [])[:5]
    )
    yelp_rating   = rep.get("yelp_rating")
    google_rating = rep.get("google_rating")
    pos_themes    = "\n".join(f"  - {t}" for t in (rep.get("positive_themes") or [])[:5])
    neg_themes    = "\n".join(f"  - {t}" for t in (rep.get("negative_themes") or [])[:4])
    rep_quotes    = "\n".join(
        f"  - [{q.get('sentiment')}] \"{q.get('quote','')[:150]}\" ({q.get('source','')})"
        for q in (rep.get("representative_quotes") or [])[:4]
    )
    is_good_deal = val.get("is_good_deal")
    groupon_price = val.get("groupon_price")
    comp_avg = val.get("competitor_avg_price")
    orig_credibility = val.get("original_price_credibility","unknown")
    deal_assessment = val.get("assessment","")

    high_gaps  = [g for g in gaps if g.get("priority") == "high"]
    med_gaps   = [g for g in gaps if g.get("priority") == "medium"]
    gaps_lines = "\n".join(
        f"  - [{g.get('priority','?').upper()}] {g.get('gap')}: {g.get('why_it_matters','')}"
        for g in (high_gaps + med_gaps)[:8]
    )

    source_urls = "\n".join(f"  - {s.get('url','')}" for s in sources[:6])

    return f"""You are a senior conversion optimization consultant at Groupon's CEO office.
Produce a specific, actionable optimization proposal. Every recommendation must cite real evidence. Be concise — ruthlessly prioritize. Total response must fit in ~300 lines.

## Deal: {merchant} ({city}) — {category}
- Title: {title}
- Rating: {rating}/5 ({reviews} reviews, {five_pct}% five-star) | Sold: {bought} | Urgency: {urgency_msg}
- Badges: {badges} | Amenities: {amenities} | Giftable: {is_giftable} | FAQs: {has_faqs}
- Images: {image_count} | Scripts: {script_count}

## Current Content
H1: {h1}
Highlights: {highlights_text}
About (excerpt): {about_text}
Fine print: {fine_print}

## Pricing
{pricing_summary}

## SEO
Meta title: {meta_title}
Meta desc: {meta_desc}
H2s: {h2s}
Schema: {schema} | Noindex: {noindex}

## Groupon Customer Quotes
{quotes_summary}

## Research Findings
Competitor pricing: {comp_notes}
{comp_list}

Yelp: {yelp_rating} | Google: {google_rating}
Positive themes: {'; '.join((rep.get('positive_themes') or [])[:4])}
Negative themes: {'; '.join((rep.get('negative_themes') or [])[:3])}
External quotes: {'; '.join(q.get('quote','')[:80] for q in (rep.get('representative_quotes') or [])[:3])}

Deal verdict: {"✅ Good deal" if is_good_deal else "❌ Not a good deal" if is_good_deal is False else "❓ Unclear"} | Groupon: ${groupon_price} vs competitor avg: ${comp_avg} | Original price: {orig_credibility}
{deal_assessment}

Top content gaps:
{gaps_lines}

---

Write the proposal using EXACTLY this structure. Keep each section tight (3–8 lines max, except rewrites). Include actual copy, not instructions.

# Optimization Proposal: {merchant}

## Executive Summary
(3 sentences: biggest strength, biggest weakness, highest-leverage fix)

## 1. Title Rewrite _(High Impact)_
**Current:** ...
**Proposed:** ...
**Why:** (1–2 lines, cite evidence)

## 2. Pricing & Value Framing _(High Impact)_
**Problem:** (1 line)
**Fix:** (proposed copy + 1-line rationale citing competitor data)

## 3. Highlights Rewrite _(High Impact)_
**Current:** ...
**Proposed:** (full bullet rewrite — 6–8 bullets, include actual copy)
**Why:** (2 lines citing review quotes or gaps)

## 4. Top 3 Missing Content Additions _(High Impact)_
For each: **[Title]** — proposed copy (2–4 lines) + evidence citation.

## 5. SEO _(Medium Impact)_
**Meta title:** (proposed)
**Meta desc:** (proposed, ≤155 chars)
**H1:** (proposed if changed)
**Key issues:** (2–3 bullet points)

## 6. Images _(Medium Impact)_
(4–5 bullets: what to add/change and why, citing review evidence)

## 7. Trust Signals _(Medium Impact)_
Present: ... | Missing: ...
Top 2 additions with proposed copy.

## 8. Competitive Positioning _(Medium Impact)_
(2–3 lines: specific angle vs named competitors with copy example)

## Priority Ranking

| # | Change | Impact | Effort | Evidence |
|---|--------|--------|--------|----------|
(8 rows, one per recommendation above)

## What to Do First
(1 short paragraph: the immediate next step — specific and actionable, no time references like "30 minutes")
"""


# ── Claude call ───────────────────────────────────────────────────────────────

def run_proposal(slug: str, audit: dict, research: dict) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY") or dotenv_values(".env").get("ANTHROPIC_API_KEY")
    client  = anthropic.Anthropic(api_key=api_key)
    prompt  = build_prompt(slug, audit, research)

    for attempt in range(1, 4):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=8000,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text

        except anthropic.RateLimitError:
            wait = 60 * attempt
            print(f"  [{slug}] rate limit (attempt {attempt}) — waiting {wait}s...")
            time.sleep(wait)
        except anthropic.APIStatusError as e:
            if e.status_code == 529:
                wait = 30 * attempt
                print(f"  [{slug}] overloaded (attempt {attempt}) — waiting {wait}s...")
                time.sleep(wait)
            else:
                raise

    raise RuntimeError(f"All retries exhausted for {slug}")


# ── Orchestrator ──────────────────────────────────────────────────────────────

def process_deal(slug: str, force: bool) -> bool:
    out_dir       = OUTPUT_DIR / slug
    audit_path    = out_dir / "audit.json"
    research_path = out_dir / "research.json"
    proposal_path = out_dir / "proposal.md"

    if not audit_path.exists():
        print(f"  {slug}: SKIP — no audit.json")
        return False
    if not research_path.exists():
        print(f"  {slug}: SKIP — no research.json (researcher.py still running?)")
        return False
    if proposal_path.exists() and not force:
        print(f"  {slug}: already done — skipping (--force to redo)")
        return False

    audit    = json.loads(audit_path.read_text())
    research = json.loads(research_path.read_text())

    print(f"  {slug}: generating proposal...")
    t0 = time.time()
    proposal_md = run_proposal(slug, audit, research)
    elapsed = round(time.time() - t0, 1)

    proposal_path.write_text(proposal_md)
    print(f"  {slug}: done in {elapsed}s → proposal.md")
    return True


# ── Entrypoint ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate deal optimization proposals")
    parser.add_argument("--slug",  help="Process a single deal by slug")
    parser.add_argument("--force", action="store_true", help="Regenerate existing proposals")
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY") or dotenv_values(".env").get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    if args.slug:
        slugs = [args.slug]
    else:
        slugs = sorted([
            d.name for d in OUTPUT_DIR.iterdir()
            if (d / "audit.json").exists() and (d / "research.json").exists()
        ])

    print(f"\nGenerating proposals for {len(slugs)} deal(s)...\n")
    done = sum(1 for s in slugs if process_deal(s, args.force))
    print(f"\nDone. {done}/{len(slugs)} proposals generated.")


if __name__ == "__main__":
    main()
