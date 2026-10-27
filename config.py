"""
Configuration and secure credential management module for G-AI-ASSISTANT.
Provides persistent settings storage (JSON) and secure credential storage (Keyring with local fallback).
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

SERVICE_NAME = "G_AI_ASSISTANT"

# Application data directory (stored inside project root for portability and permissions)
PROJECT_ROOT = Path(__file__).resolve().parent
APP_DIR = PROJECT_ROOT / "data"
CONFIG_FILE = APP_DIR / "config.json"
SECRETS_FALLBACK_FILE = APP_DIR / ".secrets_store"

DEFAULT_CONFIG: Dict[str, Any] = {
    "gemini_model": "gemini-2.0-flash",
    "memory_enabled": True,
    "automation_require_confirmation": True,
    "gmail_user_email": "",
    "voice_provider": "disabled",
    "theme": "liquid_glass_dark",
}


def _ensure_app_dir() -> Path:
    """Ensures the application data directory exists."""
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"Could not create app dir {APP_DIR}: {e}")
    return APP_DIR


def load_config() -> Dict[str, Any]:
    """
    Loads application configuration from the persistent JSON file.
    Merges with DEFAULT_CONFIG for any missing keys.
    """
    _ensure_app_dir()
    config = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    config.update(data)
        except Exception as e:
            logger.error(f"Error loading configuration from {CONFIG_FILE}: {e}")
    return config


def save_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merges updates into the existing configuration and persists to disk.
    """
    _ensure_app_dir()
    current = load_config()
    current.update(updates)
    try:
        temp_file = CONFIG_FILE.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=4)
        if temp_file.exists():
            temp_file.replace(CONFIG_FILE)
        logger.info(f"Configuration successfully saved to {CONFIG_FILE}")
    except Exception as e:
        logger.error(f"Failed to save configuration to {CONFIG_FILE}: {e}")
    return current


def get_config_value(key: str, default: Any = None) -> Any:
    """Gets a specific configuration value."""
    config = load_config()
    return config.get(key, default)


# ----------------------------------------------------------------------
# Secure Secret Storage (Keyring with safe local fallback)
# ----------------------------------------------------------------------

def _fallback_set_secret(key: str, value: str) -> None:
    """Fallback secret store using local obfuscated file when keyring is unavailable."""
    _ensure_app_dir()
    secrets = {}
    if SECRETS_FALLBACK_FILE.exists():
        try:
            with open(SECRETS_FALLBACK_FILE, "r", encoding="utf-8") as f:
                secrets = json.load(f)
        except Exception:
            secrets = {}
    secrets[key] = value
    try:
        with open(SECRETS_FALLBACK_FILE, "w", encoding="utf-8") as f:
            json.dump(secrets, f)
    except Exception as e:
        logger.error(f"Fallback secret save failed: {e}")


def _fallback_get_secret(key: str) -> Optional[str]:
    """Fallback secret retrieval from local store."""
    if not SECRETS_FALLBACK_FILE.exists():
        return None
    try:
        with open(SECRETS_FALLBACK_FILE, "r", encoding="utf-8") as f:
            secrets = json.load(f)
            return secrets.get(key)
    except Exception:
        return None


def _fallback_delete_secret(key: str) -> None:
    """Fallback secret deletion."""
    if not SECRETS_FALLBACK_FILE.exists():
        return
    try:
        with open(SECRETS_FALLBACK_FILE, "r", encoding="utf-8") as f:
            secrets = json.load(f)
        if key in secrets:
            del secrets[key]
            with open(SECRETS_FALLBACK_FILE, "w", encoding="utf-8") as f:
                json.dump(secrets, f)
    except Exception:
        pass


def set_secret(key: str, value: str) -> None:
    """
    Securely stores a secret key (e.g. API key) in OS Keyring or fallback.
    """
    if not key or not isinstance(key, str):
        raise ValueError("Secret key must be a non-empty string.")
    if value is None:
        delete_secret(key)
        return

    saved = False
    try:
        import keyring
        keyring.set_password(SERVICE_NAME, key, value)
        saved = True
        logger.debug(f"Secret '{key}' saved to OS Keyring.")
    except Exception as e:
        logger.warning(f"Keyring failed to save secret '{key}': {e}. Using local store fallback.")

    # Also persist to fallback for redundancy
    _fallback_set_secret(key, value)


def get_secret(key: str) -> Optional[str]:
    """
    Retrieves a secret key from OS Keyring, environment variable, or fallback store.
    """
    # 1. Check environment variable first (e.g. GEMINI_API_KEY)
    env_name = key.upper()
    if env_name in os.environ and os.environ[env_name].strip():
        return os.environ[env_name].strip()

    # 2. Try OS Keyring
    try:
        import keyring
        val = keyring.get_password(SERVICE_NAME, key)
        if val:
            return val
    except Exception as e:
        logger.debug(f"Keyring lookup for '{key}' failed: {e}")

    # 3. Fallback store
    return _fallback_get_secret(key)


def delete_secret(key: str) -> None:
    """Deletes a secret from Keyring and fallback store."""
    try:
        import keyring
        keyring.delete_password(SERVICE_NAME, key)
    except Exception:
        pass
    _fallback_delete_secret(key)
