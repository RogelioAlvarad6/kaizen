"""App configuration, loaded from backend/.env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")

# Obsidian vault for the (optional, parked) AI wiki features. Set VAULT_PATH in backend/.env.
VAULT_PATH = Path(os.getenv("VAULT_PATH", str(Path.home() / "Documents" / "Obsidian Vault")))
WIKI_FOLDER = os.getenv("WIKI_FOLDER", "AI-Wiki")
WIKI_ROOT = VAULT_PATH / WIKI_FOLDER

DB_PATH = Path(os.getenv("DB_PATH", str(BACKEND_DIR / "data" / "sims.db")))
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "claude-opus-5-5")
DEFAULT_EFFORT = os.getenv("DEFAULT_EFFORT", "medium")

# Models offered in the block inspector. Prices are USD per 1M tokens (input, output).
MODELS = {
    "claude-opus-5-5": {"label": "Claude Opus 5.5 (smartest)", "price": (4.00, 20.00)},
    "claude-sonnet-5-5": {"label": "Claude Sonnet 5.5 (balanced)", "price": (2.00, 10.00)},
    "claude-haiku-5-5": {"label": "Claude Haiku 5.5 (cheapest)", "price": (0.10, 0.50)},
}
EFFORTS = ["low", "medium", "high", "xhigh", "max"]

# Soft monthly budget shown on the dashboard (you also set a hard cap in the Anthropic console).
MONTHLY_BUDGET_USD = float(os.getenv("MONTHLY_BUDGET_USD", "20"))
