#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/jasperan/LeagueSpy.git"
PROJECT_DIR="${PROJECT_DIR:-$(pwd)/LeagueSpy}"

# If --local flag is passed, use current directory instead of cloning
if [[ "${1:-}" == "--local" ]]; then
    PROJECT_DIR="$(pwd)"
else
    echo "Cloning LeagueSpy..."
    git clone "$REPO_URL" "$PROJECT_DIR"
fi

cd "$PROJECT_DIR"

echo "Creating conda environment..."
conda create -n leaguespy python=3.12 -y
conda run -n leaguespy pip install -r requirements.txt

echo "Installing scrapling browsers..."
conda run -n leaguespy scrapling install || conda run -n leaguespy python -c "from scrapling.fetchers import StealthyFetcher; StealthyFetcher.install()"

if [[ ! -f config.yaml ]]; then
    echo "Copying config template..."
    cp config.example.yaml config.yaml
fi

echo ""
echo "Done! Next steps:"
echo "  1. Edit config.yaml with your Discord bot token, channel ID, and summoner list"
echo "  2. Set up the Oracle DB user (see scripts/setup_db.sql)"
echo "  3. Run: conda activate leaguespy && python -m src.bot"
