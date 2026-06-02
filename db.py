"""
DuckDB storage layer. All deal data is queryable from deals.db.

Tables:
  audits     — raw scrape data per deal (JSON blob + key fields)
  research   — competitive research results per deal (JSON blob + key fields)
"""

import json
import os
from pathlib import Path

import duckdb

DB_PATH = os.getenv("DB_PATH", "deals.db")


def _conn():
    return duckdb.connect(DB_PATH)


def init_db():
    con = _conn()
    con.execute("""
        CREATE TABLE IF NOT EXISTS audits (
            slug            VARCHAR PRIMARY KEY,
            url             VARCHAR,
            title           VARCHAR,
            merchant_name   VARCHAR,
            avg_rating      DOUBLE,
            review_count    INTEGER,
            groupon_rating  DOUBLE,
            image_count     INTEGER,
            urgency_bought  VARCHAR,
            urgency_message VARCHAR,
            option_count    INTEGER,
            min_deal_price  DOUBLE,
            max_discount_pct DOUBLE,
            scraped_at      TIMESTAMP DEFAULT current_timestamp,
            raw_json        VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS research (
            slug                VARCHAR PRIMARY KEY,
            merchant_name       VARCHAR,
            city                VARCHAR,
            category            VARCHAR,
            competitor_low      DOUBLE,
            competitor_high     DOUBLE,
            groupon_deal_price  DOUBLE,
            is_good_deal        BOOLEAN,
            yelp_rating         DOUBLE,
            google_rating       DOUBLE,
            review_themes_pos   VARCHAR,
            review_themes_neg   VARCHAR,
            content_gaps        VARCHAR,
            sources             VARCHAR,
            researched_at       TIMESTAMP DEFAULT current_timestamp,
            raw_json            VARCHAR
        )
    """)
    con.close()


def upsert_audit(slug: str, data: dict):
    init_db()
    options = data.get("pricing_options", [])
    prices  = [o.get("deal_price") for o in options if o.get("deal_price")]
    discounts = [o.get("discount_pct") for o in options if o.get("discount_pct")]

    con = _conn()
    con.execute("""
        INSERT OR REPLACE INTO audits
          (slug, url, title, merchant_name, avg_rating, review_count,
           groupon_rating, image_count, urgency_bought, urgency_message,
           option_count, min_deal_price, max_discount_pct, raw_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, [
        slug,
        data.get("url"),
        data.get("title"),
        data.get("merchant_name"),
        data.get("avg_rating"),
        data.get("review_count"),
        data.get("groupon_rating"),
        data.get("image_count"),
        data.get("urgency_bought"),
        data.get("urgency_message"),
        len(options),
        min(prices) if prices else None,
        max(discounts) if discounts else None,
        json.dumps(data),
    ])
    con.close()


def upsert_research(slug: str, data: dict):
    init_db()
    con = _conn()
    con.execute("""
        INSERT OR REPLACE INTO research
          (slug, merchant_name, city, category,
           competitor_low, competitor_high, groupon_deal_price, is_good_deal,
           yelp_rating, google_rating,
           review_themes_pos, review_themes_neg, content_gaps, sources, raw_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, [
        slug,
        data.get("merchant_name"),
        data.get("city"),
        data.get("category"),
        data.get("competitor_pricing", {}).get("low"),
        data.get("competitor_pricing", {}).get("high"),
        data.get("deal_value", {}).get("groupon_price"),
        data.get("deal_value", {}).get("is_good_deal"),
        data.get("merchant_reputation", {}).get("yelp_rating"),
        data.get("merchant_reputation", {}).get("google_rating"),
        json.dumps(data.get("merchant_reputation", {}).get("positive_themes", [])),
        json.dumps(data.get("merchant_reputation", {}).get("negative_themes", [])),
        json.dumps(data.get("content_gaps", [])),
        json.dumps(data.get("sources", [])),
        json.dumps(data),
    ])
    con.close()


def query(sql: str):
    init_db()
    con = _conn()
    result = con.execute(sql).fetchdf()
    con.close()
    return result
