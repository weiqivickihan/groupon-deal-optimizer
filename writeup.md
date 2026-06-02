# What I Built, What I'd Improve, and What Surprised Me

## What I Built

I built a three-stage Python pipeline that takes Groupon deal URLs and produces structured audit data, competitive research, and optimization proposals — fully automated from a single `deals.txt` file.

**Stage 1 — Scraper (`groupon_scraper.py`):** Uses Playwright with `playwright-stealth` to bypass Cloudflare bot detection on Groupon's pages. Rather than parsing CSS selectors, which break with every UI update, the scraper reads Groupon's embedded `__NEXT_DATA__` JSON — the Apollo GraphQL cache that Next.js injects into every page. This gives reliable access to structured data: pricing in cents with discount math already done, review distributions, FAQ nodes, badge references, schema markup, urgency signals, and image CDN URLs. The scraper populates `audit.json` and `audit_summary.md` per deal.

**Stage 2 — Researcher (`researcher.py`):** Calls `claude-sonnet-4-6` with the `web_search` tool (up to 5 searches per deal) and a structured prompt that asks for four specific outputs: competitor pricing with real sources, merchant reputation from Yelp/Google with direct review quotes, a deal value verdict comparing Groupon price vs. market, and prioritized content gaps. Results are parsed from Claude's JSON response and stored in `research.json`, `research_report.md`, and DuckDB. Runs sequentially to stay within Anthropic's 30k token-per-minute rate limit.

**Stage 3 — Proposer (`proposer.py`):** Feeds the audit and research together into Claude with a tight, section-structured prompt that demands actual rewritten copy — not instructions to rewrite. Each `proposal.md` covers 8 sections: title rewrite, pricing display, highlights rewrite (with specific bullets), missing content additions, SEO improvements, image recommendations, trust signal enhancements, and competitive positioning — plus a priority ranking table and an immediate next-step paragraph. All 20 proposals completed with zero human editing of the outputs.

All structured data (pricing, ratings, competitor prices, content gaps) is stored in DuckDB for cross-deal querying. The full pipeline runs in one sequence of three commands after initial setup.

---

## What I Would Improve With More Time

**Richer SEO analysis.** The current scraper captures meta title, meta description, H1/H2 structure, and schema types — but doesn't run a Core Web Vitals check, measure actual mobile page speed, or diff the deal page's structured data against Google's recommended schema fields for `HealthAndBeautyBusiness`, `DaySpa`, etc. A Lighthouse API call per deal would make the SEO section of each proposal much more specific.

**Deeper review mining.** The scraper captures up to 5 Groupon review quotes from the embedded Apollo state, but Groupon only renders 5 reviews in the initial page load. With more time, I'd paginate through all reviews (or use the Groupon review API endpoint) and run sentiment clustering across the full corpus — turning "customers mention 'relaxing atmosphere' 23 times but the deal page doesn't mention ambiance" from a hypothesis into a measured fact. That's the kind of specific, evidenced recommendation the CEO office would act on.

**Cross-deal pattern detection.** With 20 deals in DuckDB, I started to see patterns — automotive deals consistently lack urgency signals, dance studio deals almost never show competitor pricing context, weak deals uniformly have thin image galleries. With more time I'd codify these category-level patterns into the proposal prompt so each recommendation is benchmarked against what top performers in the same category do.

**Parallelized research with smarter rate limiting.** Running researcher.py sequentially at ~90 seconds per deal means 20 deals takes ~30 minutes. With proper exponential backoff and token-budget management (estimating input tokens before each request), I could safely parallelize 2–3 calls simultaneously and cut that to ~12 minutes without hitting the 30k TPM limit.

**Deeper manual deal review.** I only had time to manually read through 2 of the 20 deals in detail — and even that surfaced findings the automated pipeline missed entirely: a franchise ownership change visible only in the temporal pattern of reviews, Groupon's editorial content ecosystem cross-linking to deals, and the psychological layering of multiple urgency signals on the same page. With more time, I'd read every deal output myself and feed those observations back into the prompt design. The pipeline surfaces data; human judgment is still needed to notice what's interesting about it.

---

## What Surprised Me During the Research

**The "original price" credibility question turned out to be real.** I expected most Groupon deal prices to be inflated-baseline theater — markdown from a list price nobody actually charges. In practice, about 15 of the 20 deals came back with "credible" original price assessments. The spa and wellness deals in particular were consistently priced 40–55% below actual competitor rates at national chains like Massage Envy and Hand & Stone. The Groupon discount is often a real discount, not a manufactured one.

**The content gaps were shockingly consistent across categories.** Almost every deal — regardless of city, category, or quality tier — was missing the same four things: exact address with transit directions, therapist/instructor credentials or named staff, explicit cancellation policy, and tipping disclosure. These are all zero-cost copy additions that require no new assets and no merchant coordination. The highest-leverage optimization for most of these deals isn't a design change or a pricing experiment — it's filling in information that a high-intent buyer needs before clicking "Buy."

**Review sentiment without a time dimension can be deeply misleading.** While reviewing Arthur Murray Alexandria's Groupon page, I noticed almost all the 1-star reviews were from 7–9 years ago, while recent reviews were overwhelmingly 5-star. After investigating, I found the studio had relocated — Yelp still lists the old address at 6489 Little River Turnpike while the official site now shows 3223 Duke St Suite B1 — suggesting a likely franchise owner change. The aggregate 4.8-star rating is accurate, but a deal that appears to be a borderline merchant is actually a thriving one under new management. The automated pipeline flagged the rating correctly but had no way to surface this narrative. With more time, I'd weight recent reviews more heavily and flag cases where the rating trend over time diverges significantly from the aggregate score — that divergence is often the most interesting thing about a merchant.

---

*Submitted by Weiqi Han · June 1, 2026*
