# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

LeagueSpy is a Discord bot that scrapes leagueofgraphs.com for League of Legends match history and announces new games in a Discord channel. It tracks multiple players and their smurf accounts, stores match history in Oracle Database for deduplication, sends rich embeds (green for wins, red for losses), roasts losses in Spanish via a local LLM, detects rivalries, computes tilt scores, posts weekly power rankings, and alerts when players go live.

## Commands

```bash
# Environment setup
conda create -n leaguespy python=3.12 -y
conda activate leaguespy
pip install -r requirements.txt

# Run the bot
python -m src.bot

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_scraper.py -v

# Run a single test
pytest tests/test_scraper.py::TestExtractKDA::test_from_tooltip -v

# Database schema setup (Oracle)
sqlplus leaguespy/leaguespy@localhost:1523/FREEPDB1 @scripts/setup_db.sql
sqlplus leaguespy/leaguespy@localhost:1523/FREEPDB1 @scripts/migrate_v2.sql

# Start vLLM for roast engine (optional)
vllm serve Qwen/Qwen3.5-9B --port 8000
```

## Architecture

The bot runs as a single async process with multiple `discord.ext.tasks` loops and four discord.py Cogs.

**Core pipeline (check_matches loop, 5 min interval):**
1. `bot.py:LeagueSpyBot.check_matches` fires on the task loop
2. All summoners are scraped in parallel via `asyncio.gather`, with concurrency capped by a semaphore (default 3) inside `LeagueOfGraphsScraper`
3. The scraper opens a Playwright stealth browser tab per summoner, parses the HTML with regex extractors (`_extract_champion`, `_extract_kda`, etc.)
4. For each match, `database.py:Database.is_match_known` checks the Oracle `matches` table (unique constraint on `summoner_id + match_id`)
5. New matches get announced via `build_match_announcement()`, inserted into DB, and marked announced
6. After insert: `update_streak()` updates win/loss streak counters, match is appended to `new_matches` deque for cogs to consume
7. `AnalyticsCog.check_rivalry()` fires inline to detect if another tracked player was in the same match on the opposing team
8. Matches are reversed before announcement so the freshest game appears last (bottom of Discord)

**Cog system (v2):**
- Cogs are loaded conditionally in `bot.py:_load_cogs()` based on `features` flags in config
- All cogs receive the bot instance and share `self.db`, `self.scraper`, `self.summoners`
- `bot.tree.sync()` registers slash commands with Discord on startup

**Roast engine (`cogs/roast.py`):**
- 10-second polling loop reads from `bot.new_matches` deque
- `classify_trigger()` determines roast type: `single_loss`, `streak` (2+), `zero_kills`, `perfect_kda`, or `None` (skip)
- `build_roast_context()` assembles the LLM prompt with match details and streak info
- Last 5 roasts for the player are appended with "No repitas estas frases:" to avoid repetition
- `llm.py:VLLMClient` sends to vLLM's OpenAI-compatible `/v1/chat/completions` endpoint with `enable_thinking: false`
- Roast text stored in `roast_history` table. If vLLM is down, the cog silently skips.

**Slash commands (`cogs/commands.py`):**
- `SpyCog` registers an `app_commands.Group` named "spy" with 7 subcommands
- `/spy add` validates the slug, inserts into DB, and appends to in-memory summoner list (no restart needed)
- `/spy remove` soft-deletes from DB and removes from memory
- `/spy stats` aggregates player stats + streak + tilt score into a gold embed
- `/spy leaderboard` ranks all players by win rate (min 10 games)
- `/spy roast` generates an on-demand LLM roast from recent match history
- `/spy champions` shows top 10 champions by games played with win rates
- `/spy h2h` shows head-to-head record between two tracked players

**Analytics (`cogs/analytics.py` + `analytics.py` + `rankings.py`):**
- `compute_tilt_score()` returns 0-100 from four factors: loss streak (0-40), KDA decay (0-25), death rate (0-20), FF/short-game ratio (0-15)
- `AnalyticsCog.check_rivalry()` is called inline from `check_matches` after each insert. Detects same `match_id` with opposite win values between tracked players. Posts purple "RIVALIDAD DETECTADA" embed.
- `weekly_ranking_check` loop fires Monday 10:00 Madrid time (same boundary-crossing pattern as summary GIF)
- `render_power_rankings()` renders a dark-themed Pillow PNG with composite power scores, champion icons, win-rate bars

