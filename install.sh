#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/jasperan/LeagueSpy.git"
PROJECT_DIR="${PROJECT_DIR:-$(pwd)/LeagueSpy}"
ENV_BACKEND="${LEAGUESPY_ENV_BACKEND:-auto}" # auto|conda|venv
ENV_NAME="${LEAGUESPY_ENV_NAME:-leaguespy}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-$PROJECT_DIR/.venv}"

usage() {
    cat <<'EOF'
Usage: install.sh [--local]

Options:
  --local   Use the current directory instead of cloning the repo first.

Environment overrides:
  PROJECT_DIR            Target checkout directory (default: ./LeagueSpy)
  LEAGUESPY_ENV_BACKEND  auto | conda | venv (default: auto)
  LEAGUESPY_ENV_NAME     Conda environment name (default: leaguespy)
  PYTHON_BIN             Python executable for venv mode (default: python3)
  VENV_DIR               Virtualenv location for venv mode (default: $PROJECT_DIR/.venv)
EOF
}

clone_repo=true
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
    exit 0
fi
if [[ "${1:-}" == "--local" ]]; then
    clone_repo=false
    PROJECT_DIR="$(pwd)"
fi

if [[ "$clone_repo" == true ]]; then
    echo "Cloning LeagueSpy into $PROJECT_DIR..."
    git clone "$REPO_URL" "$PROJECT_DIR"
fi

cd "$PROJECT_DIR"

resolve_backend() {
    case "$ENV_BACKEND" in
        conda)
            command -v conda >/dev/null 2>&1 || {
                echo "Requested conda backend, but conda is not installed." >&2
                exit 1
            }
            echo "conda"
            ;;
        venv)
            echo "venv"
            ;;
        auto)
            if command -v conda >/dev/null 2>&1; then
                echo "conda"
            else
                echo "venv"
            fi
            ;;
        *)
            echo "Unsupported LEAGUESPY_ENV_BACKEND: $ENV_BACKEND" >&2
            exit 1
            ;;
    esac
}

BACKEND="$(resolve_backend)"

if [[ "$BACKEND" == "conda" ]]; then
    if conda env list | awk '{print $1}' | grep -Fxq "$ENV_NAME"; then
        echo "Using existing conda environment '$ENV_NAME'..."
    else
        echo "Creating conda environment '$ENV_NAME'..."
        conda create -n "$ENV_NAME" python=3.12 -y
    fi
    PYTHON_CMD=(conda run -n "$ENV_NAME" python)
    ACTIVATE_HINT="conda activate $ENV_NAME"
else
    echo "Creating virtualenv at $VENV_DIR..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    PYTHON_CMD=("$VENV_DIR/bin/python")
    ACTIVATE_HINT="source $VENV_DIR/bin/activate"
    "${PYTHON_CMD[@]}" -m pip install --upgrade pip
fi

echo "Installing Python dependencies..."
# Equivalent baseline command: python -m pip install -r requirements.txt
"${PYTHON_CMD[@]}" -m pip install -r requirements.txt

echo "Installing Playwright Chromium browser..."
# Equivalent baseline command: python -m playwright install chromium
"${PYTHON_CMD[@]}" -m playwright install chromium

echo "Running offline preflight..."
"${PYTHON_CMD[@]}" -m src.cli doctor --config config.example.yaml --offline

if [[ ! -f config.yaml ]]; then
    echo "Copying config template..."
    cp config.example.yaml config.yaml
fi

echo
echo "Done! Next steps:"
echo "  1. Activate the environment: $ACTIVATE_HINT"
echo "  2. Edit config.yaml with your Discord bot token, channel ID, and summoner list"
echo "  3. Set up the Oracle DB user (see scripts/setup_db.sql)"
echo "  4. Run a local showcase: ${PYTHON_CMD[*]} -m src.cli showcase --output-dir showcase-output"
echo "  5. Start the bot: ${PYTHON_CMD[*]} -m src.bot --config config.yaml"
