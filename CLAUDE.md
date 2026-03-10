# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`ft-reddit-insights` is a Reddit data analysis pipeline: scrape posts and comments from subreddits via PRAW, persist to Supabase, and surface insights through trend detection and sentiment analysis.

## Setup

**Dependencies:** Managed with `uv`. Run `uv sync` to install from `pyproject.toml`.

**Environment variables** — copy `.env.example` to `.env` and fill in:
```
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
```

## Commands

```bash
uv run python -m src.scraper      # run the scraper
uv run pytest                     # run all tests
uv run pytest tests/path.py::fn -v  # run a single test
uv run ruff check .               # lint
uv run ruff format .              # format
```

## Architecture

```
src/
  config.py          # env var loading via python-dotenv
  scraper.py         # PRAW client; fetches posts and comments per subreddit
  storage.py         # Supabase client; upsert helpers
  analysis/
    trends.py        # trending topic and keyword detection
    sentiment.py     # sentiment scoring over time
tests/               # pytest; PRAW and Supabase clients are mocked
```

Data flows: `scraper.py` → `storage.py` (raw data) → `analysis/` (derived insights via pandas + Claude API).

## Key Patterns

- **PRAW rate limiting:** PRAW's built-in limiter handles per-request throttling. Add `time.sleep()` between large bulk fetches to stay well within Reddit's API limits.
- **Supabase upserts:** Key on `post_id` (Reddit's stable post ID) to make re-runs idempotent — no duplicate rows on repeated scrapes.
- **Config:** All credentials and settings are loaded in `src/config.py` using `python-dotenv`. No other module should read env vars directly.
