"""
Groupon deal page scraper — extracts structured data from __NEXT_DATA__ JSON.
Usage:
    python3 groupon_scraper.py <url>
    python3 groupon_scraper.py          # uses default test URL
"""

import asyncio
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional

from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from playwright_stealth import Stealth


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class PricingOption:
    label: str
    original_price: Optional[float]
    deal_price: Optional[float]
    discount_pct: Optional[float]
    limited_sale_price: Optional[float]
    limited_sale_label: Optional[str]
    promo_price: Optional[float]
    promo_code: Optional[str]
    sold_quantity: Optional[str]
    structured_fields: list = field(default_factory=list)


@dataclass
class ReviewQuote:
    rating: Optional[int]
    text: str
    author: Optional[str]


@dataclass
class FaqItem:
    question: str
    answer: str


@dataclass
class SeoData:
    meta_title: Optional[str]
    meta_description: Optional[str]
    h1: Optional[str]
    h2s: list = field(default_factory=list)
    schema_types: list = field(default_factory=list)   # e.g. ["HealthAndBeautyBusiness","FAQPage"]
    noindex: bool = False
    canonical_url: Optional[str] = None


@dataclass
class ReviewDistribution:
    five_star_pct: Optional[int]
    four_star_pct: Optional[int]
    three_star_pct: Optional[int]
    two_star_pct: Optional[int]
    one_star_pct: Optional[int]


@dataclass
class DealData:
    url: str
    # Core
    title: Optional[str] = None
    subtitle: Optional[str] = None
    merchant_name: Optional[str] = None
    category_breadcrumbs: list = field(default_factory=list)   # ["local","beauty-and-spas","massage"]
    # Pricing
    pricing_options: list = field(default_factory=list)
    # Content
    highlights_html: Optional[str] = None
    highlights_text: Optional[str] = None
    about_deal_html: Optional[str] = None
    about_deal_text: Optional[str] = None
    highlights: list = field(default_factory=list)    # redemption/booking notes
    fine_print: list = field(default_factory=list)
    faqs: list = field(default_factory=list)          # list of {question, answer}
    amenities: list = field(default_factory=list)
    # Reviews
    review_count: Optional[int] = None
    avg_rating: Optional[float] = None
    groupon_rating: Optional[float] = None
    review_distribution: Optional[dict] = None
    review_quotes: list = field(default_factory=list)  # up to 5 CustomerReview samples
    # Trust signals
    badges: list = field(default_factory=list)        # e.g. ["Best Rated","Popular Gift"]
    urgency_bought: Optional[str] = None
    urgency_message: Optional[str] = None
    has_guarantee: Optional[bool] = None
    is_giftable: Optional[bool] = None
    # Images & media
    image_count: Optional[int] = None
    image_urls: list = field(default_factory=list)    # first 5 image URLs
    has_videos: Optional[bool] = None
    # SEO
    seo: Optional[dict] = None
    # Page load signals
    script_count: Optional[int] = None
    # Error
    error: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cents_to_dollars(amount_cents) -> Optional[float]:
    try:
        return round(int(amount_cents) / 100, 2)
    except (TypeError, ValueError):
        return None


def _f(val) -> Optional[float]:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html).strip()


# ── Parsing __NEXT_DATA__ ─────────────────────────────────────────────────────

