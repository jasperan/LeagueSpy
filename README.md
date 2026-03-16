<div align="center">

# LeagueSpy

<p align="center"><b>Track your friends' League matches. Roast their losses.</b></p>

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg?style=for-the-badge)](https://www.python.org/downloads/)
[![Oracle Database](https://img.shields.io/badge/Oracle-Database_Free-red.svg?style=for-the-badge)](https://www.oracle.com/database/free/)
[![discord.py](https://img.shields.io/badge/discord.py-2.7+-5865F2.svg?style=for-the-badge)](https://discordpy.readthedocs.io/)
[![Playwright](https://img.shields.io/badge/Playwright-stealth-2EAD33.svg?style=for-the-badge)](https://playwright.dev/)
[![Pillow](https://img.shields.io/badge/Pillow-GIF_rendering-ff6f00.svg?style=for-the-badge)](https://python-pillow.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-87_passing-brightgreen.svg?style=for-the-badge)](#running-tests)

</div>

Discord bot that scrapes [leagueofgraphs.com](https://www.leagueofgraphs.com) for League of Legends match history and announces new games in your server. Tracks multiple players and all their smurf accounts from a single config file.

![LeagueSpy Architecture](assets/visual-explainer-hero.png)

## One-Command Install

```bash
curl -fsSL https://raw.githubusercontent.com/jasperan/LeagueSpy/main/install.sh | bash
```

That clones the repo, creates a conda env, and installs everything. You'll just need to fill in `config.yaml` and set up Oracle DB.

<details><summary>Override install location</summary>

```bash
PROJECT_DIR=/opt/leaguespy curl -fsSL https://raw.githubusercontent.com/jasperan/LeagueSpy/main/install.sh | bash
```

</details>

## Features

- **Stealth scraping** via Playwright with bot-detection evasion (spoofed navigator, cookie consent handling, concurrent tab pool)
- **Champion icon thumbnails** on every match embed, pulled from Riot's [Data Dragon CDN](https://developer.riotgames.com/docs/lol#data-dragon)
- **Rich Discord embeds** with champion, KDA, win/loss, game mode, duration, and profile link
- **8-hour summary GIF** sent at 00:00, 08:00, and 16:00 Madrid time. Per-player animated cards showing net W/L, record, and champion icons played
- **Multi-account tracking** for players with multiple summoner accounts (smurfs)
- **Oracle Database** storage for match history and deduplication
- **Configurable polling** interval (default: 5 minutes)
- **Per-summoner region** support (EUW, NA, KR, etc.)

## Discord Embed Preview

![Discord Embeds](assets/slides-embeds.png)

Green sidebar for wins. Red for losses. Each embed shows the champion icon and links to the player's leagueofgraphs profile.

## Prerequisites

- Python 3.12+
- [Conda](https://docs.conda.io/) (recommended) or virtualenv
- Oracle Database (Free tier works fine)
- Discord bot token ([create one here](https://discord.com/developers/applications))

## Manual Setup

**1. Clone and create environment**

```bash
git clone https://github.com/jasperan/LeagueSpy.git
cd LeagueSpy
conda create -n leaguespy python=3.12 -y
conda activate leaguespy
pip install -r requirements.txt
playwright install chromium
```

**2. Set up Oracle Database**

Create the `leaguespy` user in your Oracle instance, then run the schema:

```bash
sqlplus leaguespy/leaguespy@localhost:1523/FREEPDB1 @scripts/setup_db.sql
```

**3. Configure**

```bash
cp config.example.yaml config.yaml
```

Fill in your Discord bot token, channel ID, and summoner list:

```yaml
discord:
  token: "YOUR_DISCORD_BOT_TOKEN"
  channel_id: 0  # Right-click channel -> Copy ID

oracle:
  user: "leaguespy"
  password: "leaguespy"
  dsn: "localhost:1523/FREEPDB1"

scraping:
  interval_minutes: 5
  region: "euw"  # default region

players:
  - name: "jasper"
    summoners:
      - slug: "jasper-1971"
        region: "euw"
```

Enable Developer Mode in Discord settings to copy channel IDs.

**4. Run**

```bash
conda activate leaguespy
python -m src.bot
```

## Adding Players and Smurfs

Each player can have multiple summoner accounts:

```yaml
players:
  - name: "jasper"
    summoners:
      - slug: "jasper-1971"
        region: "euw"
      - slug: "smurf-account-1234"
        region: "euw"
  - name: "friend1"
    summoners:
      - slug: "friend1-tag"
        region: "na"
```

The `slug` is the URL-safe summoner identifier from leagueofgraphs. Go to `leagueofgraphs.com/summoner/{region}/{slug}` to find yours.

## How It Works

![Pipeline Flow](assets/slides-flow.png)

**Match tracking:** Every 5 minutes, the bot scrapes each summoner's leagueofgraphs profile using a stealth Playwright browser (3 concurrent tabs). New match IDs get stored in Oracle DB and announced via Discord embed. Already-seen matches are skipped.

**Summary GIF:** Three times a day (00:00, 08:00, 16:00 Madrid time), the bot queries all matches from the last 8 hours, groups them by player, renders a Pillow frame per player (dark Discord theme, champion icons, W/L record, net +/- badge), and sends the animated GIF to the channel. Players with zero matches in the window are skipped.

## Project Structure

```
src/
  bot.py             # Bot core with two async task loops (matches + summary)
  scraper.py         # leagueofgraphs scraper (Playwright stealth browser)
  database.py        # Oracle DB layer (oracledb)
  embeds.py          # Discord rich embed builder with champion thumbnails
  models.py          # Data models (SummonerConfig, MatchResult)
  champion_icons.py  # Riot DDragon CDN icon resolution and caching
  daily_summary.py   # 8-hour summary GIF renderer (Pillow)
scripts/
  setup_db.sql       # Oracle schema (sequences + tables)
tests/               # 87 unit and integration tests
assets/
  visual-explainer.html  # Interactive architecture diagram
  slides.html            # Presentation deck
```

## Running Tests

```bash
conda activate leaguespy
pytest tests/ -v
```

87 tests covering the scraper, database, embeds, champion icons, summary GIF renderer, and scheduler boundary logic.

## License

MIT
