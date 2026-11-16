"""Deployment-environment resolution that fails closed.

Every security control (auth gate, tenant seam, dev-only endpoints, .env
writes, tray socket) switches on "are we in production?". Comparing
``os.getenv("APP_ENV") == "production"`` fails *open*: an unset or misspelled
APP_ENV on the hosted instance silently disables auth. Route every such check
through :func:`is_production` instead.

Resolution rules:

* ``APP_ENV`` set to ``production`` / ``development`` / ``test`` (case- and
  whitespace-insensitive) -> that value.
* ``APP_ENV`` set to anything else -> :class:`InvalidAppEnv` (raised at web
  startup by :func:`validate_app_env`, and by every later check).
* ``APP_ENV`` unset/empty and running on Railway (any ``RAILWAY_*`` runtime
  variable present) -> ``production``.
* ``APP_ENV`` unset/empty and not on Railway -> ``development`` (local
  ``start.bat`` keeps working), with a one-time warning.
"""
from __future__ import annotations

import logging
import os

PRODUCTION = "production"
DEVELOPMENT = "development"
TEST = "test"
VALID_APP_ENVS = frozenset({PRODUCTION, DEVELOPMENT, TEST})

logger = logging.getLogger(__name__)
_warned_default = False


class InvalidAppEnv(RuntimeError):
    """APP_ENV holds a value that is not a recognized environment name."""


def on_railway() -> bool:
    """True when Railway runtime variables are present.

    ``*_TOKEN`` names are ignored: a developer's local ``.env`` holds a
    ``RAILWAY_TOKEN`` for the CLI (loaded into os.environ by python-dotenv), and
    that must not flip a local run into production mode.
    """
    return any(
        k.startswith("RAILWAY_") and not k.endswith("_TOKEN") for k in os.environ
    )


def app_env() -> str:
    """Resolve the effective environment name. Raises InvalidAppEnv on garbage."""
    global _warned_default
    raw = (os.environ.get("APP_ENV") or "").strip().lower()
    if raw:
        if raw not in VALID_APP_ENVS:
            raise InvalidAppEnv(
                f"APP_ENV={os.environ.get('APP_ENV')!r} is not recognized; "
                f"expected one of {sorted(VALID_APP_ENVS)}"
            )
        return raw
    if on_railway():
        if not _warned_default:
            logger.warning("APP_ENV is unset on Railway; defaulting to production")
            _warned_default = True
        return PRODUCTION
    if not _warned_default:
        logger.warning(
            "APP_ENV is unset and no Railway runtime detected; "
            "running with development (insecure, local-only) behavior"
        )
        _warned_default = True
    return DEVELOPMENT


def is_production() -> bool:
    """True when production security controls must be enforced."""
    return app_env() == PRODUCTION


def is_dev() -> bool:
    """True for local development/test (security controls relaxed)."""
    return not is_production()


def validate_app_env() -> str:
    """Startup check: resolve APP_ENV once so a bad value aborts the boot."""
    return app_env()
