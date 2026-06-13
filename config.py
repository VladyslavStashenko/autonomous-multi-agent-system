import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    api_key: str
    api_keys: list[str]
    model: str = "gemini-2.5-flash"
    max_eval_attempts: int = 3
    max_agent_steps: int = 15


def get_settings() -> Settings:
    api_key = os.getenv("API_KEY", "").strip()
    api_keys = [key.strip() for key in os.getenv("GEMINI_API_KEYS", "").split(",") if key.strip()]
    if not api_keys and api_key:
        api_keys = [api_key]
    if not api_keys:
        raise ValueError("GEMINI_API_KEYS or API_KEY environment variable is not set.")
    if not api_key:
        api_key = api_keys[0]
    return Settings(api_key=api_key, api_keys=api_keys)
