# LeagueSpy

Discord bot that scrapes [op.gg](https://op.gg) for League of Legends match history and announces new games in a Discord channel. Track multiple players and their smurf accounts from a single config file.

## Features

- Scrapes op.gg match history using headless browser (scrapling)
- Posts rich Discord embeds with champion, KDA, win/loss, game mode, and duration
- Tracks multiple players with multiple summoner accounts each
- Oracle Database storage for match history and deduplication
- Configurable polling interval (default: 5 minutes)
- Per-summoner region support (EUW, NA, KR, etc.)

## Prerequisites

- Python 3.12+
- [Conda](https://docs.conda.io/) (recommended) or virtualenv
- Oracle Database (Free tier works fine)
- Discord bot token ([create one here](https://discord.com/developers/applications))

## Quick Start

### Option A: Install Script

```bash
curl -fsSL https://raw.githubusercontent.com/jasperan/LeagueSpy/main/install.sh | bash
```

Or clone first, then run:

```bash
git clone https://github.com/jasperan/LeagueSpy.git
cd LeagueSpy
bash install.sh --local
```

### Option B: Manual Setup

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

If that fails, try:

```python
python -c "from scrapling.fetchers import StealthyFetcher; StealthyFetcher.install()"
```

3. **Set up Oracle Database**

Create the `leaguespy` user in your Oracle instance, then run the schema script:

```bash
sqlplus leaguespy/leaguespy@localhost:1523/FREEPDB1 @scripts/setup_db.sql
```

Or skip this step entirely. The bot creates tables automatically on first run.

4. **Configure**

```bash
cp config.example.yaml config.yaml
# Edit config.yaml with your values
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

Add new players under the `players` list. Each player can have multiple summoner accounts:

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
tests/          # Unit and integration tests
```

## Running Tests

```bash
conda activate leaguespy
pytest tests/ -v
```

## License

MIT
