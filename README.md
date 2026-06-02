# Groupon Deal Page Optimizer

A Python pipeline that scrapes live Groupon deal pages, researches competitor pricing and merchant reputation, and generates specific optimization proposals — for 20 deals across NYC, Chicago, and Washington DC.

Built for the Groupon AI Builder case study assignment.

---

## What It Produces

For each of the 20 deals, the pipeline generates five files in `output/<deal-slug>/`:

| File | Contents |
|---|---|
| `audit.json` | Structured scrape: pricing, SEO, reviews, FAQs, trust signals, images |
| `audit_summary.md` | Human-readable audit with review distribution and SEO breakdown |
| `research.json` | Competitor pricing, merchant reputation, deal value verdict, content gaps |
| `research_report.md` | Human-readable research with sourced competitor data and review quotes |
| `proposal.md` | 8-section optimization proposal with rewritten copy and priority ranking |

All data is also stored in `deals.db` (DuckDB) for querying across all 20 deals.

---

## Setup

### Prerequisites
- Python 3.11+
- An Anthropic API key ([get one here](https://console.anthropic.com/))

### Install dependencies

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### Configure

```bash
cp .env.example .env
# Edit .env and set your ANTHROPIC_API_KEY
```

---

## Running the Full Pipeline

### One command — scrape, research, and propose for all deals

```bash
python3 main.py          # scrape all 20 deals
python3 researcher.py    # research all deals (uses Claude + web search, ~30 min)
python3 proposer.py      # generate proposals for all deals (~20 min)
```

### Process a specific URL

```bash
python3 main.py --url "https://www.groupon.com/deals/some-deal"
python3 researcher.py --slug some-deal
python3 proposer.py --slug some-deal
```

### Useful flags

```bash
python3 main.py --limit 3          # scrape only first 3 deals (for testing)
python3 main.py --force            # re-scrape already-processed deals
python3 main.py --skip-scrape      # reuse cached audit.json, skip scraping
python3 researcher.py --force      # re-research already-done deals
python3 proposer.py --force        # regenerate existing proposals
```

### Query results in DuckDB

```bash
python3 -c "
import duckdb
con = duckdb.connect('deals.db')
print(con.execute('SELECT slug, avg_rating, review_count, min_deal_price FROM audits ORDER BY avg_rating').df())
"
```

---

## Project Structure

```
.
├── main.py               # Entrypoint — call this to scrape; reads deals.txt, writes audit files
├── groupon_scraper.py    # Library used by main.py; run directly for one-off URL testing
├── researcher.py         # Claude + web search → competitive research
├── proposer.py           # Claude → optimization proposals
├── db.py                 # DuckDB storage layer
├── deals.txt             # 20 Groupon deal URLs (one per line)
├── requirements.txt      # Python dependencies
├── .env.example          # API key template
└── output/               # Generated outputs — one subfolder per deal
    ├── index.md          # Master summary of all 20 deals
    └── <deal-slug>/
        ├── audit.json
        ├── audit_summary.md
        ├── research.json
        ├── research_report.md
        └── proposal.md
```

---

## How It Works

### 1. Scraping (`main.py` calls `groupon_scraper.py`)
**Users should call `main.py`** — it reads URLs from `deals.txt`, handles batching and skip/force flags, writes `audit.json` + `audit_summary.md`, and saves to DuckDB. `groupon_scraper.py` is the underlying library: it contains the Playwright browser logic and `__NEXT_DATA__` parser, and can be run directly (`python3 groupon_scraper.py <url>`) for quick one-off testing that prints raw JSON to stdout without writing any files.

The scraper bypasses Cloudflare bot detection via `playwright-stealth` and reads Groupon's embedded `__NEXT_DATA__` JSON — the Apollo GraphQL cache that hydrates the Next.js page — rather than parsing CSS selectors (which break with every UI update). This gives structured access to all deal data: pricing in cents, review distribution, FAQ nodes, badge refs, schema markup, and urgency signals.

### 2. Research (`researcher.py`)
For each deal, sends a structured prompt to `claude-sonnet-4-6` with the `web_search` tool enabled (up to 5 searches per deal). Claude finds real competitor prices, Yelp/Google ratings, review themes, and content gaps. Results are parsed from Claude's JSON response and stored both as files and in DuckDB. Runs sequentially (1 deal at a time) to stay within Anthropic's token-per-minute limits.

### 3. Proposals (`proposer.py`)
Feeds both the audit and research into Claude to generate an 8-section optimization proposal with actual rewritten copy — not generic advice. Each proposal includes a title rewrite, pricing framing, highlights rewrite with specific bullets, missing content additions, SEO improvements, image recommendations, trust signal enhancements, competitive positioning, a priority ranking table, and an immediate next-step recommendation.

---

## Key Dependencies

| Package | Purpose |
|---|---|
| `playwright` | Headless Chromium for JS-rendered pages |
| `playwright-stealth` | Patches browser fingerprinting signals to bypass bot detection |
| `anthropic` | Claude API (web search + proposal generation) |
| `duckdb` | Queryable local storage for all deal data |
| `beautifulsoup4` | HTML parsing fallback |
| `python-dotenv` | `.env` configuration loading |
| `httpx` | Async HTTP client |

---

## Deals Covered

20 service deals across 3 cities and 4 categories — see `deals.txt` for all URLs and `output/index.md` for a full summary table with ratings, pricing, and deal quality assessment.

**Cities:** New York City (7), Chicago (7), Washington DC (6)
**Categories:** Activities/Tours (6), Health & Beauty (6), Spa/Wellness (5), Automotive (3)
**Weak deals included:** 4 deals with ratings ≤ 3.8★ for contrast analysis
