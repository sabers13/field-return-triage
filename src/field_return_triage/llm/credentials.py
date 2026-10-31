"""Read the gateway credential, and never show it.

Only this package reads a credential (``docs/INTERFACES.md`` §0). The lookup order
is fixed by ``PLAN.md`` §2.3 and the R2 brief:

1. the process environment;
2. the file named by ``FRT_ENV_FILE``;
3. ``.env`` in the working directory.

The value is wrapped in :class:`ApiKey`, whose ``repr`` and ``str`` are redacted.
The plain value is reachable only through :meth:`ApiKey.reveal`, which the HTTP
client calls when it builds the ``Authorization`` header and nowhere else.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from field_return_triage.llm.errors import ConfigurationError

__all__ = ["ENV_CANDIDATES", "ApiKey", "load_api_key", "read_env_file"]

#: Environment variable names tried inside each source, in order. The first name is
#: this project's own; the others are the names the gateway ecosystem uses.
ENV_CANDIDATES: tuple[str, ...] = (
    "FRT_API_KEY",
    "OPENCODE_GO_API_KEY",
    "OPENCODE_API_KEY",
)

#: The file used after ``FRT_ENV_FILE`` (PLAN §2.3).
DEFAULT_DOTENV: Path = Path(".env")


class ApiKey:
    """A credential that cannot leak through ``repr``, ``str`` or logging."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        cleaned = value.strip()
        if not cleaned:
            msg = "the configured API key is empty"
            raise ConfigurationError(msg)
        self._value = cleaned

    def reveal(self) -> str:
        """Return the plain value. Only the HTTP client may call this."""
        return self._value

    def __repr__(self) -> str:
        return "ApiKey(<redacted>)"

    __str__ = __repr__

    def __bool__(self) -> bool:
        return True


def read_env_file(path: Path) -> dict[str, str]:
    """Parse a dotenv file into a mapping, without logging any value.

    Supports blank lines, ``#`` comments, an optional ``export`` prefix and
    single- or double-quoted values. The file itself is never echoed anywhere.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"cannot read the env file {path}: {exc.__class__.__name__}"
        raise ConfigurationError(msg) from None

    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        name, separator, value = line.partition("=")
        name = name.strip()
        if not separator or not name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if value:
            values[name] = value
    return values


def _find(mapping: Mapping[str, str]) -> str | None:
    for name in ENV_CANDIDATES:
        value = mapping.get(name, "").strip()
        if value:
            return value
    return None


def load_api_key(
    environ: Mapping[str, str] | None = None,
    *,
    env_file: Path | None = None,
    dotenv: Path = DEFAULT_DOTENV,
) -> ApiKey:
    """Resolve the credential from the environment, ``FRT_ENV_FILE``, then ``.env``.

    ``env_file`` is an explicit override for tests and callers; it replaces the
    ``FRT_ENV_FILE`` lookup but not the process environment, which still wins.

    Raises :class:`ConfigurationError` when no source yields a key. The message
    names the sources and variable names, never a value.
    """
    process = os.environ if environ is None else environ

    direct = _find(process)
    if direct is not None:
        return ApiKey(direct)

    named = env_file
    if named is None:
        configured = process.get("FRT_ENV_FILE", "").strip()
        named = Path(configured) if configured else None
    if named is not None:
        if not named.is_file():
            msg = f"FRT_ENV_FILE does not name a readable file: {named}"
            raise ConfigurationError(msg)
        found = _find(read_env_file(named))
        if found is not None:
            return ApiKey(found)

    if dotenv.is_file():
        found = _find(read_env_file(dotenv))
        if found is not None:
            return ApiKey(found)

    names = ", ".join(ENV_CANDIDATES)
    msg = (
        "no API key configured: set one of "
        f"{names} in the process environment, the FRT_ENV_FILE file, or .env"
    )
    raise ConfigurationError(msg)
