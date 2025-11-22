#!/usr/bin/env python3
"""Migration tool for BMLibrarian configuration.

Migrates JSON configuration files to database-backed user settings.

Usage:
    # Migrate personal config to user settings
    uv run python migrate_config_to_db.py --user <username> --config ~/.bmlibrarian/config.json

    # Migrate to default settings (admin)
    uv run python migrate_config_to_db.py --defaults --config /path/to/config.json

    # Interactive mode
    uv run python migrate_config_to_db.py --interactive

    # Export from database to JSON
    uv run python migrate_config_to_db.py --export --user <username> --output settings_backup.json
"""

import argparse
import json
import logging
import sys
from getpass import getpass
from pathlib import Path
from typing import Optional, Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Valid settings categories that can be migrated
VALID_CATEGORIES = frozenset([
    'models', 'ollama', 'agents', 'database', 'search',
    'query_generation', 'gui', 'openathens', 'pdf', 'general'
])


def get_db_connection():
    """Get database connection from environment.

    Returns:
        psycopg connection object.

    Raises:
        Exception: If connection fails.
    """
    import os
    import psycopg

    # Load from environment
    host = os.environ.get('POSTGRES_HOST', 'localhost')
    port = os.environ.get('POSTGRES_PORT', '5432')
    database = os.environ.get('POSTGRES_DB', 'knowledgebase')
    user = os.environ.get('POSTGRES_USER', '')
    password = os.environ.get('POSTGRES_PASSWORD', '')

    if not user:
        raise ValueError(
            "Database credentials not configured. "
            "Set POSTGRES_USER and POSTGRES_PASSWORD environment variables."
        )

    conn_string = (
        f"host={host} port={port} dbname={database} "
        f"user={user} password={password}"
    )

    return psycopg.connect(conn_string)