def _parse_options(apollo: dict) -> list:
    options = []
    for key, val in apollo.items():
        if not key.startswith("DealOption:"):
            continue

        label      = val.get("title") or "Option"
        orig_cents = (val.get("unformattedStrikeThroughPrice") or {}).get("amount")
        deal_cents = (val.get("unformattedPrice") or {}).get("amount")
        orig       = _cents_to_dollars(orig_cents)
        deal_      = _cents_to_dollars(deal_cents)

        disc_str = val.get("discount") or val.get("discountExperiment")
        disc = _f(re.search(r"(\d+\.?\d*)", str(disc_str)).group(1)) if disc_str and re.search(r"\d", str(disc_str)) else None
        if disc is None and orig and deal_ and orig > 0:
            disc = round((orig - deal_) / orig * 100, 1)

        ls       = val.get("limitedSale") or {}
        ls_offer = ls.get("limitedSaleOffer") or {}
        ls_price = _cents_to_dollars((ls_offer.get("unformattedOfferPrice") or {}).get("amount"))
        ls_label = ls_offer.get("relativeOfferLabel")

        promo   = val.get("promotion") or {}
        p_price = _cents_to_dollars((promo.get("price") or {}).get("amount"))
        p_code  = promo.get("promocode")

        sf_out = []
        for sf in val.get("structuredFields") or []:
            if sf.get("__typename") == "StructuredTextField":
                sf_out.append({"label": sf.get("label"), "value": sf.get("value")})
            elif sf.get("__typename") == "StructuredIncludedExcludedField":
                items = [
                    _strip_html(i.get("valueFormatted", ""))
                    for i in sf.get("items") or []
                    if not i.get("isExcluded")
                ]
                sf_out.append({"label": sf.get("label"), "value": items})

        options.append(asdict(PricingOption(
            label=label, original_price=orig, deal_price=deal_, discount_pct=disc,
            limited_sale_price=ls_price, limited_sale_label=ls_label,
            promo_price=p_price, promo_code=p_code,
            sold_quantity=val.get("soldQuantityMessage"),
            structured_fields=sf_out,
        )))
    return options


def _parse_contract_terms(apollo: dict) -> tuple[list, list]:
    highlights, fine_print = [], []
    for key, val in apollo.items():
        if not key.startswith("ConsumerContractTerms:"):
            continue
        term_id  = val.get("id", "")
        children = val.get("children") or []
        texts    = []
        for child in children:
            if isinstance(child, dict):
                text = child.get("friendlyName")
                if text:
                    texts.append(text)
                ref = child.get("__ref")
                if ref:
                    resolved = apollo.get(ref, {})
                    t = resolved.get("friendlyName") or resolved.get("text")
                    if t:
                        texts.append(t)
        if term_id == "plan-ahead":
            highlights.extend(texts)
        elif term_id == "fine-print":
            fine_print.extend(texts)
    return highlights, fine_print


def _parse_faqs(apollo: dict) -> list:
    faqs = []
    for key, val in apollo.items():
        if not key.startswith("FaqItem:"):
            continue
        q = val.get("question") or val.get("name") or ""
        a = val.get("answer") or val.get("acceptedAnswer") or ""
        if isinstance(a, dict):
            a = a.get("text") or ""
        if q:
            faqs.append(asdict(FaqItem(question=q, answer=_strip_html(str(a)))))
    return faqs


def _parse_reviews(apollo: dict) -> list:
    quotes = []
    for key, val in apollo.items():
        if not key.startswith("CustomerReview:"):
            continue
        text = val.get("text") or ""
        if not text:
            continue
        # Resolve author name
        user_ref  = (val.get("user") or {}).get("__ref")
        user_node = apollo.get(user_ref, {}) if user_ref else {}
        author    = user_node.get("displayName") or user_node.get("name") or user_node.get("maskedName")
        quotes.append(asdict(ReviewQuote(
            rating=val.get("rating"),
            text=text[:500],
            author=author,
        )))
        if len(quotes) >= 5:
            break
    return quotes


def _parse_review_distribution(summary: dict) -> Optional[dict]:
    dist = summary.get("distribution") or {}
    if not dist:
        return None
    return asdict(ReviewDistribution(
        five_star_pct  = (dist.get("_5") or {}).get("percentage"),
        four_star_pct  = (dist.get("_4") or {}).get("percentage"),
        three_star_pct = (dist.get("_3") or {}).get("percentage"),
        two_star_pct   = (dist.get("_2") or {}).get("percentage"),
        one_star_pct   = (dist.get("_1") or {}).get("percentage"),
    ))


