"""CLI Authentication Helper Module.

Provides authentication utilities for BMLibrarian CLI applications,
including user login, session management, and config integration.
"""

import argparse
import getpass
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from psycopg import Connection

logger = logging.getLogger(__name__)

# Session token file location
SESSION_TOKEN_FILE = Path.home() / ".bmlibrarian" / ".session_token"


@dataclass
class CLIAuthResult:
    """Result of CLI authentication attempt.

    Attributes:
        success: Whether authentication was successful.
        user_id: User ID if authenticated, None otherwise.
        username: Username if authenticated, None otherwise.
        session_token: Session token if authenticated, None otherwise.
        error_message: Error message if authentication failed, None otherwise.
    """
    success: bool
    user_id: Optional[int] = None
    username: Optional[str] = None
    session_token: Optional[str] = None
    error_message: Optional[str] = None


def add_auth_arguments(parser: argparse.ArgumentParser) -> None:
    """Add authentication-related arguments to an argument parser.

    Adds --user, --password, and --session-token arguments to the parser.
    These arguments enable optional user authentication for CLI applications.

    Args:
        parser: The argument parser to add arguments to.

    Example:
        parser = argparse.ArgumentParser()
        add_auth_arguments(parser)
        args = parser.parse_args()
    """
    auth_group = parser.add_argument_group(
        'Authentication',
        'Optional user authentication for personalized settings'
    )

    auth_group.add_argument(
        '--user', '-u',
        type=str,
        metavar='USERNAME',
        help='Username for authentication (enables database-backed settings)'
    )

    auth_group.add_argument(
        '--password', '-p',
        type=str,
        metavar='PASSWORD',
        help='Password for authentication (will prompt if --user provided without --password)'
    )

    auth_group.add_argument(
        '--session-token',
        type=str,
        metavar='TOKEN',
        help='Session token from previous login (alternative to --user/--password)'
    )

    auth_group.add_argument(
        '--save-session',
        action='store_true',
        help='Save session token for future use (with --user/--password)'
    )

    auth_group.add_argument(
        '--logout',
        action='store_true',
        help='Clear saved session token and exit'
    )


def add_config_sync_arguments(parser: argparse.ArgumentParser) -> None:
    """Add configuration sync arguments to an argument parser.

    Adds arguments for syncing configuration between JSON files and database.

    Args:
        parser: The argument parser to add arguments to.
    """
    config_group = parser.add_argument_group(
        'Configuration Sync',
        'Sync settings between JSON files and database (requires authentication)'
    )

    config_group.add_argument(
        '--sync-to-db',
        action='store_true',
        help='Push current JSON config to database (requires --user)'
    )

    config_group.add_argument(
        '--sync-from-db',
        action='store_true',
        help='Pull database settings to local JSON config (requires --user)'
    )

    config_group.add_argument(
        '--export-config',
        type=str,
        metavar='FILE',
        help='Export current configuration to JSON file'
    )

    config_group.add_argument(
        '--import-config',
        type=str,
        metavar='FILE',
        help='Import configuration from JSON file'
    )


def load_saved_session_token() -> Optional[str]:
    """Load saved session token from file.

    Returns:
        Session token if found and valid, None otherwise.
    """
    try:
        if SESSION_TOKEN_FILE.exists():
            token = SESSION_TOKEN_FILE.read_text().strip()
            if token:
                logger.debug("Loaded saved session token")
                return token
    except Exception as e:
        logger.warning(f"Failed to load session token: {e}")
    return None


def save_session_token(token: str) -> bool:
    """Save session token to file for future use.

    Args:
        token: The session token to save.

    Returns:
        True if saved successfully, False otherwise.
    """
    try:
        SESSION_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSION_TOKEN_FILE.write_text(token)
        # Set restrictive permissions (owner read/write only)
        SESSION_TOKEN_FILE.chmod(0o600)
        logger.debug("Saved session token")
        return True
    except Exception as e:
        logger.warning(f"Failed to save session token: {e}")
        return False


def clear_saved_session_token() -> bool:
    """Clear saved session token file.

    Returns:
        True if cleared successfully or file didn't exist, False on error.
    """
    try:
        if SESSION_TOKEN_FILE.exists():
            SESSION_TOKEN_FILE.unlink()
            logger.info("Cleared saved session token")
        return True
    except Exception as e:
        logger.warning(f"Failed to clear session token: {e}")
        return False


