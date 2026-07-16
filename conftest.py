"""Pytest's process entry point. Loads .env exactly once, before any test
module is collected, so LLM_GATEWAY_* env vars are available without any
library module (integrations/, models/) importing dotenv itself.

Safe when .env is absent — load_dotenv() just no-ops, so the offline suite
is unaffected. A real environment variable already set on the process always
wins over whatever is in .env (load_dotenv's default, non-overriding behavior).
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