def _parse_seo(apollo: dict, deal_node: dict, page_data: dict) -> dict:
    # Meta from Deal node
    seo_title = deal_node.get("seoTitle")
    seo_node  = deal_node.get("seodata") or {}
    noindex   = seo_node.get("noindex", False) if isinstance(seo_node, dict) else False
    canonical = page_data.get("canonicalUrl")

    # H2s from breadcrumbs / known deal page sections
    # (actual H1/H2 come from live DOM — use Deal node fields as proxy)
    h1 = deal_node.get("title")
    h2s_raw = ["What We Offer", "Why You Should Grab The Offer",
               "Need To Know Info", "Frequently Asked Questions",
               "About " + (deal_node.get("merchant", {}).get("name") or "Merchant")
               if isinstance(deal_node.get("merchant"), dict) else "About Merchant"]

    # Schema types from ld+json (populated from live page in scraper)
    schema_types = page_data.get("_schema_types", [])

    return asdict(SeoData(
        meta_title=seo_title,
        meta_description=None,   # populated from live DOM below
        h1=h1,
        h2s=h2s_raw,
        schema_types=schema_types,
        noindex=noindex,
        canonical_url=canonical,
    ))


def extract_from_next_data(data: dict, url: str, dom_extras: dict = None) -> DealData:
    dom_extras = dom_extras or {}
    props   = data.get("props", {})
    page_p  = props.get("pageProps", {})
    apollo  = page_p.get("__APOLLO_STATE__", {})
    deal    = DealData(url=url)

    deal_node = next((v for k, v in apollo.items() if k.startswith("Deal:")), {})

    # ── Core ───────────────────────────────────────────────────────────────
    deal.title    = deal_node.get("title")
    deal.subtitle = deal_node.get("subtitle") or None

    # Merchant
    merchant_node = deal_node.get("merchant") or {}
    if isinstance(merchant_node, dict) and "__ref" in merchant_node:
        merchant_node = apollo.get(merchant_node["__ref"], {})
    deal.merchant_name = merchant_node.get("name") or merchant_node.get("id")

    # Breadcrumbs → category path
    deal.category_breadcrumbs = [
        apollo.get((b.get("__ref", "")), {}).get("id", "")
        for b in (deal_node.get("breadcrumbs") or [])
        if isinstance(b, dict)
    ]

    # ── Pricing ────────────────────────────────────────────────────────────
    deal.pricing_options = _parse_options(apollo)

    # ── Content ────────────────────────────────────────────────────────────
    deal.highlights_html = deal_node.get("highlightsHtml")
    deal.highlights_text = _strip_html(deal.highlights_html) if deal.highlights_html else None
    deal.about_deal_html = deal_node.get("aboutDealHtml")
    deal.about_deal_text = _strip_html(deal.about_deal_html) if deal.about_deal_html else None
    deal.highlights, deal.fine_print = _parse_contract_terms(apollo)
    deal.faqs      = _parse_faqs(apollo)
    deal.amenities = [a.get("name") for a in (deal_node.get("amenities") or []) if a.get("name")]

    # ── Reviews ────────────────────────────────────────────────────────────
    review_summary       = deal_node.get("reviewSummary") or {}
    deal.review_count    = review_summary.get("total")
    deal.avg_rating      = _f(review_summary.get("rating"))
    deal.groupon_rating  = _f(deal_node.get("grouponRating"))
    deal.review_distribution = _parse_review_distribution(review_summary)
    deal.review_quotes   = _parse_reviews(apollo)

    # ── Trust signals ──────────────────────────────────────────────────────
    deal.badges         = [
        apollo.get(b.get("__ref", ""), {}).get("text", "")
        for b in (deal_node.get("badges") or [])
        if isinstance(b, dict) and b.get("__ref")
    ]
    deal.urgency_bought = deal_node.get("soldQuantityMessage")
    urgency_node        = deal_node.get("urgencyMessage") or {}
    deal.urgency_message = urgency_node.get("messageText")
    flags               = deal_node.get("flags") or {}
    deal.has_guarantee  = deal_node.get("showGrouponGuarantee")
    deal.is_giftable    = flags.get("isGiftable")

    # ── Images & media ─────────────────────────────────────────────────────
    imgs              = deal_node.get("images") or []
    deal.image_count  = len(imgs)
    deal.image_urls   = []
    for i in imgs[:5]:
        # top-level url field is most reliable; fallback to imgFallbackUrls
        url_ = (i.get("url")
                or i.get("largeUrl")
                or (i.get("imgFallbackUrls") or {}).get("url")
                or (i.get("imgFallbackUrls") or {}).get("srcSetUrls"))
        if url_ and isinstance(url_, str):
            deal.image_urls.append(url_)
    deal.has_videos   = bool(deal_node.get("videos"))

    # ── SEO (mix of Apollo + DOM extras) ──────────────────────────────────
    seo = _parse_seo(apollo, deal_node, page_p)
    seo["meta_description"] = dom_extras.get("meta_description")
    seo["schema_types"]     = dom_extras.get("schema_types", [])
    seo["h2s"]              = dom_extras.get("h2s", seo["h2s"])
    deal.seo = seo

    # ── Page load signals ──────────────────────────────────────────────────
    deal.script_count = dom_extras.get("script_count")

    return deal