**Live game alerts (`cogs/live.py`):**
- 2-minute polling loop (configurable via `scraping.live_check_minutes`)
- `scraper.py:parse_in_game_status()` checks for `current-game` class in HTML, extracts champion from banner
- State tracked in `live_games` table: row exists = in game, deleted when indicator disappears
- Table truncated on bot startup to clear stale state from restarts
- Blue Discord embed sent when a player starts a game

**8-hour summary GIF (summary_check loop):**
1. `bot.py:summary_check` runs every 60s, checks if Madrid time crossed a boundary (00:00, 08:00, 16:00) via `should_fire_summary()`
2. `database.py:Database.get_matches_since()` queries matches from the last 8 hours
3. `daily_summary.py:group_by_player()` groups by player name, skips players with zero matches
4. `daily_summary.py:render_player_frame()` renders a Pillow card per player (dark Discord theme, gold accent, champion icons, W/L record, net +/- result)
5. `daily_summary.py:build_summary_gif()` normalizes frame heights, quantizes to palette mode, assembles animated GIF (3s per frame)
6. Sent to Discord as `discord.File`. If nobody played, the whole summary is skipped.

**Champion icons:**
- `champion_icons.py` resolves DDragon CDN URLs: `https://ddragon.leagueoflegends.com/cdn/{version}/img/champion/{key}.png`
- `normalize_champion_name()` handles spaces, apostrophes (lowercase after `'`), and ~3 special cases (Wukong, Renata Glasc, Nunu)
- `download_icon()` caches resized PNGs in `/tmp/leaguespy_icons/`
- Match embeds use `embed.set_thumbnail()` with the icon URL

**Database schema:**
- `summoners` table: id, player_name, summoner_slug, region, current_streak, longest_win_streak, longest_loss_streak, created_at
- `matches` table: id, summoner_id, match_id, champion, win, kills, deaths, assists, game_duration, game_mode, played_at, announced, created_at
- `live_games` table: summoner_id (PK), detected_at, champion, game_mode
- `roast_history` table: id, summoner_id, match_id, roast_text, trigger_type, created_at
- Oracle sequences for auto-incrementing IDs. `setup_db.sql` for v1 schema, `migrate_v2.sql` for v2 additions.

**Key design decisions:**
- The scraper uses a single shared Playwright browser context with stealth JS injection (navigator.webdriver override, fake plugins). A warm-up page load handles cookie consent.
- Oracle DB uses sequences (`summoners_seq`, `matches_seq`, `roast_history_seq`) for auto-incrementing IDs, not identity columns.
- `SummonerConfig.profile_url` generates leagueofgraphs.com URLs with `urllib.parse.quote` for URL-safe slugs.
- `MatchResult.kda_ratio` returns `float("inf")` on zero deaths (not a division error).
- Discord embed is sent *before* the DB insert to prevent lost announcements if the insert fails.
- Summary timestamps are converted from Madrid local time to UTC before querying Oracle (DB server timezone independence).
- `build_summary_gif` runs in `asyncio.run_in_executor` so synchronous icon downloads don't block the event loop.
- DDragon version is cached with a 6-hour TTL so new patches pick up automatically without restart.
- `summary_check` and `roast_loop` are wrapped in try/except so errors don't kill loops permanently.
- The `new_matches` deque (maxlen=100) decouples match detection from roast generation. The roast cog drains it every 10s.
- vLLM's `enable_thinking: false` disables Qwen3.5's chain-of-thought for faster, punchier roast output.
- `/spy add` and `/spy remove` modify both DB and in-memory state so no restart is needed.
- Rivalry detection is zero-cost: just a DB query on `match_id` after each insert. No extra scraping.

## Config

Copy `config.example.yaml` to `config.yaml`. Required fields: `discord.token`, `discord.channel_id`, `oracle.*`, `players[]` with summoner slugs/regions. The `scraping.region` field sets a default region; individual summoners can override it.

v2 config sections:
- `llm.base_url`, `llm.model`, `llm.max_tokens`: vLLM endpoint for roast engine
- `features.roast`, `features.analytics`, `features.live_alerts`, `features.slash_commands`: toggle each cog on/off
- `scraping.live_check_minutes`: polling interval for in-game detection (default 2)

## Dependencies

Core: `discord.py`, `playwright` (async API), `oracledb`, `PyYAML`, `Pillow` (GIF + rankings rendering), `httpx` (icon downloads + vLLM client). Tests use `pytest` + `pytest-asyncio`. vLLM serves Qwen3.5:9B externally (not a pip dependency).
