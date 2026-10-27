"""Import first: applies administrator-saved settings before other modules read them."""

from pathlib import Path

from dotenv import load_dotenv

import runtime_settings

# Load the server's .env first (as providers.py would later) so it is the
# baseline a reset restores, and saved values are applied on top of it.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
runtime_settings.apply_saved()
