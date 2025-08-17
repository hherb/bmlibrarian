"""Unit tests for the CLI module."""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bmlibrarian.cli import create_parser, main


class TestCreateParser:
    """Test cases for create_parser function."""

    def test_create_parser_basic(self):
        """Test basic parser creation."""
        parser = create_parser()
        
        assert parser.prog == "bmlibrarian"
        assert parser.description == "Biomedical Literature Librarian CLI"

    def test_create_parser_migrate_subcommand(self):
        """Test migrate subcommand parsing."""
        parser = create_parser()
        
        # Test migrate help
        with pytest.raises(SystemExit):
            parser.parse_args(["migrate", "--help"])

    def test_create_parser_init_subcommand(self):
        """Test init subcommand arguments."""
        parser = create_parser()
        
        args = parser.parse_args([
            "migrate", "init",
            "--host", "localhost",
            "--user", "testuser", 
            "--password", "testpass",
            "--database", "testdb"
        ])
        
        assert args.command == "migrate"
        assert args.migrate_action == "init"
        assert args.host == "localhost"
        assert args.port == "5432"  # default
        assert args.user == "testuser"
        assert args.password == "testpass"
        assert args.database == "testdb"
        assert args.baseline_schema is None

    def test_create_parser_init_with_custom_port(self):
        """Test init subcommand with custom port."""
        parser = create_parser()
        
        args = parser.parse_args([
            "migrate", "init",
            "--host", "localhost",
            "--port", "5433",
            "--user", "testuser",
            "--password", "testpass", 
            "--database", "testdb"
        ])
        
        assert args.port == "5433"

    def test_create_parser_init_with_baseline_schema(self):
        """Test init subcommand with baseline schema."""
        parser = create_parser()
        
        args = parser.parse_args([
            "migrate", "init",
            "--host", "localhost",
            "--user", "testuser",
            "--password", "testpass",
            "--database", "testdb",
            "--baseline-schema", "/path/to/schema.sql"
        ])
        
        assert args.baseline_schema == "/path/to/schema.sql"

    def test_create_parser_apply_subcommand(self):
        """Test apply subcommand arguments."""
        parser = create_parser()
        
        args = parser.parse_args([
            "migrate", "apply",
            "--host", "localhost",
            "--user", "testuser",
            "--password", "testpass",
            "--database", "testdb"
        ])
        
        assert args.command == "migrate"
        assert args.migrate_action == "apply"
        assert args.host == "localhost"
        assert args.user == "testuser"
        assert args.password == "testpass"
        assert args.database == "testdb"
        assert args.migrations_dir is None

    def test_create_parser_apply_with_migrations_dir(self):
        """Test apply subcommand with custom migrations directory."""
        parser = create_parser()
        
        args = parser.parse_args([
            "migrate", "apply",
            "--host", "localhost",
            "--user", "testuser",
            "--password", "testpass",
            "--database", "testdb",
            "--migrations-dir", "/custom/migrations"
        ])
        
        assert args.migrations_dir == "/custom/migrations"

    def test_create_parser_missing_required_args(self):
        """Test parser with missing required arguments."""
        parser = create_parser()
        
        # Missing --host should cause error
        with pytest.raises(SystemExit):
            parser.parse_args([
                "migrate", "init",
                "--user", "testuser",
                "--password", "testpass",
                "--database", "testdb"
            ])


