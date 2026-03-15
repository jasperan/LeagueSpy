<div align="center">

# LeagueSpy

<p align="center"><b>Track your friends' League matches. Roast their losses.</b></p>

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg?style=for-the-badge)](https://www.python.org/downloads/)
[![Oracle Database](https://img.shields.io/badge/Oracle-Database_Free-red.svg?style=for-the-badge)](https://www.oracle.com/database/free/)
[![discord.py](https://img.shields.io/badge/discord.py-2.7+-5865F2.svg?style=for-the-badge)](https://discordpy.readthedocs.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-37_passing-brightgreen.svg?style=for-the-badge)](#running-tests)

</div>

Discord bot that scrapes [op.gg](https://op.gg) for League of Legends match history and announces new games in your server. Track multiple players and all their smurf accounts from a single config file.

![LeagueSpy Architecture](assets/visual-explainer-hero.png)

## Features

- **op.gg scraping** with headless browser stealth (scrapling's StealthyFetcher)
- **Rich Discord embeds** with champion, KDA, win/loss, game mode, and duration
- **Multi-account tracking** for players with multiple summoner accounts
- **Oracle Database** storage for match history and deduplication
- **Configurable polling** interval (default: 5 minutes)
- **Per-summoner region** support (EUW, NA, KR, etc.)

## Discord Embed Preview

![Discord Embeds](assets/slides-embeds.png)

Green sidebar for wins. Red for losses. Each embed links to the player's op.gg profile.

## Setup

<!-- one-command-install -->
> **One-command install** -- clone, configure, and run in a single step:
>
> ```bash
> curl -fsSL https://raw.githubusercontent.com/jasperan/LeagueSpy/main/install.sh | bash
> ```
>
> <details><summary>Advanced options</summary>
>
> Override install location:
> ```bash
> PROJECT_DIR=/opt/leaguespy curl -fsSL https://raw.githubusercontent.com/jasperan/LeagueSpy/main/install.sh | bash
> ```
>
> Or install manually:
> ```bash
> git clone https://github.com/jasperan/LeagueSpy.git
> cd LeagueSpy
> # See below for setup instructions
> ```
> </details>

### Prerequisites

- Python 3.12+
- [Conda](https://docs.conda.io/) (recommended) or virtualenv
- Oracle Database (Free tier works fine)
- Discord bot token ([create one here](https://discord.com/developers/applications))

### Manual Setup

1. **Clone and create environment**

```bash
git clone https://github.com/jasperan/LeagueSpy.git
cd LeagueSpy
conda create -n leaguespy python=3.12 -y
conda activate leaguespy
pip install -r requirements.txt
```

2. **Install scrapling browsers**

```bash
scrapling install
```

3. **Set up Oracle Database**

Create the `leaguespy` user in your Oracle instance, then run the schema:

```bash
sqlplus leaguespy/leaguespy@localhost:1523/FREEPDB1 @scripts/setup_db.sql
```

4. **Configure**

```bash
cp config.example.yaml config.yaml
# Edit config.yaml with your Discord bot token, channel ID, and summoner list
```

5. **Run**

```bash
conda activate leaguespy
python -m src.bot
```

## Configuration

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

The `slug` is the URL-safe summoner identifier from op.gg. Go to `op.gg/summoners/{region}/{slug}` to find yours.

## How It Works

![Pipeline Flow](assets/slides-flow.png)

Every 5 minutes, the bot scrapes each tracked summoner's op.gg profile. New match IDs get stored in Oracle DB and announced via Discord embed. Already-seen matches are skipped.

## Project Structure

```
src/
  bot.py        # Bot core with async scheduler
  scraper.py    # op.gg scraper (scrapling + StealthyFetcher)
  database.py   # Oracle DB layer (oracledb)
  embeds.py     # Discord rich embed builder
  models.py     # Data models (SummonerConfig, MatchResult)
scripts/
  setup_db.sql  # Oracle schema (sequences + tables)
tests/          # 37 unit and integration tests
assets/
  visual-explainer.html  # Interactive architecture diagram
  slides.html            # Presentation deck
```

## Running Tests

```bash
conda activate leaguespy
pytest tests/ -v
```

## License

MIT
