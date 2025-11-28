#!/usr/bin/env python3
"""
Model Benchmark CLI - Benchmark document scoring models

Command-line interface for benchmarking document scoring models against
an authoritative model to evaluate accuracy and performance.

Usage:
    # Basic benchmark with default authoritative model (gpt-oss:120B)
    python model_benchmark_cli.py "What are the cardiovascular benefits of exercise?" \
        --models gpt-oss:20b medgemma4B_it_q8:latest

    # Custom authoritative model
    python model_benchmark_cli.py "CRISPR gene editing mechanisms" \
        --models gpt-oss:20b qwen2.5:32b \
        --authoritative gpt-oss:120B

    # Limit documents and export results
    python model_benchmark_cli.py "COVID-19 vaccine efficacy" \
        --models gpt-oss:20b medgemma4B_it_q8:latest \
        --max-docs 20 \
        --output results.json

    # View previous benchmark results
    python model_benchmark_cli.py history

    # View specific benchmark run
    python model_benchmark_cli.py show --run-id 5
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import psycopg
from dotenv import load_dotenv

from src.bmlibrarian.benchmarking import (
    BenchmarkRunner,
    BenchmarkDatabase,
    BenchmarkSummary,
    SEMANTIC_THRESHOLD,
    BEST_REASONING_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    DEFAULT_OLLAMA_HOST,
)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def get_db_connection() -> psycopg.Connection:
    """
    Get database connection from environment.

    Returns:
        Active database connection

    Raises:
        SystemExit: If connection fails
    """
    # Load environment variables
    user_env_path = Path.home() / ".bmlibrarian" / ".env"
    if user_env_path.exists():
        load_dotenv(user_env_path)
    else:
        load_dotenv()

    db_params = {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "5432"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
        "dbname": os.getenv("POSTGRES_DB", "knowledgebase"),
    }

    if not db_params["user"] or not db_params["password"]:
        print("\n✗ Error: Missing POSTGRES_USER or POSTGRES_PASSWORD in environment")
        sys.exit(1)

    try:
        return psycopg.connect(**db_params)
    except Exception as e:
        print(f"\n✗ Error connecting to database: {e}")
        sys.exit(1)


def progress_callback(status: str, current: int, total: int) -> None:
    """Progress callback for benchmark runner."""
    if total > 0:
        pct = (current / total) * 100
        print(f"\r  {status}: {current}/{total} ({pct:.1f}%)", end="", flush=True)
        if current >= total:
            print()  # Newline when complete
    else:
        print(f"  {status}")


def cmd_benchmark(args: argparse.Namespace) -> int:
    """Execute a benchmark run."""
    print("=" * 70)
    print("MODEL BENCHMARKING")
    print("=" * 70)
    print()
    print(f"Question: {args.question}")
    print(f"Models to evaluate: {', '.join(args.models)}")
    print(f"Authoritative model: {args.authoritative}")
    print(f"Semantic threshold: {args.threshold}")
    if args.max_docs:
        print(f"Max documents: {args.max_docs}")
    print()

    conn = get_db_connection()

    try:
        runner = BenchmarkRunner(
            conn=conn,
            ollama_host=args.ollama_host,
            temperature=args.temperature,
            top_p=args.top_p,
            authoritative_model=args.authoritative,
            semantic_threshold=args.threshold,
            progress_callback=progress_callback
        )

        # Run benchmark
        result = runner.run_benchmark(
            question_text=args.question,
            models=args.models,
            max_documents=args.max_docs,
            created_by=args.user
        )

        # Print summary
        print()
        print(runner.print_summary(result))

        # Export results if requested
        if args.output:
            output_path = Path(args.output)
            runner.export_results_json(result, output_path)
            print(f"\n✓ Results exported to {output_path}")

        return 0

    except KeyboardInterrupt:
        print("\n\n⚠ Benchmark interrupted by user")
        return 130

    except Exception as e:
        print(f"\n✗ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

    finally:
        conn.close()


def cmd_history(args: argparse.Namespace) -> int:
    """Show benchmark history."""
    print("=" * 70)
    print("BENCHMARK HISTORY")
    print("=" * 70)
    print()

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT br.run_id, rq.question_text, br.started_at,
                       br.completed_at, br.status, br.total_documents,
                       array_length(br.models_evaluated, 1) as num_models,
                       br.authoritative_model
                FROM benchmarking.benchmark_runs br
                JOIN benchmarking.research_questions rq ON br.question_id = rq.question_id
                ORDER BY br.started_at DESC
                LIMIT %s
            """, (args.limit,))

            rows = cur.fetchall()

            if not rows:
                print("No benchmark runs found.")
                return 0

            print(f"{'ID':>5}  {'Status':>10}  {'Docs':>5}  {'Models':>6}  {'Started':>20}  Question")
            print("-" * 70)

            for row in rows:
                run_id, question, started, completed, status, docs, num_models, auth_model = row
                started_str = started.strftime("%Y-%m-%d %H:%M") if started else "N/A"
                question_short = question[:35] + "..." if len(question) > 35 else question
                print(f"{run_id:>5}  {status:>10}  {docs or 0:>5}  {num_models or 0:>6}  {started_str:>20}  {question_short}")

        return 0

    except Exception as e:
        print(f"\n✗ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

    finally:
        conn.close()


def cmd_show(args: argparse.Namespace) -> int:
    """Show details for a specific benchmark run."""
    print("=" * 70)
    print(f"BENCHMARK RUN #{args.run_id}")
    print("=" * 70)
    print()

    conn = get_db_connection()

    try:
        db = BenchmarkDatabase(conn)

        # Get run details
        run = db.get_benchmark_run(args.run_id)
        if not run:
            print(f"✗ Benchmark run #{args.run_id} not found")
            return 1

        print(f"Question: {run['question_text']}")
        print(f"Status: {run['status']}")
        print(f"Started: {run['started_at']}")
        print(f"Completed: {run['completed_at'] or 'N/A'}")
        print(f"Documents: {run['total_documents']}")
        print(f"Models evaluated: {', '.join(run['models_evaluated'] or [])}")
        print(f"Authoritative model: {run['authoritative_model']}")
        print()

        # Get ranked results
        results = db.get_ranked_results(args.run_id)

        if results:
            print("-" * 70)
            print("RANKINGS")
            print("-" * 70)
            print()
            print(f"{'Rank':>4}  {'Model':>30}  {'MAE':>6}  {'Exact%':>7}  {'Within1%':>8}  {'Avg ms':>8}")
            print("-" * 70)

            for r in results:
                rank = r["final_rank"] or "N/A"
                model = r["model_name"][:30]
                mae = f"{r['mean_absolute_error']:.3f}" if r["mean_absolute_error"] else "N/A"
                exact = f"{r['exact_match_rate']:.1f}" if r["exact_match_rate"] else "N/A"
                within = f"{r['within_one_rate']:.1f}" if r["within_one_rate"] else "N/A"
                avg_ms = f"{r['avg_scoring_time_ms']:.1f}" if r["avg_scoring_time_ms"] else "N/A"

                print(f"{rank:>4}  {model:>30}  {mae:>6}  {exact:>7}  {within:>8}  {avg_ms:>8}")

        # Export if requested
        if args.output:
            summary = db.get_benchmark_summary(args.run_id)
            if summary:
                output_path = Path(args.output)
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(summary.to_dict(), f, indent=2, ensure_ascii=False)
                print(f"\n✓ Summary exported to {output_path}")

        return 0

    except Exception as e:
        print(f"\n✗ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

    finally:
        conn.close()


def cmd_compare(args: argparse.Namespace) -> int:
    """Compare score distributions between models."""
    print("=" * 70)
    print("MODEL SCORE COMPARISON")
    print("=" * 70)
    print()

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            # Get score distributions for the run
            cur.execute("""
                SELECT e.model_name, s.score, COUNT(*) as count
                FROM benchmarking.scoring s
                JOIN benchmarking.evaluators e ON s.evaluator_id = e.evaluator_id
                JOIN benchmarking.benchmark_runs br ON s.question_id = br.question_id
                WHERE br.run_id = %s
                GROUP BY e.model_name, s.score
                ORDER BY e.model_name, s.score
            """, (args.run_id,))

            rows = cur.fetchall()

            if not rows:
                print(f"No scores found for run #{args.run_id}")
                return 1

            # Group by model
            model_scores = {}
            for model, score, count in rows:
                if model not in model_scores:
                    model_scores[model] = {i: 0 for i in range(6)}
                model_scores[model][score] = count

            # Print comparison table
            print(f"{'Model':>35}  {'0':>5}  {'1':>5}  {'2':>5}  {'3':>5}  {'4':>5}  {'5':>5}  {'Total':>6}")
            print("-" * 80)

            for model, scores in sorted(model_scores.items()):
                total = sum(scores.values())
                model_short = model[:35]
                print(f"{model_short:>35}  {scores[0]:>5}  {scores[1]:>5}  {scores[2]:>5}  "
                      f"{scores[3]:>5}  {scores[4]:>5}  {scores[5]:>5}  {total:>6}")

        return 0

    except Exception as e:
        print(f"\n✗ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

    finally:
        conn.close()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Benchmark document scoring models against an authoritative model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Benchmark two models
  python model_benchmark_cli.py "What are the benefits of exercise?" \\
      --models gpt-oss:20b medgemma4B_it_q8:latest

  # With custom authoritative model and output
  python model_benchmark_cli.py "COVID-19 vaccine efficacy" \\
      --models gpt-oss:20b qwen2.5:32b \\
      --authoritative gpt-oss:120B \\
      --output results.json

  # View benchmark history
  python model_benchmark_cli.py history

  # View specific run details
  python model_benchmark_cli.py show --run-id 5
        """
    )

    # Global options
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Benchmark command (default when question is provided)
    bench_parser = subparsers.add_parser('benchmark', help='Run a benchmark')
    bench_parser.add_argument(
        'question',
        type=str,
        help='Research question for semantic search'
    )
    bench_parser.add_argument(
        '--models', '-m',
        nargs='+',
        required=True,
        help='Model names to benchmark (e.g., gpt-oss:20b medgemma4B_it_q8:latest)'
    )
    bench_parser.add_argument(
        '--authoritative', '-a',
        type=str,
        default=BEST_REASONING_MODEL,
        help=f'Authoritative model for ground truth (default: {BEST_REASONING_MODEL})'
    )
    bench_parser.add_argument(
        '--threshold', '-t',
        type=float,
        default=SEMANTIC_THRESHOLD,
        help=f'Semantic search threshold (default: {SEMANTIC_THRESHOLD})'
    )
    bench_parser.add_argument(
        '--max-docs',
        type=int,
        default=None,
        help='Maximum documents to score (default: all found)'
    )
    bench_parser.add_argument(
        '--temperature',
        type=float,
        default=DEFAULT_TEMPERATURE,
        help=f'Model temperature (default: {DEFAULT_TEMPERATURE})'
    )
    bench_parser.add_argument(
        '--top-p',
        type=float,
        default=DEFAULT_TOP_P,
        help=f'Model top-p (default: {DEFAULT_TOP_P})'
    )
    bench_parser.add_argument(
        '--ollama-host',
        type=str,
        default=DEFAULT_OLLAMA_HOST,
        help=f'Ollama server URL (default: {DEFAULT_OLLAMA_HOST})'
    )
    bench_parser.add_argument(
        '--user',
        type=str,
        default=None,
        help='Username for tracking'
    )
    bench_parser.add_argument(
        '-o', '--output',
        type=str,
        help='Output JSON file for results'
    )
    bench_parser.set_defaults(func=cmd_benchmark)

    # History command
    hist_parser = subparsers.add_parser('history', help='Show benchmark history')
    hist_parser.add_argument(
        '--limit',
        type=int,
        default=20,
        help='Number of runs to show (default: 20)'
    )
    hist_parser.set_defaults(func=cmd_history)

    # Show command
    show_parser = subparsers.add_parser('show', help='Show benchmark run details')
    show_parser.add_argument(
        '--run-id', '-r',
        type=int,
        required=True,
        help='Benchmark run ID'
    )
    show_parser.add_argument(
        '-o', '--output',
        type=str,
        help='Export summary to JSON file'
    )
    show_parser.set_defaults(func=cmd_show)

    # Compare command
    compare_parser = subparsers.add_parser('compare', help='Compare model score distributions')
    compare_parser.add_argument(
        '--run-id', '-r',
        type=int,
        required=True,
        help='Benchmark run ID'
    )
    compare_parser.set_defaults(func=cmd_compare)

    # Parse arguments
    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    # Handle no command - check if first positional looks like a question
    if not args.command:
        # Check if there's a positional argument that could be a question
        if len(sys.argv) > 1 and not sys.argv[1].startswith('-'):
            # Re-parse with benchmark as default
            new_args = ['benchmark'] + sys.argv[1:]
            args = parser.parse_args(new_args)
        else:
            parser.print_help()
            return 0

    # Execute command
    if hasattr(args, 'func'):
        return args.func(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