class TestMain:
    """Test cases for main function."""

    @patch('bmlibrarian.cli.create_parser')
    def test_main_no_command(self, mock_create_parser):
        """Test main with no command specified."""
        mock_parser = MagicMock()
        mock_args = MagicMock()
        mock_args.command = None
        mock_parser.parse_args.return_value = mock_args
        mock_create_parser.return_value = mock_parser
        
        with patch('sys.exit') as mock_exit:
            main()
        
        mock_parser.print_help.assert_called_once()
        mock_exit.assert_called_once_with(1)

    @patch('bmlibrarian.cli.create_parser')
    def test_main_migrate_no_action(self, mock_create_parser):
        """Test main with migrate command but no action."""
        mock_parser = MagicMock()
        mock_args = MagicMock()
        mock_args.command = "migrate"
        mock_args.migrate_action = None
        mock_parser.parse_args.return_value = mock_args
        mock_create_parser.return_value = mock_parser
        
        with patch('sys.exit') as mock_exit:
            main()
        
        mock_parser.print_help.assert_called_once()
        mock_exit.assert_called_once_with(1)

    @patch('bmlibrarian.cli.MigrationManager')
    @patch('bmlibrarian.cli.create_parser')
    def test_main_migrate_init_success(self, mock_create_parser, mock_migration_manager):
        """Test main with successful migrate init command."""
        # Setup parser mock
        mock_parser = MagicMock()
        mock_args = MagicMock()
        mock_args.command = "migrate"
        mock_args.migrate_action = "init"
        mock_args.host = "localhost"
        mock_args.port = "5432"
        mock_args.user = "testuser"
        mock_args.password = "testpass"
        mock_args.database = "testdb"
        mock_args.baseline_schema = None
        mock_parser.parse_args.return_value = mock_args
        mock_create_parser.return_value = mock_parser
        
        # Setup migration manager mock
        mock_manager_instance = MagicMock()
        mock_migration_manager.return_value = mock_manager_instance
        
        # Create temporary baseline schema file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
            f.write("CREATE TABLE test (id INT);")
            baseline_path = Path(f.name)
        
        try:
            with patch('pathlib.Path') as mock_path_cls:
                # Mock the path resolution for baseline schema
                mock_path_instance = MagicMock()
                mock_path_instance.exists.return_value = True
                mock_path_cls.return_value = mock_path_instance
                
                # Mock __file__ path resolution  
                with patch('bmlibrarian.cli.Path') as mock_path:
                    mock_file_path = MagicMock()
                    mock_file_path.parent.parent.parent.parent = Path("/fake/project/root")
                    mock_path.return_value = mock_file_path
                    
                    # Make the baseline schema path exist
                    baseline_mock = MagicMock()
                    baseline_mock.exists.return_value = True
                    mock_path.return_value = baseline_mock
                    
                    with patch('builtins.print') as mock_print:
                        main()
            
            # Verify MigrationManager was created with correct params
            mock_migration_manager.assert_called_once_with(
                host="localhost",
                port="5432",
                user="testuser",
                password="testpass",
                database="testdb"
            )
            
            # Verify initialize_database was called
            mock_manager_instance.initialize_database.assert_called_once()
            mock_print.assert_called_with("Database initialized successfully!")
        
        finally:
            baseline_path.unlink()

    @patch('bmlibrarian.cli.create_parser')
    def test_main_migrate_init_missing_baseline_schema(self, mock_create_parser):
        """Test main with migrate init when baseline schema is missing."""
        mock_parser = MagicMock()
        mock_args = MagicMock()
        mock_args.command = "migrate"
        mock_args.migrate_action = "init"
        mock_args.host = "localhost"
        mock_args.port = "5432"
        mock_args.user = "testuser"
        mock_args.password = "testpass"
        mock_args.database = "testdb"
        mock_args.baseline_schema = "/non/existent/baseline.sql"  # Provide explicit path that doesn't exist
        mock_parser.parse_args.return_value = mock_args
        mock_create_parser.return_value = mock_parser
        
        with patch('bmlibrarian.cli.MigrationManager') as mock_migration_manager:
            mock_manager_instance = MagicMock()
            mock_manager_instance.initialize_database.side_effect = FileNotFoundError("Baseline schema file not found: /non/existent/baseline.sql")
            mock_migration_manager.return_value = mock_manager_instance
            
            with pytest.raises(FileNotFoundError):
                main()

    @patch('bmlibrarian.cli.MigrationManager')
    @patch('bmlibrarian.cli.create_parser')
    def test_main_migrate_apply_success(self, mock_create_parser, mock_migration_manager):
        """Test main with successful migrate apply command."""
        mock_parser = MagicMock()
        mock_args = MagicMock()
        mock_args.command = "migrate"
        mock_args.migrate_action = "apply"
        mock_args.host = "localhost"
        mock_args.port = "5432"
        mock_args.user = "testuser"
        mock_args.password = "testpass"
        mock_args.database = "testdb"
        mock_args.migrations_dir = None
        mock_parser.parse_args.return_value = mock_args
        mock_create_parser.return_value = mock_parser
        
        mock_manager_instance = MagicMock()
        mock_manager_instance.apply_pending_migrations.return_value = 2
        mock_migration_manager.return_value = mock_manager_instance
        
        with patch('bmlibrarian.cli.Path') as mock_path:
            expected_path = Path.home() / ".bmlibrarian" / "migrations"
            mock_path.home.return_value = Path.home()
            
            with patch('builtins.print') as mock_print:
                main()
        
        mock_migration_manager.assert_called_once_with(
            host="localhost",
            port="5432", 
            user="testuser",
            password="testpass",
            database="testdb"
        )
        
        mock_manager_instance.apply_pending_migrations.assert_called_once()
        mock_print.assert_called_with("Applied 2 migration(s) successfully!")

    @patch('bmlibrarian.cli.MigrationManager')
    @patch('bmlibrarian.cli.create_parser')
    def test_main_migrate_apply_no_migrations(self, mock_create_parser, mock_migration_manager):
        """Test main with migrate apply when no migrations to apply."""
        mock_parser = MagicMock()
        mock_args = MagicMock()
        mock_args.command = "migrate"
        mock_args.migrate_action = "apply"
        mock_args.host = "localhost"
        mock_args.port = "5432"
        mock_args.user = "testuser"
        mock_args.password = "testpass"
        mock_args.database = "testdb"
        mock_args.migrations_dir = None
        mock_parser.parse_args.return_value = mock_args
        mock_create_parser.return_value = mock_parser
        
        mock_manager_instance = MagicMock()
        mock_manager_instance.apply_pending_migrations.return_value = 0
        mock_migration_manager.return_value = mock_manager_instance
        
        with patch('builtins.print') as mock_print:
            main()
        
        mock_print.assert_called_with("No pending migrations to apply.")

    @patch('bmlibrarian.cli.MigrationManager')
    @patch('bmlibrarian.cli.create_parser')
    def test_main_migrate_apply_custom_migrations_dir(self, mock_create_parser, mock_migration_manager):
        """Test main with migrate apply using custom migrations directory."""
        mock_parser = MagicMock()
        mock_args = MagicMock()
        mock_args.command = "migrate"
        mock_args.migrate_action = "apply"
        mock_args.host = "localhost"
        mock_args.port = "5432"
        mock_args.user = "testuser"
        mock_args.password = "testpass"
        mock_args.database = "testdb"
        mock_args.migrations_dir = "/custom/migrations"
        mock_parser.parse_args.return_value = mock_args
        mock_create_parser.return_value = mock_parser
        
        mock_manager_instance = MagicMock()
        mock_manager_instance.apply_pending_migrations.return_value = 1
        mock_migration_manager.return_value = mock_manager_instance
        
        with patch('builtins.print') as mock_print:
            main()
        
        # Should use custom migrations directory
        mock_manager_instance.apply_pending_migrations.assert_called_once_with("/custom/migrations")

    @patch('sys.argv', ['bmlibrarian'])
    @patch('bmlibrarian.cli.create_parser')
    def test_main_integration(self, mock_create_parser):
        """Test main function integration with actual argument parsing."""
        mock_parser = MagicMock()
        mock_args = MagicMock()
        mock_args.command = None
        mock_parser.parse_args.return_value = mock_args
        mock_create_parser.return_value = mock_parser
        
        with patch('sys.exit') as mock_exit:
            main()
        
        mock_create_parser.assert_called_once()
        mock_parser.parse_args.assert_called_once()
        mock_exit.assert_called_once_with(1)