# config.py
"""
Central configuration: API keys, model name, and directory setup.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root
load_dotenv()

# ─────────────────────────────────────────────────────────────
# Gemini API
# ─────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-2.5-flash"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# ─────────────────────────────────────────────────────────────
# Directories (auto-created on import)
# ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.resolve()
UPLOAD_DIR = BASE_DIR / "uploads"
GENERATED_DIR = BASE_DIR / "generated"
STATIC_DIR = BASE_DIR / "static"

for d in (UPLOAD_DIR, GENERATED_DIR, STATIC_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────────────────────
# Startup warning if the key is missing
# ─────────────────────────────────────────────────────────────
if not GEMINI_API_KEY:
    print("⚠️  WARNING: GEMINI_API_KEY is not set. Add it to your .env file.")