def load_json_config(config_path: Path) -> Dict[str, Any]:
    """Load configuration from JSON file.

    Args:
        config_path: Path to JSON configuration file.

    Returns:
        Configuration dictionary.

    Raises:
        FileNotFoundError: If file doesn't exist.
        json.JSONDecodeError: If file contains invalid JSON.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, 'r') as f:
        return json.load(f)


def filter_valid_categories(config: Dict[str, Any]) -> Dict[str, Any]:
    """Filter config to only include valid categories.

    Args:
        config: Full configuration dictionary.

    Returns:
        Filtered dictionary with only valid categories.
    """
    filtered = {}
    for category in VALID_CATEGORIES:
        if category in config:
            filtered[category] = config[category]
    return filtered


def migrate_to_user_settings(
    username: str,
    password: str,
    config: Dict[str, Any],
    merge: bool = True
) -> bool:
    """Migrate JSON config to user's database settings.

    Args:
        username: Username to migrate settings for.
        password: User's password for authentication.
        config: Configuration dictionary to migrate.
        merge: If True, merge with existing settings; if False, replace.

    Returns:
        True if migration succeeded.
    """
    from bmlibrarian.auth import UserService, UserSettingsManager

    logger.info(f"Connecting to database...")
    conn = get_db_connection()

    try:
        # Authenticate user
        logger.info(f"Authenticating user: {username}")
        user_service = UserService(conn)
        user, _ = user_service.authenticate(username, password)

        # Create settings manager
        settings_manager = UserSettingsManager(conn, user.id)

        # Filter to valid categories
        valid_config = filter_valid_categories(config)

        # Migrate each category
        migrated_count = 0
        for category, settings in valid_config.items():
            if not isinstance(settings, dict):
                logger.warning(f"Skipping {category}: not a dictionary")
                continue

            if merge:
                # Get existing settings and merge
                existing = settings_manager.get(category) or {}
                merged = {**existing, **settings}
                settings_manager.set(category, merged)
            else:
                settings_manager.set(category, settings)

            logger.info(f"  Migrated category: {category} ({len(settings)} settings)")
            migrated_count += 1

        logger.info(f"Successfully migrated {migrated_count} categories for user {username}")
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False
    finally:
        conn.close()


def migrate_to_defaults(config: Dict[str, Any], merge: bool = True) -> bool:
    """Migrate JSON config to default database settings.

    Args:
        config: Configuration dictionary to migrate.
        merge: If True, merge with existing defaults; if False, replace.

    Returns:
        True if migration succeeded.
    """
    logger.info("Connecting to database...")
    conn = get_db_connection()

    try:
        valid_config = filter_valid_categories(config)

        with conn.cursor() as cur:
            for category, settings in valid_config.items():
                if not isinstance(settings, dict):
                    logger.warning(f"Skipping {category}: not a dictionary")
                    continue

                settings_json = json.dumps(settings)

                if merge:
                    # Get existing and merge
                    cur.execute(
                        """
                        SELECT settings FROM bmlsettings.default_settings
                        WHERE category = %s
                        """,
                        (category,)
                    )
                    row = cur.fetchone()
                    if row:
                        existing = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                        merged = {**existing, **settings}
                        settings_json = json.dumps(merged)

                # Upsert
                cur.execute(
                    """
                    INSERT INTO bmlsettings.default_settings (category, settings)
                    VALUES (%s, %s::jsonb)
                    ON CONFLICT (category)
                    DO UPDATE SET settings = EXCLUDED.settings, updated_at = NOW()
                    """,
                    (category, settings_json)
                )
                logger.info(f"  Migrated default category: {category}")

        conn.commit()
        logger.info("Successfully migrated default settings")
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def export_user_settings(username: str, password: str, output_path: Path) -> bool:
    """Export user's database settings to JSON file.

    Args:
        username: Username to export settings for.
        password: User's password for authentication.
        output_path: Path to output JSON file.

    Returns:
        True if export succeeded.
    """
    from bmlibrarian.auth import UserService, UserSettingsManager

    logger.info("Connecting to database...")
    conn = get_db_connection()

    try:
        # Authenticate user
        logger.info(f"Authenticating user: {username}")
        user_service = UserService(conn)
        user, _ = user_service.authenticate(username, password)

        # Create settings manager
        settings_manager = UserSettingsManager(conn, user.id)

        # Export all categories
        config = {}
        for category in VALID_CATEGORIES:
            settings = settings_manager.get(category)
            if settings:
                config[category] = settings

        # Write to file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(config, f, indent=2)

        logger.info(f"Exported settings to: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Export failed: {e}")
        return False
    finally:
        conn.close()


def export_default_settings(output_path: Path) -> bool:
    """Export default database settings to JSON file.

    Args:
        output_path: Path to output JSON file.

    Returns:
        True if export succeeded.
    """
    logger.info("Connecting to database...")
    conn = get_db_connection()

    try:
        config = {}

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT category, settings
                FROM bmlsettings.default_settings
                """
            )
            for row in cur:
                category = row[0]
                settings = row[1] if isinstance(row[1], dict) else json.loads(row[1])
                config[category] = settings

        # Write to file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(config, f, indent=2)

        logger.info(f"Exported default settings to: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Export failed: {e}")
        return False
    finally:
        conn.close()


