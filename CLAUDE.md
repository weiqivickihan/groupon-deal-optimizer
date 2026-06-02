# Groupon Deal Optimizer — Project Guide

## What This Is

A Python pipeline that takes Groupon deal URLs and produces three outputs per deal:
1. **Audit** — structured JSON of every element scraped from the live deal page
2. **Research** — competitive pricing, merchant reputation, market context (via web search + Claude)
3. **Proposal** — specific, data-backed optimization recommendations (via Claude)

Full assignment spec: `case-study-deal-optimizer.md`

---

## Setup

### Prerequisites
- Python 3.11+
- A Claude API key (set in `.env`)

### Install

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### Configure

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

---

## Running

### One command — process all deals in deals.txt

```bash
python main.py
```

### Process a specific URL directly

```bash
python main.py --url "https://www.groupon.com/deals/some-deal"
```

### Process only N deals (useful for testing)

```bash
python main.py --limit 3
```

### Skip scraping (reuse cached audit JSON) and go straight to research + proposal

```bash
python main.py --skip-scrape
```

---

## Output Structure

Each deal gets its own folder under `output/`:

```
output/
└── renew-cozy-spa/
    ├── audit.json          # Raw structured scrape data
    ├── audit_summary.md    # Human-readable audit
    ├── research.json       # Competitive research data
    ├── research_report.md  # Human-readable research
    └── proposal.md         # Optimization recommendations
```

A summary across all deals is written to `output/index.md`.

---

## Project Layout

```
.
├── main.py               # Entrypoint — reads deals.txt, runs pipeline
├── groupon_scraper.py    # Playwright + stealth scraper → audit JSON
├── researcher.py         # Web search + Claude → research report
├── proposer.py           # Claude → optimization proposal
├── db.py                 # DuckDB storage layer
├── deals.txt             # One Groupon deal URL per line (# for comments)
├── requirements.txt
├── .env.example
└── output/               # Generated — one subfolder per deal
```

---

## Adding More Deals

Add URLs to `deals.txt`, one per line. Lines starting with `#` are ignored.

```
# Spa deals — NYC
https://www.groupon.com/deals/renew-cozy-spa
# Activities — Chicago
https://www.groupon.com/deals/some-activity
```

Then re-run `python main.py`. Already-processed deals are skipped unless you pass `--force`.

---

## Key Dependencies

| Package | Purpose |
|---|---|
| `playwright` | Headless browser for JS-rendered pages |
| `playwright-stealth` | Bypass Cloudflare bot detection |
| `anthropic` | Claude API for research + proposals |
| `duckdb` | Queryable local storage for deal data |
| `beautifulsoup4` | HTML parsing fallback |
| `python-dotenv` | Load `.env` config |
| `httpx` | Async HTTP for web research |

---

## Notes

- The scraper reads Groupon's embedded `__NEXT_DATA__` JSON rather than CSS selectors — more robust to UI changes.
- Playwright runs headless Chromium. First run downloads ~90 MB of browser binaries.
- Rate-limit: the pipeline adds a short delay between deals to avoid triggering blocks.
- All raw data is stored in `deals.db` (DuckDB) so results are queryable even after pipeline runs.