# ── Scraper ───────────────────────────────────────────────────────────────────

async def scrape_deal(url: str, retries: int = 2) -> DealData:
    async with async_playwright() as p:
        for attempt in range(1, retries + 2):
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="America/Chicago",
            )
            page = await context.new_page()
            await Stealth().apply_stealth_async(page)

            try:
                print(f"  [attempt {attempt}] fetching {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(4_000)

                page_title = await page.title()
                if "just a moment" in page_title.lower():
                    raise RuntimeError(f"Bot challenge (title: '{page_title}')")

                next_data_raw = await page.eval_on_selector(
                    "#__NEXT_DATA__", "el => el.textContent"
                )
                if not next_data_raw:
                    raise RuntimeError("__NEXT_DATA__ not found")

                # ── Collect DOM extras ─────────────────────────────────────
                dom_extras = {}

                # meta description
                meta_desc = await page.get_attribute('meta[name="description"]', "content")
                dom_extras["meta_description"] = meta_desc

                # H2s (deal-page only, exclude nav/footer noise)
                h2_els = await page.query_selector_all("main h2, article h2, [class*='deal'] h2")
                if not h2_els:
                    h2_els = await page.query_selector_all("h2")
                h2s = []
                for el in h2_els[:12]:
                    t = (await el.inner_text()).strip()
                    if t and len(t) < 100:
                        h2s.append(t)
                dom_extras["h2s"] = h2s

                # JSON-LD schema types
                ld_scripts = await page.query_selector_all('script[type="application/ld+json"]')
                schema_types = []
                for s in ld_scripts:
                    try:
                        raw = await s.inner_text()
                        parsed = json.loads(raw)
                        nodes = parsed if isinstance(parsed, list) else [parsed]
                        for node in nodes:
                            t = node.get("@type")
                            if t and t not in schema_types:
                                schema_types.append(t)
                    except Exception:
                        pass
                dom_extras["schema_types"] = schema_types

                # Script count (page weight signal)
                scripts = await page.query_selector_all("script[src]")
                dom_extras["script_count"] = len(scripts)

                next_data = json.loads(next_data_raw)
                return extract_from_next_data(next_data, url, dom_extras)

            except PWTimeout:
                err = f"Timeout on attempt {attempt}"
                print(f"    {err}")
                if attempt > retries:
                    return DealData(url=url, error=err)
                await page.wait_for_timeout(3_000)

            except RuntimeError as e:
                err = str(e)
                print(f"    {err}")
                if attempt > retries:
                    return DealData(url=url, error=err)
                await page.wait_for_timeout(5_000)

            except Exception as e:
                return DealData(url=url, error=f"Unexpected: {e}")

            finally:
                await browser.close()

    return DealData(url=url, error="All retries exhausted")


# ── Entrypoint ────────────────────────────────────────────────────────────────

async def main():
    url = sys.argv[1] if len(sys.argv) > 1 else (
        "https://www.groupon.com/deals/renew-cozy-spa"
        "?redemptionLocationId=8a16b1fa-000a-b0c4-0d6c-0192fea79982"
    )
    result = await scrape_deal(url)
    print("\n── Scraped Deal ──────────────────────────────────────────────")
    print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
