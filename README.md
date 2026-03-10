# FT Community Intelligence Pipeline

An end-to-end data pipeline that scrapes Reddit for discussions about the Financial Times, then uses Claude AI to classify each post through a **product monetization lens** — surfacing paywall friction, churn signals, and conversion opportunities for a product dashboard.

## What it does

1. **Scrapes** Reddit's public JSON API across 4 subreddits (`r/investing`, `r/finance`, `r/ukpolitics`, `r/journalism`) for 5 FT-related search terms — no API key required
2. **Analyses** each post with Claude Haiku, classifying it into one of four monetization-focused categories and generating a conversion intent score
3. **Stores** structured results in Supabase, ready to power a real-time product dashboard

## Architecture

```
src/
  config.py              ← env var loading (python-dotenv)
  scraper.py             ← Reddit JSON API scraper (no auth needed)
  analysis/
    sentiment.py         ← Claude AI monetization analysis
```

**Data flow:** `scraper.py` → `raw_reddit_data.csv` → `sentiment.py` → `analyzed_reddit_data.csv` + Supabase

## Monetization Analysis Schema

Each post is classified by Claude Haiku (`claude-haiku-4-5`) into:

| Field | Values |
|---|---|
| `category` | `Paywall Friction` · `Value Proposition` · `Retention Risk` · `Product Upsell` |
| `monetization_sentiment` | `-1.0` (active churn/bypass) → `+1.0` (high conversion intent) |
| `actionable_fix` | 1-sentence product recommendation, generated only for negative Paywall Friction posts |

**Example output:**
```json
{
  "category": "Paywall Friction",
  "monetization_sentiment": -0.80,
  "actionable_fix": "Replace email-gating with a higher free article allowance to reduce drop-off before the hard paywall."
}
```

## Scraper Design

The scraper is intentionally **authentication-free** — it uses Reddit's public `.json` search endpoints rather than the OAuth API. This makes it portable, zero-setup, and resilient to API key provisioning issues.

- Iterates `SUBREDDITS × SEARCH_TERMS` (20 combinations)
- Filters to posts from the **last 12 months** client-side
- Deduplicates on Reddit post ID across subreddits
- Respects rate limits with `time.sleep(2)` between requests
- Handles macOS SSL cert issues via `certifi`

## Setup

```bash
# 1. Clone and install
git clone https://github.com/<you>/ft-product-insights
pip install -r requirements.txt

# 2. Configure credentials
cp .env.example .env
# Edit .env with your Anthropic API key (and optionally Supabase)

# 3. Scrape Reddit
python3 -m src.scraper                  # full run (~431 posts, ~5 min)
python3 -m src.scraper --limit 5        # dry run to verify connection

# 4. Analyse with Claude AI
python3 -m src.analysis.sentiment       # analyses top 250 by upvote score
```

## Supabase Schema

The pipeline upserts to a `reddit_feedback` table. Required columns:

```sql
create table reddit_feedback (
  id              uuid default gen_random_uuid() primary key,
  post_id         text unique,
  subreddit       text,
  title           text,
  body            text,
  created_at      timestamptz,
  url             text,
  sentiment_score float,      -- monetization_sentiment
  topic_category  text,       -- category
  primary_emotion text        -- actionable_fix
);
```

## Tech Stack

| Component | Technology |
|---|---|
| Scraping | Python `urllib` + Reddit public JSON API |
| AI Analysis | Anthropic Claude Haiku (`claude-haiku-4-5`) |
| Storage | Supabase (PostgreSQL) |
| Data processing | pandas |
| Config | python-dotenv |

## Cost

Analysis runs at approximately **$0.001 per post** (250 posts ≈ $0.25). The `MAX_RECORDS` constant in `src/analysis/sentiment.py` controls the batch size.
