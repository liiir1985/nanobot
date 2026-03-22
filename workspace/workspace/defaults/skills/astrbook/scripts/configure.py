#!/usr/bin/env python3
"""
Astrbook Configuration Helper

This script helps set up Astrbook credentials for the bot.
Run this script to configure your API base URL and token.
"""

import json
import os
from pathlib import Path


def get_config_path() -> Path:
    """Get the config file path."""
    # Try XDG config first, then fallback to home directory
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        config_dir = Path(xdg_config) / "astrbook"
    else:
        config_dir = Path.home() / ".config" / "astrbook"
    
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "credentials.json"


def load_config() -> dict:
    """Load existing config or return empty dict."""
    config_path = get_config_path()
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(config: dict) -> None:
    """Save config to file."""
    config_path = get_config_path()
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"✅ Config saved to: {config_path}")


def main():
    print("🤖 Astrbook Configuration Helper")
    print("=" * 40)
    
    config = load_config()
    
    # API Base URL
    current_base = config.get("api_base", "http://localhost:8000")
    print(f"\nCurrent API Base: {current_base}")
    new_base = input("Enter new API Base URL (or press Enter to keep): ").strip()
    if new_base:
        config["api_base"] = new_base
    elif "api_base" not in config:
        config["api_base"] = current_base
    
    # Token
    current_token = config.get("token", "")
    if current_token:
        masked = current_token[:10] + "..." + current_token[-4:] if len(current_token) > 14 else "***"
        print(f"\nCurrent Token: {masked}")
    else:
        print("\nNo token configured.")
    
    new_token = input("Enter new Bot Token (or press Enter to keep): ").strip()
    if new_token:
        config["token"] = new_token
    
    # Bot Name
    current_name = config.get("bot_name", "")
    print(f"\nCurrent Bot Name: {current_name or '(not set)'}")
    new_name = input("Enter your bot name (or press Enter to keep): ").strip()
    if new_name:
        config["bot_name"] = new_name
    
    save_config(config)
    
    print("\n" + "=" * 40)
    print("Configuration complete!")
    print("\nYou can also set environment variables:")
    print(f"  export ASTRBOOK_API_BASE=\"{config.get('api_base', '')}\"")
    print(f"  export ASTRBOOK_TOKEN=\"{config.get('token', 'your_token')}\"")


if __name__ == "__main__":
    main()
