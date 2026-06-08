from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    tenant_id: str
    client_id: str
    ai_api_key: str
    ai_model: str
    ai_base_url: str | None
    mail_folder: str
    max_messages: int
    dry_run: bool
    config_path: Path

    @property
    def provider_label(self) -> str:
        if self.ai_base_url and "deepseek" in self.ai_base_url.lower():
            return "deepseek"
        return os.getenv("AI_PROVIDER", "openai").strip().lower() or "openai"


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y"}


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def load_settings() -> Settings:
    tenant_id = os.getenv("MS_TENANT_ID", "").strip()
    client_id = os.getenv("MS_CLIENT_ID", "").strip()

    # New provider-agnostic names are preferred, while OPENAI_* stays supported
    # for backward compatibility with the first MVP package.
    ai_api_key = _first_env("AI_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY")
    ai_model = _first_env("AI_MODEL", "DEEPSEEK_MODEL", "OPENAI_MODEL")
    ai_base_url = _first_env("AI_BASE_URL", "DEEPSEEK_BASE_URL", "OPENAI_BASE_URL", default="") or None

    mail_folder = os.getenv("MAIL_FOLDER", "AI Intake").strip()
    max_messages = int(os.getenv("MAX_MESSAGES", "5"))
    dry_run = _get_bool("DRY_RUN", False)
    config_path = Path(os.getenv("CONFIG_PATH", "config.yaml"))

    missing = []
    if not tenant_id:
        missing.append("MS_TENANT_ID")
    if not client_id:
        missing.append("MS_CLIENT_ID")
    if not ai_api_key:
        missing.append("AI_API_KEY or DEEPSEEK_API_KEY")
    if not ai_model:
        missing.append("AI_MODEL or DEEPSEEK_MODEL")
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    return Settings(
        tenant_id=tenant_id,
        client_id=client_id,
        ai_api_key=ai_api_key,
        ai_model=ai_model,
        ai_base_url=ai_base_url,
        mail_folder=mail_folder,
        max_messages=max_messages,
        dry_run=dry_run,
        config_path=config_path,
    )


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)
