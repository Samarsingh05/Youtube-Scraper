YouTube Brand Influencer Scraper

Scrape YouTube videos where creators specifically talk about selected AI tools/brands, then enrich each video with:
video URL → views → creator email → Instagram (if any) → X/Twitter (if any).

The scraper uses:

YouTube Data API v3 for search and stats

youtube-transcript-api to check relevance from transcripts (no API quota)

Requests + BeautifulSoup for channel “About” info

Optional Selenium (headless & muted) to grab emails/socials that need JS rendering

It outputs two Excel files and can safely append across multiple runs without duplicates.

Supported brands (strict filters)

loom, guidde, scribe, "scribe how", gamma, lovable, synthesia, clueso ai, emergent ai
Each brand has required terms (positive context) and negatives (to block false matches, e.g., weaving “loom”, piano “synthesia”).

You can edit brand rules inside yt_scrape_pipeline.py under the BRANDS dict.

Requirements

Python 3.10+

A YouTube Data API v3 key (Google Cloud project)

(Optional) Google Chrome for Selenium mode (ChromeDriver auto-installed)

Install dependencies:

python3 -m venv venv
source venv/bin/activate            # Windows PowerShell: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt

Provide your API key

Either export it:

export YOUTUBE_API_KEY="YOUR_API_KEY_HERE"   # macOS/Linux

# Windows PowerShell:
# setx YOUTUBE_API_KEY "YOUR_API_KEY_HERE"
# $env:YOUTUBE_API_KEY="YOUR_API_KEY_HERE"


Or pass inline with --api-key "..." in the command.

How to run
A) Single brand (example: Loom)
python yt_scrape_pipeline.py \
  --brands loom \
  --per-query 120 \
  --target-per-brand 300 \
  --video-duration medium --order relevance \
  --final-xlsx all_brands.xlsx --candidates-xlsx all_candidates.xlsx --append

B) Multiple brands in one run
python yt_scrape_pipeline.py \
  --brands loom guidde scribe "scribe how" gamma lovable synthesia \
  --per-query 120 \
  --target-per-brand 300 \
  --video-duration medium --order relevance \
  --final-xlsx all_brands.xlsx --candidates-xlsx all_candidates.xlsx --append

C) Using an inline API key
python yt_scrape_pipeline.py \
  --api-key "YOUR_API_KEY_HERE" \
  --brands synthesia \
  --per-query 80 \
  --target-per-brand 200 \
  --video-duration medium --order date \
  --final-xlsx all_brands.xlsx --candidates-xlsx all_candidates.xlsx --append

D) Faster runs without Selenium (no browser)
python yt_scrape_pipeline.py \
  --brands loom \
  --per-query 100 \
  --target-per-brand 250 \
  --video-duration medium --order relevance \
  --no-selenium \
  --final-xlsx all_brands.xlsx --candidates-xlsx all_candidates.xlsx --append


Flags (most useful):

--brands one or many (space-separated; use quotes if brand has spaces, e.g., "scribe how")

--per-query max results per search query (affects API cost; default 150)

--target-per-brand stop after collecting this many relevant videos for the brand

--video-duration any|short|medium|long (use medium to avoid Shorts noise)

--order relevance|date|viewCount

--no-selenium skip JS-based About scraping (faster, quieter)

--append merge into existing Excel files and dedupe by videoId

Output files

candidates.xlsx (or custom via --candidates-xlsx)
All relevant candidates found by search:
brand, videoId, video_url, title

final_enriched.xlsx (or custom via --final-xlsx)
Enriched final list:
video_url, views, creator_email, instagram, x_profile, brand, title, creator_channel, creator_channel_id, videoId

Safe to run multiple times with --append. The script dedupes by videoId.

Quota tips

If you see quotaExceeded (HTTP 403):

Lower --per-query (e.g., 150 → 80 → 40)

Lower --target-per-brand (e.g., 350 → 200)

Prefer --video-duration medium, --order relevance or date

Spread load across different API keys (different Google Cloud projects)

Progress is saved as it goes. If a run stops mid-way, already-found candidates and enriched rows remain in the Excel files.
