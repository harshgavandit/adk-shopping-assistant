import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Tests never use the user's credentials or Redis instance.
os.environ["OPENAI_API_KEY"] = "test-key"
os.environ["LLM_MODEL"] = "gpt-4o-mini"
os.environ["REDIS_URL"] = "redis://127.0.0.1:6381/15"
