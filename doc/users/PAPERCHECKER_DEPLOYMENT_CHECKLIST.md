# PaperChecker Deployment Checklist

This checklist ensures PaperChecker is properly deployed and operational. Complete all items before considering the system production-ready.

## Pre-Deployment Requirements

### Environment Setup

- [ ] **PostgreSQL >=12** with pgvector extension installed
  ```bash
  psql -c "SELECT version();"
  psql -c "SELECT * FROM pg_extension WHERE extname = 'vector';"
  ```

- [ ] **Python >=3.12** available
  ```bash
  python --version
  ```

- [ ] **Ollama server running** with required models
  ```bash
  curl http://localhost:11434/api/tags
  ```

- [ ] **Required models downloaded**
  - [ ] `gpt-oss:20b` (or configured default model)
  - [ ] `nomic-embed-text` (for embeddings)
  ```bash
  ollama list
  ```

- [ ] **Database populated** with documents for searching
  ```bash
  psql -d knowledgebase -c "SELECT COUNT(*) FROM public.documents;"
  ```

- [ ] **Document embeddings generated**
  ```bash
  psql -d knowledgebase -c "SELECT COUNT(*) FROM public.document_embeddings;"
  ```

- [ ] **Sufficient disk space** for database and results

### Configuration

- [ ] **Config file created** at `~/.bmlibrarian/config.json`
  ```bash
  ls -la ~/.bmlibrarian/config.json
  ```

- [ ] **Database credentials configured** in environment or config
  ```bash
  # Verify environment variables
  echo $POSTGRES_DB $POSTGRES_USER $POSTGRES_HOST
  ```

- [ ] **Ollama URL configured** (default: `http://localhost:11434`)

- [ ] **PaperChecker agent parameters** tuned (optional)
  - `max_statements`: 2 (default)
  - `score_threshold`: 3.0 (default)
  - `search.semantic_limit`: 50 (default)
  - `search.hyde_limit`: 50 (default)

- [ ] **Logging configured** (optional)

### Database Schema

- [ ] **Schema migration applied**
  ```bash
  # Verify papercheck schema exists
  psql -d knowledgebase -c "\\dt papercheck.*"

  # Expected output: 8 tables (abstracts_checked, statements,
  # counter_statements, search_results, scored_documents,
  # citations, counter_reports, verdicts)
  ```

- [ ] **Views created**
  ```bash
  psql -d knowledgebase -c "\\dv papercheck.*"

  # Expected: v_complete_results, v_search_strategy_stats, v_verdict_distribution
  ```

- [ ] **Functions available**
  ```bash
  psql -d knowledgebase -c "\\df papercheck.*"

  # Expected: get_complete_result, cleanup_orphaned_search_results
  ```

## Testing Validation

### Unit Tests

- [ ] **All unit tests passing**
  ```bash
  uv run python -m pytest tests/paperchecker/ -v

  # Expected: 177+ tests passed
  ```

### Integration Tests

- [ ] **CLI processes sample abstract**
  ```bash
  uv run python paper_checker_cli.py examples/paperchecker/sample_abstract.json \
    -o /tmp/test_results.json --quick

  # Should complete without errors
  ```

- [ ] **Laboratory GUI launches**
  ```bash
  uv run python paper_checker_lab.py &
  sleep 5
  kill %1

  # Should launch without errors
  ```

- [ ] **Database writes verified**
  ```bash
  psql -d knowledgebase -c "SELECT COUNT(*) FROM papercheck.abstracts_checked;"
  ```

### Performance Validation

- [ ] **Run performance benchmark**
  ```bash
  uv run python examples/paperchecker/benchmark_performance.py
  ```

- [ ] **Performance targets met**
  - Short abstract (<100 words): < 90 seconds
  - Medium abstract (~250 words): < 180 seconds
  - Long abstract (~500 words): < 300 seconds

### Error Handling

- [ ] **Error scenarios handled correctly**
  ```bash
  uv run python examples/paperchecker/test_error_scenarios.py

  # All tests should pass
  ```

## Documentation Verification

- [ ] **User documentation exists**
  - `doc/users/paper_checker_guide.md`
  - `doc/users/paper_checker_cli_guide.md`
  - `doc/users/paper_checker_lab_guide.md`

- [ ] **Developer documentation exists**
  - `doc/developers/paper_checker_architecture.md`
  - `doc/developers/paper_checker_components.md`

- [ ] **Examples created**
  - `examples/paperchecker/sample_abstract.json`
  - `examples/paperchecker/diverse_test_abstracts.json`
  - `examples/paperchecker/README.md`

## Post-Deployment Verification

### Functional Verification

- [ ] **Process diverse test abstracts**
  ```bash
  uv run python paper_checker_cli.py examples/paperchecker/diverse_test_abstracts.json \
    -o results/diverse_results.json \
    --export-markdown results/reports/
  ```

- [ ] **Verify verdict distribution** is reasonable
  ```bash
  psql -d knowledgebase -c "SELECT * FROM papercheck.v_verdict_distribution;"
  ```

### Database Health

- [ ] **No orphaned records**
  ```bash
  psql -d knowledgebase -c "SELECT papercheck.cleanup_orphaned_search_results();"
  ```

- [ ] **Index health verified**
  ```bash
  psql -d knowledgebase -c "\\di papercheck.*"
  ```

## Monitoring Setup (Optional)

### Metrics to Track

- [ ] **Daily usage query available**
  ```sql
  SELECT DATE(checked_at) as date, COUNT(*) as abstracts_checked
  FROM papercheck.abstracts_checked
  WHERE checked_at >= NOW() - INTERVAL '7 days'
  GROUP BY DATE(checked_at)
  ORDER BY date DESC;
  ```

- [ ] **Error rate monitoring**
  ```sql
  SELECT
      SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
      SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
  FROM papercheck.abstracts_checked
  WHERE checked_at >= NOW() - INTERVAL '7 days';
  ```

- [ ] **Performance monitoring**
  ```sql
  SELECT AVG(processing_time_seconds) as avg_time,
         MIN(processing_time_seconds) as min_time,
         MAX(processing_time_seconds) as max_time
  FROM papercheck.abstracts_checked
  WHERE status = 'completed'
  AND checked_at >= NOW() - INTERVAL '7 days';
  ```

## Rollback Plan

If critical issues arise:

1. **Stop Processing**: Disable CLI/Lab access
2. **Diagnose**: Check logs and database for errors
3. **Fix or Rollback**: Apply hotfix or revert changes
4. **Verify**: Run test suite before resuming
5. **Resume**: Gradual rollout with monitoring

## Final Sign-Off

- [ ] All checklist items completed
- [ ] System tested with real data
- [ ] Documentation reviewed by team
- [ ] Rollback plan communicated
- [ ] Monitoring in place

**Deployment Date**: ________________

**Deployed By**: ________________

**Sign-Off**: ________________
