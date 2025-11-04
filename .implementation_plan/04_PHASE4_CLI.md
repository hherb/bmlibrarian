# Phase 4: CLI Integration

**Estimated Time**: 4-5 hours

## Objectives
1. Add multi-query search orchestration to QueryAgent
2. Update CLI query processing module
3. Add UI display functions for multi-query results
4. Maintain backward compatibility

## Files to Modify

### 1. src/bmlibrarian/agents/query_agent.py

**Add new method** (after convert_question_multi_model):

```python
def find_abstracts_multi_query(
    self,
    question: str,
    max_rows: int = 100,
    use_pubmed: bool = True,
    use_medrxiv: bool = True,
    use_others: bool = True,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    human_in_the_loop: bool = False,
    human_query_modifier: Optional[Callable[[List[str]], List[str]]] = None
) -> Generator[Dict, None, None]:
    """
    Find abstracts using multi-model query generation.

    Process (SERIAL):
    1. Generate multiple queries using different models
    2. If human_in_the_loop, show queries and allow selection/editing
    3. Execute each query SERIALLY to get document IDs
    4. De-duplicate IDs across all queries
    5. Fetch full documents for unique IDs
    6. Yield documents

    Args:
        question: Natural language question
        max_rows: Max results per query (total may be less after dedup)
        human_in_the_loop: Allow user to review/select queries
        human_query_modifier: Callback for query selection
        ... (other args same as find_abstracts)

    Yields:
        Document dictionaries (same format as find_abstracts)
    """
    from bmlibrarian.config import get_query_generation_config
    from bmlibrarian.database import find_abstract_ids, fetch_documents_by_ids
    from .query_generation.data_types import MultiModelQueryResult

    # Get config
    qg_config = get_query_generation_config()

    # Check if multi-model enabled
    if not qg_config.get('multi_model_enabled', False):
        # Fallback to original single-query behavior
        yield from self.find_abstracts(
            question=question,
            max_rows=max_rows,
            use_pubmed=use_pubmed,
            use_medrxiv=use_medrxiv,
            use_others=use_others,
            from_date=from_date,
            to_date=to_date,
            human_in_the_loop=human_in_the_loop,
            human_query_modifier=human_query_modifier
        )
        return

    # Step 1: Generate queries with multiple models
    self._call_callback("multi_query_generation_started", question)
    query_results = self.convert_question_multi_model(question)

    # Step 2: Human-in-the-loop query selection
    queries_to_execute = query_results.unique_queries

    if human_in_the_loop and human_query_modifier:
        try:
            self._call_callback("human_query_review_started", query_results)
            modified_queries = human_query_modifier(queries_to_execute)
            if modified_queries:
                queries_to_execute = modified_queries
            self._call_callback("queries_selected", queries_to_execute)
        except Exception as e:
            logger.warning(f"Human query modification failed: {e}")
            # Continue with original queries

    # Step 3: Execute queries SERIALLY and collect IDs
    self._call_callback("multi_query_execution_started", len(queries_to_execute))

    all_document_ids = set()
    rows_per_query = max_rows // len(queries_to_execute) if len(queries_to_execute) > 1 else max_rows

    for i, query in enumerate(queries_to_execute, 1):
        try:
            self._call_callback("query_executing", {"query": query, "index": i, "total": len(queries_to_execute)})

            # Execute query to get IDs only
            ids = find_abstract_ids(
                ts_query_str=query,
                max_rows=rows_per_query,
                use_pubmed=use_pubmed,
                use_medrxiv=use_medrxiv,
                use_others=use_others,
                plain=False,
                from_date=from_date,
                to_date=to_date
            )

            all_document_ids.update(ids)
            self._call_callback("query_executed", {"query": query, "ids_found": len(ids)})

        except Exception as e:
            logger.error(f"Query execution failed: {query} - {e}")
            self._call_callback("query_failed", {"query": query, "error": str(e)})
            # Continue with other queries

    # Step 4: Fetch full documents for unique IDs
    self._call_callback("fetching_documents", len(all_document_ids))

    if not all_document_ids:
        self._call_callback("no_documents_found", None)
        return

    documents = fetch_documents_by_ids(all_document_ids)

    self._call_callback("multi_query_search_completed", {
        "queries_executed": len(queries_to_execute),
        "unique_documents": len(documents)
    })

    # Step 5: Yield documents
    for doc in documents:
        yield doc
```

### 2. src/bmlibrarian/cli/query_processing.py

**Modify search_documents_with_review** (around line 26):

