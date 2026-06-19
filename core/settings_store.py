# ============================================================
#   core/settings_store.py — Runtime, teacher-editable settings
#   Stored as JSON in the writable DATA_DIR (NOT in code/.env).
#   Lets a non-technical teacher set their own API key + model
#   from inside the app, no code editing required.
# ============================================================

import json
import logging
import config

logger = logging.getLogger("settings_store")

SETTINGS_PATH = config.DATA_DIR / "user_settings.json"

# Languages the grader can be told to expect.
LANGUAGES = ["Auto (detect)", "English", "Urdu", "Roman Urdu", "Mixed (English + Urdu)"]


def _defaults() -> dict:
    """Defaults fall back to whatever config loaded from .env, so the
    app keeps working out of the box even before the teacher changes anything."""
    return {
        "api_key":          config.NVIDIA_API_KEY,
        "api_key2":         getattr(config, "NVIDIA_API_KEY2", ""),  # backup key for failover
        "base_url":         config.NVIDIA_BASE_URL,
        "model":            config.NVIDIA_MODEL,
        "fast_model":       getattr(config, "NVIDIA_FAST_MODEL", "meta/llama-3.1-8b-instruct"),
        "vision_model":     config.NVIDIA_VISION_MODEL,
        "temperature":      config.AI_TEMPERATURE,
        "language":         "Auto (detect)",
        "theme":            "dark",
        "license_accepted": False,
        # Email (teacher's own Gmail + App Password) for sending report cards.
        "email_address":      "",
        "email_app_password": "",
        "email_sender_name":  "",
        # Students' email domain — their address is built as <roll>@<domain>.
        "email_domain":       "@umt.edu.pk",
    }


_cache = None


def load(force: bool = False) -> dict:
    """Merge saved settings over the .env defaults. Cached after first read."""
    global _cache
    if _cache is not None and not force:
        return _cache
    data = _defaults()
    try:
        if SETTINGS_PATH.exists():
            saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            for k, v in saved.items():
                # Don't let a blank saved value wipe out a working default
                # (e.g. keep the bundled API key if the teacher never set one).
                if isinstance(v, str) and v.strip() == "" and k not in ("language", "theme"):
                    continue
                data[k] = v
    except Exception as e:
        logger.error(f"Could not read settings ({e}); using defaults.")
    _cache = data
    return data


def save(updates: dict) -> dict:
    """Patch and persist settings. Returns the full merged dict."""
    data = load(force=True)
    data.update(updates or {})
    try:
        SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Settings saved.")
    except Exception as e:
        logger.error(f"Could not save settings: {e}")
    global _cache
    _cache = data
    return data


def get(key: str, default=None):
    return load().get(key, default)


def is_license_accepted() -> bool:
    return bool(load().get("license_accepted"))


def accept_license():
    save({"license_accepted": True})
