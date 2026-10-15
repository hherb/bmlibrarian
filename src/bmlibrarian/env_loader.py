"""Select and load the .env file that configures BMLibrarian (database, paths).

By default the user configuration ``~/.bmlibrarian/.env`` is loaded, falling
back to a ``.env`` in the current directory. Setting ``BMLIBRARIAN_ENV_FILE``
selects another file explicitly, e.g. the PostgreSQL 18 configuration
``~/.bmlibrarian/.env_pg18``. An explicitly named file that does not exist is an
error, never a silent fallback: falling back would connect the caller to
whatever database the default file names.
"""

import os
from pathlib import Path
from typing import Mapping, Optional

from dotenv import load_dotenv

ENV_FILE_VARIABLE = "BMLIBRARIAN_ENV_FILE"
USER_CONFIG_DIR_NAME = ".bmlibrarian"
USER_ENV_FILE_NAME = ".env"


def resolve_env_file(environ: Mapping[str, str], home: Path) -> Optional[Path]:
    """Return the env file to load, or None if there is no user env file.

    Args:
        environ: Environment mapping (usually ``os.environ``).
        home: Home directory containing ``.bmlibrarian/``.

    Returns:
        The explicit file named by ``BMLIBRARIAN_ENV_FILE``, else
        ``~/.bmlibrarian/.env`` if it exists, else None.

    Raises:
        FileNotFoundError: If ``BMLIBRARIAN_ENV_FILE`` names a missing file.
    """
    explicit = environ.get(ENV_FILE_VARIABLE, "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise FileNotFoundError(
                f"{ENV_FILE_VARIABLE}={explicit!r} does not exist; refusing to fall back "
                f"to the default configuration")
        return path
    user_env = home / USER_CONFIG_DIR_NAME / USER_ENV_FILE_NAME
    return user_env if user_env.is_file() else None


def load_bmlibrarian_env(home: Optional[Path] = None, override: bool = True) -> Optional[Path]:
    """Load the selected env file into ``os.environ``.

    Args:
        home: Home directory (defaults to the user's home).
        override: Whether file values replace existing environment variables.
            True keeps the established rule that the user configuration takes
            precedence over the shell environment.

    Returns:
        The file that was loaded, or None if only a current-directory ``.env``
        (if any) was loaded.

    Raises:
        FileNotFoundError: If ``BMLIBRARIAN_ENV_FILE`` names a missing file.
    """
    path = resolve_env_file(os.environ, home or Path.home())
    if path is not None:
        load_dotenv(path, override=override)
    else:
        load_dotenv()  # development convenience: .env in the current directory
    return path