def interactive_mode() -> None:
    """Run interactive migration wizard."""
    print("\n" + "=" * 60)
    print("BMLibrarian Settings Migration Tool")
    print("=" * 60)

    print("\nOptions:")
    print("  1. Migrate JSON config to user settings")
    print("  2. Migrate JSON config to default settings (admin)")
    print("  3. Export user settings to JSON")
    print("  4. Export default settings to JSON")
    print("  5. Exit")

    choice = input("\nSelect option (1-5): ").strip()

    if choice == '1':
        # Migrate to user settings
        username = input("Username: ").strip()
        password = getpass("Password: ")
        config_path = input("Config file path [~/.bmlibrarian/config.json]: ").strip()
        if not config_path:
            config_path = str(Path.home() / ".bmlibrarian" / "config.json")

        merge = input("Merge with existing settings? [Y/n]: ").strip().lower() != 'n'

        try:
            config = load_json_config(Path(config_path))
            if migrate_to_user_settings(username, password, config, merge):
                print("\nMigration successful!")
            else:
                print("\nMigration failed. Check the logs above.")
        except Exception as e:
            print(f"\nError: {e}")

    elif choice == '2':
        # Migrate to defaults
        config_path = input("Config file path: ").strip()
        merge = input("Merge with existing defaults? [Y/n]: ").strip().lower() != 'n'

        try:
            config = load_json_config(Path(config_path))
            if migrate_to_defaults(config, merge):
                print("\nMigration successful!")
            else:
                print("\nMigration failed. Check the logs above.")
        except Exception as e:
            print(f"\nError: {e}")

    elif choice == '3':
        # Export user settings
        username = input("Username: ").strip()
        password = getpass("Password: ")
        output_path = input("Output file path [./user_settings_backup.json]: ").strip()
        if not output_path:
            output_path = "./user_settings_backup.json"

        if export_user_settings(username, password, Path(output_path)):
            print(f"\nExported to: {output_path}")
        else:
            print("\nExport failed. Check the logs above.")

    elif choice == '4':
        # Export default settings
        output_path = input("Output file path [./default_settings_backup.json]: ").strip()
        if not output_path:
            output_path = "./default_settings_backup.json"

        if export_default_settings(Path(output_path)):
            print(f"\nExported to: {output_path}")
        else:
            print("\nExport failed. Check the logs above.")

    elif choice == '5':
        print("\nGoodbye!")
        sys.exit(0)
    else:
        print("\nInvalid option. Please try again.")
        interactive_mode()


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    parser = argparse.ArgumentParser(
        description='Migrate BMLibrarian configuration to database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--user', '-u',
        help='Username to migrate settings for'
    )
    mode_group.add_argument(
        '--defaults',
        action='store_true',
        help='Migrate to default settings (admin operation)'
    )
    mode_group.add_argument(
        '--interactive', '-i',
        action='store_true',
        help='Run in interactive mode'
    )

    # Export mode
    parser.add_argument(
        '--export',
        action='store_true',
        help='Export settings from database to JSON instead of importing'
    )

    # Input/output
    parser.add_argument(
        '--config', '-c',
        type=Path,
        help='Path to JSON configuration file to import'
    )
    parser.add_argument(
        '--output', '-o',
        type=Path,
        default=Path('./settings_export.json'),
        help='Path to output JSON file (for export mode)'
    )

    # Merge behavior
    parser.add_argument(
        '--replace',
        action='store_true',
        help='Replace existing settings instead of merging'
    )

    # Password
    parser.add_argument(
        '--password', '-p',
        help='Password (will prompt if not provided)'
    )

    # Verbosity
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Interactive mode
    if args.interactive:
        interactive_mode()
        return 0

    # Validate arguments
    if args.export:
        # Export mode
        if args.user:
            password = args.password or getpass("Password: ")
            success = export_user_settings(args.user, password, args.output)
        elif args.defaults:
            success = export_default_settings(args.output)
        else:
            parser.error("--export requires --user or --defaults")
            return 1
    else:
        # Import mode
        if not args.config:
            if not args.user and not args.defaults:
                # No mode specified, run interactive
                interactive_mode()
                return 0
            parser.error("--config is required for import mode")
            return 1

        try:
            config = load_json_config(args.config)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return 1

        merge = not args.replace

        if args.user:
            password = args.password or getpass("Password: ")
            success = migrate_to_user_settings(args.user, password, config, merge)
        elif args.defaults:
            success = migrate_to_defaults(config, merge)
        else:
            parser.error("--user or --defaults is required")
            return 1

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
