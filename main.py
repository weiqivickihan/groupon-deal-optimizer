"""
Groupon Deal Optimizer — main pipeline entrypoint.

Usage:
    python main.py                          # process all URLs in deals.txt
    python main.py --url <url>              # process a single URL
    python main.py --limit 3               # process first N deals only
    python main.py --skip-scrape           # skip scraping, reuse audit.json cache
    python main.py --force                 # re-process already-completed deals
"""

import argparse
import asyncio
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from groupon_scraper import scrape_deal
import db


# ── Config ────────────────────────────────────────────────────────────────────

DEALS_FILE    = Path("deals.txt")
OUTPUT_DIR    = Path(os.getenv("OUTPUT_DIR", "output"))
SCRAPE_DELAY  = float(os.getenv("SCRAPE_DELAY_SECONDS", "3"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_urls(path: Path) -> list[str]:
    if not path.exists():
        print(f"ERROR: {path} not found. Create it and add one Groupon URL per line.")
        sys.exit(1)
    urls = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and line.startswith("http"):
            urls.append(line.split()[0])  # strip any trailing inline comments/annotations
    if not urls:
        print(f"ERROR: {path} has no URLs. Add at least one Groupon deal URL.")
        sys.exit(1)
    return urls


def deal_slug(url: str) -> str:
    """Extract a filesystem-safe slug from a Groupon deal URL."""
    # e.g. https://www.groupon.com/deals/renew-cozy-spa?... → renew-cozy-spa
    path = url.split("?")[0].rstrip("/")
    return path.split("/deals/")[-1] if "/deals/" in path else path.split("/")[-1]


def deal_output_dir(slug: str) -> Path:
    d = OUTPUT_DIR / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_audit(deal_data, out_dir: Path):
    import json
    data = asdict(deal_data) if hasattr(deal_data, '__dataclass_fields__') else deal_data
    (out_dir / "audit.json").write_text(json.dumps(data, indent=2))

    d = data
    seo  = d.get("seo") or {}
    dist = d.get("review_distribution") or {}

    lines = [
        f"# Deal Audit: {d.get('title') or 'Unknown'}",
        "",
        f"**Merchant:** {d.get('merchant_name') or 'N/A'}",
        f"**Category:** {' › '.join(c for c in (d.get('category_breadcrumbs') or []) if c)}",
        f"**Rating:** {d.get('avg_rating')} ({d.get('review_count')} reviews)",
        f"**Groupon Rating:** {d.get('groupon_rating')}",
        f"**Images:** {d.get('image_count')} | **Scripts:** {d.get('script_count')}",
        f"**Giftable:** {d.get('is_giftable')} | **Guarantee:** {d.get('has_guarantee')}",
        f"**Badges:** {', '.join(d.get('badges') or []) or 'none'}",
        f"**Urgency:** {d.get('urgency_bought')} bought · {d.get('urgency_message')}",
        f"**Amenities:** {', '.join(d.get('amenities') or []) or 'none'}",
        "",
        "## SEO",
        "",
        f"- **Meta title:** {seo.get('meta_title') or '_(missing)_'}",
        f"- **Meta description:** {seo.get('meta_description') or '_(missing)_'}",
        f"- **H1:** {seo.get('h1') or '_(missing)_'}",
        f"- **H2s:** {', '.join(seo.get('h2s') or [])}",
        f"- **Schema types:** {', '.join(seo.get('schema_types') or [])}",
        f"- **Noindex:** {seo.get('noindex')}",
        f"- **Canonical:** {seo.get('canonical_url') or '_(none)_'}",
        "",
        "## Pricing Options",
        "",
    ]
    for opt in d.get("pricing_options") or []:
        disc = f"{opt['discount_pct']}% off" if opt.get('discount_pct') else ""
        lines.append(f"- **{opt['label']}** — ~~${opt.get('original_price')}~~ → ${opt.get('deal_price')} {disc}")
        if opt.get("limited_sale_price"):
            lines.append(f"  - Limited sale: ${opt['limited_sale_price']} ({opt.get('limited_sale_label', '')})")
        if opt.get("promo_price"):
            lines.append(f"  - With code `{opt.get('promo_code')}`: ${opt['promo_price']}")
        if opt.get("sold_quantity"):
            lines.append(f"  - Sold: {opt['sold_quantity']}")

    lines += ["", "## Highlights", ""]
    lines.append(d.get('highlights_text') or "_(none)_")
    for h in d.get("highlights") or []:
        lines.append(f"- {h}")

    if d.get("about_deal_text"):
        lines += ["", "## About the Deal", "", d["about_deal_text"][:600]]

    lines += ["", "## Fine Print", ""]
    for fp in d.get("fine_print") or []:
        lines.append(f"- {fp}")

    if d.get("faqs"):
        lines += ["", "## FAQs", ""]
        for faq in d["faqs"]:
            lines.append(f"**Q: {faq['question']}**")
            lines.append(f"A: {faq['answer'][:300]}")
            lines.append("")

    if d.get("review_quotes"):
        lines += ["## Sample Customer Reviews", ""]
        for q in d["review_quotes"]:
            author = q.get("author") or "Customer"
            rating = "⭐" * (q.get("rating") or 0)
            lines.append(f"> {rating} \"{q['text'][:200]}\" — *{author}*")
            lines.append("")

    if dist:
        lines += ["## Review Distribution", ""]
        for star, key in [(5,"five"),(4,"four"),(3,"three"),(2,"two"),(1,"one")]:
            pct = dist.get(f"{key}_star_pct")
            if pct is not None:
                bar = "█" * (pct // 5)
                lines.append(f"- {star}★ {bar} {pct}%")

    (out_dir / "audit_summary.md").write_text("\n".join(lines))


def print_status(i: int, total: int, slug: str, status: str):
    print(f"[{i}/{total}] {slug}: {status}")


# ── Pipeline ──────────────────────────────────────────────────────────────────

async def process_deal(url: str, skip_scrape: bool, force: bool, i: int, total: int):
    import json

    slug    = deal_slug(url)
    out_dir = deal_output_dir(slug)
    audit_path = out_dir / "audit.json"

    # ── Step 1: Scrape ─────────────────────────────────────────────────────
    if skip_scrape and audit_path.exists():
        print_status(i, total, slug, "using cached audit.json")
        import dataclasses, groupon_scraper
        raw = json.loads(audit_path.read_text())
        # Reconstruct minimal DealData-like object for downstream steps
        deal_data = type("DealData", (), raw)()
    elif not force and audit_path.exists():
        print_status(i, total, slug, "already scraped — skipping (use --force to re-run)")
        return
    else:
        print_status(i, total, slug, "scraping...")
        deal_data = await scrape_deal(url)
        if deal_data.error:
            print_status(i, total, slug, f"SCRAPE ERROR: {deal_data.error}")
        write_audit(deal_data, out_dir)
        db.upsert_audit(slug, asdict(deal_data))
        print_status(i, total, slug, f"audit saved → {out_dir}/audit.json")

    # ── Step 2: Research ───────────────────────────────────────────────────
    research_path = out_dir / "research.json"
    if not research_path.exists():
        print_status(i, total, slug, "research — run: python3 researcher.py")

    # ── Step 3: Proposal ───────────────────────────────────────────────────
    proposal_path = out_dir / "proposal.md"
    if not proposal_path.exists():
        print_status(i, total, slug, "proposal — run: python3 proposer.py")


async def run(urls: list[str], skip_scrape: bool, force: bool):
    total = len(urls)
    print(f"\nProcessing {total} deal(s) → {OUTPUT_DIR}/\n")

    for i, url in enumerate(urls, 1):
        await process_deal(url, skip_scrape, force, i, total)
        if i < total:
            time.sleep(SCRAPE_DELAY)

    print(f"\nDone. Outputs in {OUTPUT_DIR}/")


# ── Entrypoint ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Groupon Deal Optimizer pipeline")
    parser.add_argument("--url",         help="Process a single URL instead of deals.txt")
    parser.add_argument("--limit",       type=int, help="Process only the first N deals")
    parser.add_argument("--skip-scrape", action="store_true", help="Reuse cached audit.json")
    parser.add_argument("--force",       action="store_true", help="Re-process already-done deals")
    args = parser.parse_args()

    if args.url:
        urls = [args.url]
    else:
        urls = load_urls(DEALS_FILE)

    if args.limit:
        urls = urls[: args.limit]

    asyncio.run(run(urls, skip_scrape=args.skip_scrape, force=args.force))


if __name__ == "__main__":
    main()
