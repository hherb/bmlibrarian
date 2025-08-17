# User Documentation

Welcome to BMLibrarian user documentation! This section contains all the information you need to install, configure, and use BMLibrarian effectively.

## Getting Started

Start here if you're new to BMLibrarian:

📖 **[Getting Started Guide](getting_started.md)**
- Installation instructions
- Prerequisites and setup
- Basic configuration
- Quick start examples

## Core Features

### Migration System

🗄️ **[Migration System Guide](migration_system.md)**
- Understanding the migration system
- Creating and managing migrations
- Best practices and safety guidelines
- Advanced migration patterns

### Command Line Interface

⚡ **[CLI Reference](cli_reference.md)**
- Complete command reference
- Usage examples
- Configuration options
- Environment variables

## Support

### Troubleshooting

🔧 **[Troubleshooting Guide](troubleshooting.md)**
- Common issues and solutions
- Error message explanations
- Debug and recovery procedures
- Performance optimization

## Quick Reference

### Installation
```bash
pip install bmlibrarian
```

### Basic Commands
```bash
# Initialize database
bmlibrarian migrate init --host localhost --user username --password password --database dbname

# Apply migrations
bmlibrarian migrate apply --host localhost --user username --password password --database dbname
```

### Environment Variables
```bash
export POSTGRES_USER=username
export POSTGRES_PASSWORD=password
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=bmlibrarian_dev
```

## Need More Help?

- **Technical Issues**: Check the [Troubleshooting Guide](troubleshooting.md)
- **Feature Requests**: See the developer documentation
- **API Usage**: Refer to the [API Reference](../developers/api_reference.md)

---

Choose a topic above to get started, or begin with the [Getting Started Guide](getting_started.md) if you're new to BMLibrarian.