```python
def search_documents_with_review(self, question: str) -> List[Dict[str, Any]]:
    """Use QueryAgent to search documents with multi-model support."""
    from bmlibrarian.config import get_query_generation_config

    # Check if multi-model enabled
    qg_config = get_query_generation_config()
    multi_model_enabled = qg_config.get('multi_model_enabled', False)

    if multi_model_enabled and len(qg_config.get('models', [])) > 1:
        return self._search_with_multi_model(question)
    else:
        return self._search_with_single_model(question)

def _search_with_single_model(self, question: str) -> List[Dict[str, Any]]:
    """Original single-model search (current implementation)."""
    # Move existing search_documents_with_review code here
    # Lines 28-139 from current implementation
    pass

def _search_with_multi_model(self, question: str) -> List[Dict[str, Any]]:
    """New multi-model search orchestration."""
    self.ui.show_step_header(2, "Multi-Model Query Generation & Search")

    try:
        # Step 1: Display multi-model info
        qg_config = get_query_generation_config()
        models = qg_config['models']
        queries_per = qg_config['queries_per_model']

        self.ui.show_info_message(f"Using {len(models)} models for query generation:")
        for model in models:
            print(f"  • {model}")
        print(f"  • Generating {queries_per} query/queries per model")
        print()

        # Step 2: Generate queries with human-in-the-loop
        documents = []

        def query_review_callback(queries: List[str]) -> List[str]:
            """Allow user to review and select queries."""
            return self._review_and_select_queries(queries)

        # Execute multi-query search
        self.ui.show_progress_message("Generating queries with multiple models...")

        results_generator = self.query_agent.find_abstracts_multi_query(
            question=question,
            max_rows=self.config.max_search_results,
            human_in_the_loop=True,
            human_query_modifier=query_review_callback
        )

        self.ui.show_progress_message("Executing queries and collecting documents...")
        documents = list(results_generator)

        if not documents:
            self.ui.show_error_message("No documents found.")
            return []

        self.ui.show_success_message(f"Found {len(documents)} unique documents")
        return documents

    except Exception as e:
        self.ui.show_error_message(f"Multi-query search failed: {e}")
        return []

def _review_and_select_queries(self, queries: List[str]) -> List[str]:
    """Show generated queries and allow user selection."""
    # Display all queries
    self.ui.display_generated_queries(queries)

    # User options
    choice = self.ui.get_query_selection_choice(len(queries))

    if choice == 'all':
        return queries
    elif choice == 'select':
        return self.ui.select_specific_queries(queries)
    elif choice == 'edit':
        return self.ui.edit_queries(queries)
    else:
        return queries
```

### 3. src/bmlibrarian/cli/ui.py

**Add new display methods** (after existing methods):

```python
def display_generated_queries(self, queries: List[str]) -> None:
    """Display all generated queries."""
    print("\n" + "="*70)
    print("📋 Generated Queries from Multiple Models")
    print("="*70)

    for i, query in enumerate(queries, 1):
        print(f"\n[Query {i}]")
        print(f"  {query}")
    print()

def get_query_selection_choice(self, num_queries: int) -> str:
    """Get user's choice for query selection."""
    print("\n" + "="*70)
    print("🎯 Query Selection")
    print("="*70)
    print("\nOptions:")
    print("1. Execute all queries")
    print("2. Select specific queries")
    print("3. Edit queries before execution")
    print("4. Back to question entry")

    choice = input("\nChoose option (1-4): ").strip()

    choice_map = {
        '1': 'all',
        '2': 'select',
        '3': 'edit',
        '4': 'back'
    }

    return choice_map.get(choice, 'all')

def select_specific_queries(self, queries: List[str]) -> List[str]:
    """Let user select which queries to execute."""
    print("\nSelect queries to execute (e.g., '1 3' or '1,2,3'):")
    selection = input("Query numbers: ").strip()

    # Parse selection
    try:
        if ',' in selection:
            indices = [int(x.strip()) - 1 for x in selection.split(',')]
        else:
            indices = [int(x.strip()) - 1 for x in selection.split()]

        selected = [queries[i] for i in indices if 0 <= i < len(queries)]

        if not selected:
            self.show_warning_message("No valid queries selected, using all")
            return queries

        return selected

    except (ValueError, IndexError):
        self.show_warning_message("Invalid selection, using all queries")
        return queries

def edit_queries(self, queries: List[str]) -> List[str]:
    """Allow user to edit queries."""
    edited = []

    for i, query in enumerate(queries, 1):
        print(f"\n[Query {i}] Current: {query}")
        choice = input("Keep (k), Edit (e), or Skip (s)? [k/e/s]: ").strip().lower()

        if choice == 'e':
            new_query = input("Enter new query: ").strip()
            if new_query:
                edited.append(new_query)
            else:
                edited.append(query)
        elif choice == 's':
            continue
        else:  # 'k' or default
            edited.append(query)

    return edited if edited else queries
```

## Testing Phase 4

### Integration Test
```bash
uv run python bmlibrarian_cli.py --quick
# Enable multi-model in config first
# Test with real question
# Verify all UI flows work
```

### Test Cases
1. Single model (backward compatible)
2. Multi-model with all queries
3. Multi-model with query selection
4. Multi-model with query editing
5. Error handling (model unavailable)

## Completion Criteria
- [x] find_abstracts_multi_query() implemented
- [x] CLI integration complete
- [x] UI functions added
- [x] Backward compatibility verified
- [x] Manual testing passes

## Next Step
Update `00_OVERVIEW.md`, read `05_PHASE5_TESTS.md`.

## Key Implementation Notes
- **Serial execution**: Simple for-loops, no threads
- **Human-in-the-loop**: Show all queries, allow selection/editing
- **Backward compatible**: Falls back to single-model if disabled
- **Error handling**: Continue if one query fails
