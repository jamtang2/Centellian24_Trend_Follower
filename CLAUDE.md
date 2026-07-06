# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repository currently contains only the PRD (`PRD/Centellian24_US_Monitor_PRD.md`) — no code has been implemented yet, and this is not yet a git repository. The PRD is written in Korean and is the sole source of truth for what to build. When starting implementation, follow its milestones (M1–M8) in order rather than inventing new structure.

## What this project is

A weekly-refreshed, statically-hosted dashboard (GitHub Pages) tracking US market traction signals for 센텔리안24 (Centellian24), a Dongkook Pharmaceutical cosmetics brand, following its 2026-06 launch into Ulta Beauty (1,400 stores) and Nordstrom (89 stores). The dashboard exists to surface weekly leading indicators of US consumer demand, since official company results (quarterly IR/DART filings) lag too far behind to catch momentum early.

This project reuses the architecture of prior sibling projects (`Shortage_Bottleneck_Scanner`, `CAPEX_Dashboard`): PRD → Claude Code implementation → GitHub Actions (scheduled) → GitHub Pages (static dashboard). Match those projects' tone/visual style if/when they're available as reference.

## Planned architecture (per PRD)

### Data collection (5 tracked metric groups, §3–4)

1. **Amazon** — direct HTML scraping (no paid API/SerpApi). Scrapes search results + product detail pages for: product name, ASIN, estimated monthly sales (parsed from "N+ bought last month" badges), category, category BSR rank, review count, rating, price, stock status. Tracks 3–5 flagship SKUs (마데카 크림 타임 리버스, 360도 샷 PDRN 리프팅 아이크림, 마데카 크림 액티브 리뉴 PDRN 등). On scrape failure: carry forward last week's value + log failure — do NOT fall back to Gemini grounding for Amazon; it's scrape-only.
2. **Google Trends** — via `pytrends` (unofficial lib), queried for both **US and JP** region codes, keywords "Centellian24" / "Madeca Cream" (JP-script keyword tracking to be decided in M2 based on real data). 12-month rolling window fetched each run; only the latest week's value is appended to history.
3. **Ulta Beauty**, **TikTok hashtags**, **Instagram hashtags** — collected *exclusively* via **Gemini API + Google Search grounding** (no direct scraping attempted for these three channels — see §4.3–4.4). Prompts must request structured JSON output plus cited source URLs. All values from this channel are treated as **estimates** and flagged with a low-confidence badge in the dashboard, distinct from Amazon/Trends "measured" data.

### AI usage

Gemini is the **only** AI API used in this project (unlike sibling projects that may ensemble Claude/GPT/Gemini) because Google Search grounding is core to collection, not just summarization. Gemini's three roles: (1) sole collection mechanism for Ulta/TikTok/Instagram via grounded search, (2) weekly qualitative Korean-language summary generation from collected data, (3) returning cited source URLs alongside every grounded answer. API key lives in GitHub Actions Secrets (`GEMINI_API_KEY`).

### Data storage (§5)

- Each run writes a snapshot to `data/YYYY-MM-DD.json` and appends to a cumulative `data/history.csv` (or `history.json`).
- See the PRD for the full example schema (fields: `week`, `amazon[]`, `google_trends.{US,JP}`, `ulta`, `tiktok`, `instagram`, `ai_summary`, `sources[]`). Every non-Amazon/non-Trends field carries a `source` and `confidence` tag.

### Automation pipeline (§7)

Runs weekly via GitHub Actions, **Sundays 06:17 KST** (deliberately off the top-of-hour, per a lesson carried over from prior projects) in this order: Amazon scrape → pytrends (US+JP) → Gemini grounding (Ulta) → Gemini grounding (TikTok) → Gemini grounding (Instagram) → data validation + history append → Gemini weekly summary generation → regenerate static `index.html` → deploy to GitHub Pages. Any step failure (scrape or grounding call) falls back to carrying forward the previous week's value with a logged failure, rather than blocking the whole run.

### Dashboard (GitHub Pages) (§6)

Single static page: (1) top summary cards with WoW deltas per metric, (2) time-series charts — Amazon est. monthly sales per product, Amazon BSR (inverted scale, lower=better ranks higher), Amazon/Ulta review count trends, Google Trends US vs JP comparison line, TikTok/Instagram post/view count trends (marked as estimates), (3) AI weekly commentary section with source links, (4) raw data table with per-week CSV download, (5) confidence badges distinguishing scraped/measured data (Amazon, Trends) from Gemini-grounding-estimated data (Ulta, TikTok, Instagram).

## Known constraints and risks (§9 — keep in mind when implementing)

- Amazon scraping must stay low-frequency (weekly) and non-commercial in spirit — ToS risk if request patterns look aggressive.
- Ulta/TikTok/Instagram numbers are grounding-derived estimates with potentially large error vs. reality — treat as directional/trend signals, not absolute truth, and always keep the confidence badge wired through the UI.
- Amazon page structure changes will break scraping selectors — expect to need periodic selector maintenance.
- Products may span multiple Amazon categories, which can destabilize BSR comparisons over time — pin the tracked category per product explicitly rather than re-resolving it each run.
- Gemini grounding responses can vary week-to-week for the same query — enforce a strict output JSON schema in the prompt and add retry logic for parse failures.
