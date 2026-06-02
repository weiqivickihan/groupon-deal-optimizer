# Case Study Assignment: Groupon Deal Page Optimizer

**Role:** AI Builder, CEO Office
**Time limit:** 48 hours from receipt
**Deliverable:** Working system + outputs for 20 deals

---

## The Problem

Groupon has thousands of live deal pages. Most were created by sales reps or merchants using templates, with minimal optimization. The CEO office needs a system that can take any deal URL, analyze it end-to-end, and produce an actionable optimization proposal backed by real data.

This is not a mockup or a design exercise. We want a working system that produces real output.

## What to Build

A Python-based pipeline that takes Groupon deal URLs as input and produces three outputs per deal:

### Output 1: Deal Page Audit
Scrape the live deal page and extract every structured element:
- Title, subtitle, merchant name, category
- All pricing options (original price, deal price, discount %, savings)
- Highlights / what you get
- Fine print / terms and conditions
- Images (count, quality assessment, alt text)
- Reviews (count, average rating, sample quotes)
- FAQs if present
- SEO elements (meta title, meta description, H1/H2 structure, schema marku, technical page elements)
- Mobile vs desktop differences if detectable
- Page load indicators (image count, script count)
- Trust signals present (ratings, review count, "X bought", guarantees)
- Urgency elements (countdown, limited quantity, "selling fast")

Format: structured JSON + human-readable summary.

### Output 2: Competitive & Market Research
For each deal, automatically research:
- **Competitor pricing:** What do competitors charge for the same or similar service in the same city? (Search Google, Yelp, competitor websites)
- **Merchant reputation:** Yelp rating, Google rating, review themes. What do customers love/complain about?
- **Deal value assessment:** Is the Groupon price actually a good deal vs. booking direct? vs. competitor coupons?
- **Category context:** What are typical discount ranges for this category (spa, restaurant, activities, etc.)?
- **Content gaps:** What information is missing from the deal page that customers would want to know before purchasing?

Use web search, scraping, and AI to compile this. Cite sources. Include direct quotes from reviews where relevant.

### Output 3: Optimization Proposal
Based on the audit and research, generate specific recommendations:
- **Title rewrite:** Proposed new title with reasoning (clarity, keywords, conversion)
- **Pricing display:** How to frame the price/value proposition better
- **Highlights rewrite:** What to emphasize based on real customer sentiment
- **Missing content:** What to add (specific details, trust signals, FAQs)
- **Image recommendations:** What types of images would improve conversion
- **SEO improvements:** Meta title, description, heading structure
- **Competitive positioning:** How to frame this deal vs. alternatives
- **Priority ranking:** Which changes would have the biggest impact, ordered by expected effect

Each recommendation should reference specific data from the research (e.g., "Yelp reviews mention 'relaxing atmosphere' 23 times but the deal page doesn't mention ambiance at all").

## Technical Requirements

- **Language:** Python. Use whatever libraries you need.
- **AI integration:** Use Claude (we can provide a Claude MAX login with Claude Code access if needed). The system should use AI for research synthesis, content analysis, and proposal generation. Show us how you use AI as part of your build workflow, not just as a feature.
- **Data storage:** Use DuckDB or SQLite for structured data. Each deal's research should be queryable.
- **Reproducible:** The system must run in a Claude Code environment. Include a README with setup instructions. Ideally: clone the repo, install dependencies, run one command, get outputs.
- **Extensible:** It should be easy to add more deal URLs. A simple `urls.txt` or CLI argument. No hardcoding.
- **Output format:** Each deal gets its own folder with the three outputs (audit JSON + summary, research report, optimization proposal). Generate both structured data (JSON) and human-readable reports (Markdown or HTML).

## Deals to Process

Pick 20 deals from groupon.com yourself. Choose a mix:
- At least 3 different cities
- At least 4 different categories (spa/wellness, health&beauty, activities/tours, automotive)
- Include at least 2 deals that look "good" (high ratings, lots sold) and at least 2 that look "weak" (low ratings, poor descriptions)
- No physical goods. Services only.

List the 20 URLs in a `deals.txt` file in the repo.

## What We Are Evaluating

1. **Systems thinking:** How you structure the pipeline. Data model for deals, research, recommendations. How components connect.
2. **Code quality:** Clean, readable, well-organized code. Not a single 500-line script. Proper error handling for scraping failures, rate limits, missing data.
3. **Research rigor:** Do your competitive findings hold up? Are sources cited? Is the analysis specific or generic?
4. **AI integration depth:** How you use Claude in the pipeline. Prompt design, structured output parsing, using AI for judgment calls (not just summarization).
5. **Output quality:** Would a CEO look at the optimization proposals and say "yes, do this"? Are recommendations specific and actionable, or generic advice?
6. **Speed and shipping:** Did you actually produce outputs for all 20 deals? A working system with 20 real outputs beats a perfect architecture with 3.

## How to Submit

Share a GitHub repository (public or private, invite dsenkypl@groupon.com if private) or zip file containing:
- Source code
- README with setup and run instructions
- `deals.txt` with your 20 chosen URLs
- `output/` folder with all 20 deal outputs
- Brief write-up (1 page max): what you built, what you would improve with more time, and what surprised you during the research

## Timeline

96 hours from when you receive this assignment. If you need the Claude MAX login, reply and we will set it up within a few hours.

---

Dusan Senkypl
CEO, Groupon
