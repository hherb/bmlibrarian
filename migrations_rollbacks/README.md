# Migration Rollback Scripts

This directory contains rollback scripts for database migrations.

## Important Notes

- **These scripts are NOT auto-executed** - unlike files in `migrations/`, these scripts must be run manually
- Each rollback script corresponds to a migration file with the same number prefix
- Running a rollback script will **permanently delete** data created by the corresponding migration
- **Always backup data** before running rollback scripts in production

## Usage

To rollback a migration, execute the corresponding script manually:

```bash
psql -d knowledgebase -f migrations_rollbacks/011_rollback_paper_weight_schema.sql
```

## Rollback Scripts

| Script | Description |
|--------|-------------|
| `011_rollback_paper_weight_schema.sql` | Removes the `paper_weights` schema and all its objects |

## Safety Guidelines

1. **Test in development first** - Always test rollbacks in a non-production environment
2. **Backup before rollback** - Export any important data before running rollback scripts
3. **Verify dependencies** - Check if other schemas or applications depend on the schema being rolled back
4. **Document the reason** - Log why the rollback was necessary for future reference