def authenticate_cli(
    username: Optional[str] = None,
    password: Optional[str] = None,
    session_token: Optional[str] = None,
    prompt_for_password: bool = True
) -> CLIAuthResult:
    """Authenticate user for CLI session.

    Attempts authentication using provided credentials or session token.
    If username is provided without password and prompt_for_password is True,
    will prompt for password interactively.

    Args:
        username: Username for login.
        password: Password for login.
        session_token: Existing session token to validate.
        prompt_for_password: Whether to prompt for password if not provided.

    Returns:
        CLIAuthResult with authentication outcome.

    Example:
        result = authenticate_cli(username="alice", password="secret")
        if result.success:
            print(f"Logged in as {result.username}")
    """
    from ..database import get_db_manager
    from ..auth import UserService, AuthenticationError

    # Try session token first
    if session_token:
        try:
            db = get_db_manager()
            with db.get_connection() as conn:
                service = UserService(conn)
                user = service.validate_session(session_token)
                if user:
                    return CLIAuthResult(
                        success=True,
                        user_id=user.id,
                        username=user.username,
                        session_token=session_token
                    )
        except Exception as e:
            logger.debug(f"Session token validation failed: {e}")
            # Fall through to try username/password if provided

    # Try username/password
    if username:
        # Prompt for password if not provided
        if not password and prompt_for_password:
            try:
                password = getpass.getpass(f"Password for {username}: ")
            except (EOFError, KeyboardInterrupt):
                return CLIAuthResult(
                    success=False,
                    error_message="Password input cancelled"
                )

        if not password:
            return CLIAuthResult(
                success=False,
                error_message="Password required for authentication"
            )

        try:
            db = get_db_manager()
            with db.get_connection() as conn:
                service = UserService(conn)
                session = service.authenticate(
                    username=username,
                    password=password,
                    client_type='cli'
                )
                return CLIAuthResult(
                    success=True,
                    user_id=session.user_id,
                    username=username,
                    session_token=session.session_token
                )
        except AuthenticationError as e:
            return CLIAuthResult(
                success=False,
                error_message=str(e)
            )
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return CLIAuthResult(
                success=False,
                error_message=f"Authentication failed: {e}"
            )

    # No credentials provided
    return CLIAuthResult(
        success=False,
        error_message="No credentials provided"
    )


def setup_config_with_auth(args: argparse.Namespace) -> Tuple[bool, Optional[str]]:
    """Setup configuration with optional authentication from CLI args.

    Checks for authentication arguments and sets up user context if provided.
    Also handles config sync operations if requested.

    Args:
        args: Parsed command line arguments (must include auth arguments).

    Returns:
        Tuple of (success, error_message). If success is True, config is ready.
        If False, error_message explains what went wrong.

    Example:
        success, error = setup_config_with_auth(args)
        if not success:
            print(f"Error: {error}")
            sys.exit(1)
    """
    from ..config import get_config
    from ..database import get_db_manager

    config = get_config()

    # Handle logout request
    if getattr(args, 'logout', False):
        clear_saved_session_token()
        return True, None

    # Check for authentication
    username = getattr(args, 'user', None)
    password = getattr(args, 'password', None)
    session_token = getattr(args, 'session_token', None)
    save_session = getattr(args, 'save_session', False)

    # Try to load saved session if no credentials provided
    if not username and not session_token:
        session_token = load_saved_session_token()

    # If we have credentials, authenticate
    if username or session_token:
        result = authenticate_cli(
            username=username,
            password=password,
            session_token=session_token,
            prompt_for_password=True
        )

        if not result.success:
            return False, result.error_message

        # Set user context on config
        try:
            db = get_db_manager()
            conn = db.get_connection()
            config.set_user_context(
                user_id=result.user_id,
                connection=conn,
                session_token=result.session_token
            )
            logger.info(f"Authenticated as {result.username}")

            # Save session token if requested
            if save_session and result.session_token:
                save_session_token(result.session_token)

        except Exception as e:
            return False, f"Failed to setup user context: {e}"

    # Handle config sync operations
    sync_to_db = getattr(args, 'sync_to_db', False)
    sync_from_db = getattr(args, 'sync_from_db', False)
    export_config = getattr(args, 'export_config', None)
    import_config = getattr(args, 'import_config', None)

    if sync_to_db or sync_from_db:
        if not config.has_user_context():
            return False, "Config sync requires authentication (--user)"

    if sync_to_db:
        try:
            config.sync_to_database()
            print("Configuration synced to database")
        except Exception as e:
            return False, f"Failed to sync to database: {e}"

    if sync_from_db:
        try:
            config._sync_from_database()
            print("Configuration synced from database")
        except Exception as e:
            return False, f"Failed to sync from database: {e}"

    if export_config:
        try:
            config.export_to_json(Path(export_config))
            print(f"Configuration exported to: {export_config}")
        except Exception as e:
            return False, f"Failed to export config: {e}"

    if import_config:
        try:
            config.import_from_json(
                Path(import_config),
                sync_to_db=config.has_user_context()
            )
            print(f"Configuration imported from: {import_config}")
        except Exception as e:
            return False, f"Failed to import config: {e}"

    return True, None


def print_auth_status() -> None:
    """Print current authentication status."""
    from ..config import get_config

    config = get_config()

    if config.has_user_context():
        user_id = config.get_user_id()
        print(f"Authenticated: user_id={user_id}")
        print("Using: Database-backed settings")
    else:
        print("Not authenticated")
        print("Using: JSON file / default settings")

    # Check for saved session
    if SESSION_TOKEN_FILE.exists():
        print(f"Saved session: {SESSION_TOKEN_FILE}")
    else:
        print("Saved session: None")
