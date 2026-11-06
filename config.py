"""
Configuration and Environment Variable Loader for Autonomous Bug Detection & Repair Agent.
Supports loading from a local .env file or system environment variables without requiring external dependencies.
"""

import os
from pathlib import Path
from typing import Optional, Dict

BASE_DIR = Path(__file__).resolve().parent

def load_env_file(filepath: Optional[Path] = None) -> Dict[str, str]:
    """Parse a .env file and set environment variables if not already set."""
    if filepath is None:
        filepath = BASE_DIR / ".env"
    
    loaded = {}
    if not filepath.exists():
        return loaded

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key not in os.environ:
                        os.environ[key] = val
                    loaded[key] = val
    except Exception as e:
        print(f"Warning: Failed to read .env file: {e}")
    
    return loaded

# Auto-load .env on import
load_env_file()

class Config:
    """Application configuration parameters."""
    GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    DEFAULT_LLM_PROVIDER: str = os.getenv("DEFAULT_LLM_PROVIDER", "gemini")  # "gemini", "openai", "local"
    DEFAULT_MODEL_NAME: str = os.getenv("DEFAULT_MODEL_NAME", "gemini-2.0-flash")
    
    # Sandbox configuration
    SANDBOX_TIMEOUT_SECONDS: int = int(os.getenv("SANDBOX_TIMEOUT_SECONDS", "8"))
    MAX_REPAIR_ITERATIONS: int = int(os.getenv("MAX_REPAIR_ITERATIONS", "3"))
    MAX_OUTPUT_CHARS: int = int(os.getenv("MAX_OUTPUT_CHARS", "10000"))
    
    # Database configuration
    DB_PATH: Path = BASE_DIR / "database" / "bug_agent.db"

    @classmethod
    def has_llm_key(cls) -> bool:
        """Check if any LLM API key is present."""
        return bool(cls.GEMINI_API_KEY or cls.OPENAI_API_KEY)

    @classmethod
    def get_active_provider(cls) -> str:
        """Return the active provider or 'local' if no key is configured."""
        if cls.DEFAULT_LLM_PROVIDER == "openai" and cls.OPENAI_API_KEY:
            return "openai"
        if cls.GEMINI_API_KEY:
            return "gemini"
        if cls.OPENAI_API_KEY:
            return "openai"
        return "local"

