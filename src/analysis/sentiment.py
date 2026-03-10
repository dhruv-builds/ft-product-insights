"""
Monetization-focused analysis for Reddit posts using the Claude API.
Reads raw_reddit_data.csv, writes analyzed_reddit_data.csv, upserts to Supabase.

Usage:
    python3 -m src.analysis.sentiment
    python3 -m src.analysis.sentiment --input raw_reddit_data.csv --output analyzed_reddit_data.csv
"""

import argparse
import json
import time

import anthropic
import pandas as pd
from supabase import create_client

from src.config import ANTHROPIC_API_KEY, SUPABASE_SERVICE_KEY, SUPABASE_URL

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

MAX_RECORDS = 250  # top 250 by upvote score
COST_PER_ROW = 0.001  # $0.01 per 10 rows (Claude Haiku estimate)

SYSTEM_PROMPT = """You are a product monetization analyst for the Financial Times (FT).
Analyze Reddit posts and comments about FT's subscription, paywall, and products.

Return only valid JSON with exactly these three fields — no markdown, no explanation:

{
  "category": one of:
    "Paywall Friction"    – comments about price, bypass methods, gift links, or login loops
    "Value Proposition"   – whether FT content is worth the cost; comparisons to Bloomberg/Economist
    "Retention Risk"      – complaints about cancellation friction, renewal issues, or churn signals
    "Product Upsell"      – mentions of FT Edit app or Unhedged podcast as discovery/entry points,

  "monetization_sentiment": float from -1.0 to +1.0 where:
    -1.0 = actively bypassing paywall or churning
     0.0 = neutral / uninformed
    +1.0 = high intent to convert to paid subscription,

  "actionable_fix": if category is "Paywall Friction" AND monetization_sentiment < 0,
    write a concise 1-sentence product recommendation to reduce that friction (e.g. "Simplify guest
    registration by allowing social login before showing the paywall"). Otherwise return null.
}"""


def analyze_text(text: str) -> dict:
    """Analyze a single post and return monetization-focused structured data."""
    if not text or not text.strip():
        return {
            "category": "Value Proposition",
            "monetization_sentiment": 0.0,
            "actionable_fix": None,
        }

    response = claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,  # actionable_fix needs more room
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text[:2000]}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def _push_to_supabase(df: pd.DataFrame) -> None:
    """Upsert analyzed rows to the reddit_feedback table.

    Column mapping (reuses existing Supabase schema):
      topic_category   ← category
      sentiment_score  ← monetization_sentiment
      primary_emotion  ← actionable_fix
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("Supabase credentials not set — skipping upload.")
        return

    sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    records = []
    for _, row in df.iterrows():
        record = {
            "post_id": row.get("post_id") or row.get("id"),
            "subreddit": row.get("subreddit"),
            "title": row.get("title"),
            "body": row.get("body"),
            "created_at": row.get("created_utc"),
            "url": row.get("url"),
            "sentiment_score": row.get("monetization_sentiment"),
            "topic_category": row.get("category"),
            "primary_emotion": row.get("actionable_fix"),
        }
        records.append({
            k: (None if (isinstance(v, float) and v != v) else v)
            for k, v in record.items()
        })

    sb.table("reddit_feedback").upsert(records, on_conflict="post_id").execute()
    print(f"Pushed {len(records)} rows to Supabase reddit_feedback table.")


def analyze_csv(
    input_file: str = "raw_reddit_data.csv",
    output_file: str = "analyzed_reddit_data.csv",
) -> pd.DataFrame:
    df = pd.read_csv(input_file)

    # Sort by upvote score descending — highest quality signal first
    df = df.sort_values("score", ascending=False).head(MAX_RECORDS).reset_index(drop=True)

    estimated_cost = len(df) * COST_PER_ROW
    print(f"Analyzing {len(df)} rows (top {MAX_RECORDS} by score). Estimated cost: ${estimated_cost:.2f}")

    results = []
    for i, row in df.iterrows():
        text = str(row.get("body") or row.get("title") or "")
        print(f"  [{i + 1}/{len(df)}] score={row.get('score', 0):>5} | {row.get('id', '?')} | r/{row.get('subreddit', '?')}")

        try:
            result = analyze_text(text)
            fix_preview = f" | fix: {result['actionable_fix'][:60]}..." if result.get("actionable_fix") else ""
            print(f"    sentiment={result['monetization_sentiment']:+.2f}  "
                  f"category={result['category']}{fix_preview}")
        except Exception as e:
            print(f"    Error: {e}")
            result = {
                "category": None,
                "monetization_sentiment": None,
                "actionable_fix": None,
            }

        results.append(result)
        time.sleep(1)

    analysis_df = pd.DataFrame(results)
    out = pd.concat([df, analysis_df], axis=1)
    out.to_csv(output_file, index=False)
    print(f"\nSaved analyzed data to {output_file}")

    _push_to_supabase(out)
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monetization sentiment analysis via Claude API")
    parser.add_argument("--input", default="raw_reddit_data.csv")
    parser.add_argument("--output", default="analyzed_reddit_data.csv")
    args = parser.parse_args()
    analyze_csv(input_file=args.input, output_file=args.output)
