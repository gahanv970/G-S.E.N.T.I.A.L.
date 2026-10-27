"""
Unit tests for config and credential management.
"""

from pathlib import Path
import tempfile
import pytest

from config import (
    DEFAULT_CONFIG,
    delete_secret,
    get_config_value,
    get_secret,
    load_config,
    save_config,
    set_secret,
)


def test_config_defaults():
    cfg = load_config()
    assert isinstance(cfg, dict)
    assert "gemini_model" in cfg
    assert "memory_enabled" in cfg
    assert "automation_require_confirmation" in cfg


def test_config_save_and_reload():
    test_val = "gemini-2.5-flash"
    save_config({"gemini_model": test_val})
    assert get_config_value("gemini_model") == test_val

    # Restore default
    save_config({"gemini_model": DEFAULT_CONFIG["gemini_model"]})


def test_secrets_management():
    key_name = "test_verification_key_xyz"
    val = "super_secret_token_12345"

    set_secret(key_name, val)
    retrieved = get_secret(key_name)
    assert retrieved == val

    delete_secret(key_name)
    assert get_secret(key_name) is None
