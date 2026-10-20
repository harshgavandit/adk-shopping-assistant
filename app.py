"""Vercel entry point; the local ADK development server remains unchanged."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "ADK_Shopping"))
from cloud_server import app
