#!/usr/bin/env python3
"""
Transparency Analyzer CLI - Detect undisclosed bias risk in biomedical papers

Command-line interface for assessing transparency and disclosure completeness
of biomedical research publications. Uses local LLM (Ollama) for offline analysis.

Usage:
    # Assess a single document by database ID
    python transparency_analyzer_cli.py assess --doc-id 12345

    # Assess a batch of documents with full text
    python transparency_analyzer_cli.py assess --has-fulltext --limit 50

    # Assess documents matching a search query
    python transparency_analyzer_cli.py assess --query "cardiovascular exercise"

    # Show statistics from previous assessments
    python transparency_analyzer_cli.py stats

    # Show detailed assessment for a document
    python transparency_analyzer_cli.py show --doc-id 12345

    # Export assessments to JSON or CSV
    python transparency_analyzer_cli.py export --output results.json
    python transparency_analyzer_cli.py export --output results.csv --format csv
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg
from dotenv import load_dotenv

from src.bmlibrarian.agents import TransparencyAgent, TransparencyAssessment
from src.bmlibrarian.agents.transparency_data import RiskLevel
from src.bmlibrarian.config import BMLibrarianConfig

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the CLI.

    Args:
        verbose: Enable debug-level logging.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_db_connection() -> psycopg.Connection:
    """Get database connection from environment.

    Returns:
        Active database connection.

    Raises:
        SystemExit: If connection fails.
    """
    user_env_path = Path.home() / ".bmlibrarian" / ".env"
    if user_env_path.exists():
        load_dotenv(user_env_path)
    else:
        load_dotenv()

    try:
        import os
        conn = psycopg.connect(
            dbname=os.environ.get("POSTGRES_DB", "knowledgebase"),
            user=os.environ.get("POSTGRES_USER", ""),
            password=os.environ.get("POSTGRES_PASSWORD", ""),
            host=os.environ.get("POSTGRES_HOST", "localhost"),
            port=os.environ.get("POSTGRES_PORT", "5432"),
        )
        return conn
    except Exception as e:
        print(f"Error: Could not connect to database: {e}", file=sys.stderr)
        sys.exit(1)


def create_agent(config: Optional[BMLibrarianConfig] = None) -> TransparencyAgent:
    """Create a TransparencyAgent from configuration.

    Args:
        config: Optional BMLibrarianConfig instance.

    Returns:
        Configured TransparencyAgent.
    """
    if config is None:
        config = BMLibrarianConfig()

    model = config.get_model("transparency")
    host = config.get("ollama", {}).get("host", "http://localhost:11434")

    agent_config = config.get_agent_config("transparency")
    temperature = agent_config.get("temperature", 0.1)
    top_p = agent_config.get("top_p", 0.9)

    return TransparencyAgent(
        model=model,
        host=host,
        temperature=temperature,
        top_p=top_p,
    )


def fetch_documents_for_assessment(
    conn: psycopg.Connection,
    doc_ids: Optional[List[int]] = None,
    has_fulltext: bool = False,
    query: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Fetch documents from database for transparency assessment.

    Args:
        conn: Database connection.
        doc_ids: Specific document IDs to fetch.
        has_fulltext: Only fetch documents with full text.
        query: Search query to filter documents.
        limit: Maximum number of documents.

    Returns:
        List of document dictionaries.
    """
    documents = []

    with conn.cursor() as cur:
        if doc_ids:
            cur.execute(
                """
                SELECT id, title, abstract, full_text, doi,
                       array_to_string(authors, ', ') as authors_str
                FROM public.document
                WHERE id = ANY(%s)
                """,
                (doc_ids,),
            )
        elif query:
            cur.execute(
                """
                SELECT id, title, abstract, full_text, doi,
                       array_to_string(authors, ', ') as authors_str
                FROM public.document
                WHERE (title ILIKE %s OR abstract ILIKE %s)
                AND (abstract IS NOT NULL AND abstract != '')
                ORDER BY publication_date DESC NULLS LAST
                LIMIT %s
                """,
                (f"%{query}%", f"%{query}%", limit),
            )
        elif has_fulltext:
            cur.execute(
                """
                SELECT id, title, abstract, full_text, doi,
                       array_to_string(authors, ', ') as authors_str
                FROM public.document
                WHERE full_text IS NOT NULL AND full_text != ''
                AND id NOT IN (SELECT document_id FROM transparency.assessments)
                ORDER BY publication_date DESC NULLS LAST
                LIMIT %s
                """,
                (limit,),
            )
        else:
            cur.execute(
                """
                SELECT id, title, abstract, full_text, doi,
                       array_to_string(authors, ', ') as authors_str
                FROM public.document
                WHERE (abstract IS NOT NULL AND abstract != '')
                AND id NOT IN (SELECT document_id FROM transparency.assessments)
                ORDER BY publication_date DESC NULLS LAST
                LIMIT %s
                """,
                (limit,),
            )

        for row in cur.fetchall():
            doc_id, title, abstract, full_text, doi, authors_str = row
            documents.append({
                "id": doc_id,
                "title": title or "Untitled",
                "abstract": abstract or "",
                "full_text": full_text or "",
                "doi": doi,
                "authors": authors_str,
            })

    return documents


def save_assessment(
    conn: psycopg.Connection,
    assessment: TransparencyAssessment,
) -> None:
    """Save a transparency assessment to the database.

    Args:
        conn: Database connection.
        assessment: TransparencyAssessment to save.
    """
    try:
        doc_id = int(assessment.document_id)
    except (ValueError, TypeError):
        logger.warning(f"Cannot save assessment - non-numeric document_id: {assessment.document_id}")
        return

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO transparency.assessments (
                document_id, has_funding_disclosure, funding_statement,
                funding_sources, is_industry_funded, industry_funding_confidence,
                funding_disclosure_quality,
                has_coi_disclosure, coi_statement, conflicts_identified,
                coi_disclosure_quality,
                data_availability, data_availability_statement,
                has_author_contributions, contributions_statement,
                has_trial_registration, trial_registry_ids,
                transparency_score, overall_confidence, risk_level,
                risk_indicators, strengths, weaknesses,
                is_retracted, retraction_reason, trial_sponsor_class,
                model_used, agent_version
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (document_id)
            DO UPDATE SET
                has_funding_disclosure = EXCLUDED.has_funding_disclosure,
                funding_statement = EXCLUDED.funding_statement,
                funding_sources = EXCLUDED.funding_sources,
                is_industry_funded = EXCLUDED.is_industry_funded,
                industry_funding_confidence = EXCLUDED.industry_funding_confidence,
                funding_disclosure_quality = EXCLUDED.funding_disclosure_quality,
                has_coi_disclosure = EXCLUDED.has_coi_disclosure,
                coi_statement = EXCLUDED.coi_statement,
                conflicts_identified = EXCLUDED.conflicts_identified,
                coi_disclosure_quality = EXCLUDED.coi_disclosure_quality,
                data_availability = EXCLUDED.data_availability,
                data_availability_statement = EXCLUDED.data_availability_statement,
                has_author_contributions = EXCLUDED.has_author_contributions,
                contributions_statement = EXCLUDED.contributions_statement,
                has_trial_registration = EXCLUDED.has_trial_registration,
                trial_registry_ids = EXCLUDED.trial_registry_ids,
                transparency_score = EXCLUDED.transparency_score,
                overall_confidence = EXCLUDED.overall_confidence,
                risk_level = EXCLUDED.risk_level,
                risk_indicators = EXCLUDED.risk_indicators,
                strengths = EXCLUDED.strengths,
                weaknesses = EXCLUDED.weaknesses,
                is_retracted = EXCLUDED.is_retracted,
                retraction_reason = EXCLUDED.retraction_reason,
                trial_sponsor_class = EXCLUDED.trial_sponsor_class,
                model_used = EXCLUDED.model_used,
                agent_version = EXCLUDED.agent_version,
                assessed_at = NOW()
            """,
            (
                doc_id,
                assessment.has_funding_disclosure,
                assessment.funding_statement,
                assessment.funding_sources,
                assessment.is_industry_funded,
                assessment.industry_funding_confidence,
                assessment.funding_disclosure_quality,
                assessment.has_coi_disclosure,
                assessment.coi_statement,
                assessment.conflicts_identified,
                assessment.coi_disclosure_quality,
                assessment.data_availability,
                assessment.data_availability_statement,
                assessment.has_author_contributions,
                assessment.contributions_statement,
                assessment.has_trial_registration,
                assessment.trial_registry_ids,
                assessment.transparency_score,
                assessment.overall_confidence,
                assessment.risk_level,
                assessment.risk_indicators,
                assessment.strengths,
                assessment.weaknesses,
                assessment.is_retracted,
                assessment.retraction_reason,
                assessment.trial_sponsor_class,
                assessment.model_used,
                assessment.agent_version,
            ),
        )
    conn.commit()


# ──────────────────────────────────────────────────────────────────────────────
# CLI Commands
# ──────────────────────────────────────────────────────────────────────────────

def cmd_assess(args: argparse.Namespace) -> None:
    """Run transparency assessment on documents.

    Args:
        args: Parsed command line arguments.
    """
    conn = get_db_connection()
    agent = create_agent()

    # Determine which documents to assess
    doc_ids = None
    if args.doc_id:
        doc_ids = [args.doc_id]

    documents = fetch_documents_for_assessment(
        conn,
        doc_ids=doc_ids,
        has_fulltext=args.has_fulltext,
        query=args.query,
        limit=args.limit,
    )

    if not documents:
        print("No documents found matching the criteria.")
        return

    print(f"\nAssessing transparency for {len(documents)} document(s)...\n")

    def progress_callback(current: int, total: int, title: str) -> None:
        """Display progress during batch assessment."""
        print(f"  [{current}/{total}] {title[:60]}...")

    assessments = agent.assess_batch(
        documents,
        progress_callback=progress_callback,
    )

    # Optionally enrich with bulk metadata
    for assessment in assessments:
        agent.enrich_with_metadata(assessment)

    # Save to database
    saved_count = 0
    for assessment in assessments:
        try:
            save_assessment(conn, assessment)
            saved_count += 1
        except Exception as e:
            logger.error(f"Failed to save assessment for document {assessment.document_id}: {e}")

    conn.close()

    # Print results
    print(f"\n{'='*60}")
    print(f"Assessment Complete: {len(assessments)} of {len(documents)} documents assessed")
    print(f"Saved to database: {saved_count}")
    print(f"{'='*60}\n")

    for assessment in assessments:
        print(agent.format_assessment_summary(assessment))

    # Print aggregate stats
    if len(assessments) > 1:
        risk_dist = agent.get_risk_distribution(assessments)
        print("\n--- RISK DISTRIBUTION ---")
        for level, count in risk_dist.items():
            print(f"  {level.upper()}: {count}")

    # Export if requested
    if args.output:
        output_path = Path(args.output)
        if output_path.suffix == ".csv":
            agent.export_to_csv(assessments, args.output)
        else:
            agent.export_to_json(assessments, args.output)
        print(f"\nResults exported to: {args.output}")


def cmd_stats(args: argparse.Namespace) -> None:
    """Show transparency assessment statistics.

    Args:
        args: Parsed command line arguments.
    """
    conn = get_db_connection()

    with conn.cursor() as cur:
        # Try the view first, fall back to direct query
        try:
            cur.execute("SELECT * FROM transparency.v_statistics")
            row = cur.fetchone()
        except Exception:
            conn.rollback()
            print("No transparency assessments found. Run 'assess' first.")
            conn.close()
            return

    if not row:
        print("No transparency assessments found. Run 'assess' first.")
        conn.close()
        return

    (total, low, medium, high, unknown, avg_score,
     industry_count, funding_count, coi_count, trial_count, retracted_count) = row

    print(f"\n{'='*60}")
    print(f"TRANSPARENCY ASSESSMENT STATISTICS")
    print(f"{'='*60}")
    print(f"\nTotal Assessed: {total}")
    print(f"Average Score:  {avg_score:.1f}/10" if avg_score else "Average Score:  N/A")
    print(f"\n--- Risk Distribution ---")
    print(f"  Low Risk:     {low}")
    print(f"  Medium Risk:  {medium}")
    print(f"  High Risk:    {high}")
    print(f"  Unknown:      {unknown}")
    print(f"\n--- Disclosure Rates ---")
    if total > 0:
        print(f"  With Funding Disclosure:   {funding_count} ({funding_count/total:.0%})")
        print(f"  With COI Disclosure:       {coi_count} ({coi_count/total:.0%})")
        print(f"  With Trial Registration:   {trial_count} ({trial_count/total:.0%})")
        print(f"  Industry Funded:           {industry_count} ({industry_count/total:.0%})")
        print(f"  Retracted:                 {retracted_count} ({retracted_count/total:.0%})")
    print(f"{'='*60}\n")

    conn.close()


def cmd_show(args: argparse.Namespace) -> None:
    """Show detailed assessment for a document.

    Args:
        args: Parsed command line arguments.
    """
    conn = get_db_connection()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.*, d.title, d.doi, d.abstract
            FROM transparency.assessments a
            JOIN public.document d ON d.id = a.document_id
            WHERE a.document_id = %s
            """,
            (args.doc_id,),
        )
        row = cur.fetchone()

    if not row:
        print(f"No transparency assessment found for document ID {args.doc_id}.")
        print("Run 'assess --doc-id {id}' to create one.")
        conn.close()
        return

    # Build assessment from database row (use column names)
    colnames = [desc[0] for desc in conn.cursor().description] if hasattr(conn, 'cursor') else []

    # Simpler approach: just fetch and display using the agent formatter
    agent = TransparencyAgent(show_model_info=False)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT document_id, transparency_score, risk_level, overall_confidence,
                   has_funding_disclosure, funding_statement, funding_sources,
                   is_industry_funded, industry_funding_confidence, funding_disclosure_quality,
                   has_coi_disclosure, coi_statement, conflicts_identified, coi_disclosure_quality,
                   data_availability, data_availability_statement,
                   has_author_contributions, contributions_statement,
                   has_trial_registration, trial_registry_ids,
                   risk_indicators, strengths, weaknesses,
                   is_retracted, retraction_reason, trial_sponsor_class,
                   model_used, agent_version, assessed_at
            FROM transparency.assessments
            WHERE document_id = %s
            """,
            (args.doc_id,),
        )
        row = cur.fetchone()

    if not row:
        print(f"No assessment found for document {args.doc_id}")
        conn.close()
        return

    # Fetch title
    with conn.cursor() as cur:
        cur.execute("SELECT title FROM public.document WHERE id = %s", (args.doc_id,))
        title_row = cur.fetchone()
        title = title_row[0] if title_row else "Unknown"

    assessment = TransparencyAssessment(
        document_id=str(row[0]),
        document_title=title,
        transparency_score=row[1] or 0.0,
        risk_level=row[2] or "unknown",
        overall_confidence=row[3] or 0.0,
        has_funding_disclosure=row[4] or False,
        funding_statement=row[5],
        funding_sources=row[6] or [],
        is_industry_funded=row[7],
        industry_funding_confidence=row[8] or 0.0,
        funding_disclosure_quality=row[9] or 0.0,
        has_coi_disclosure=row[10] or False,
        coi_statement=row[11],
        conflicts_identified=row[12] or [],
        coi_disclosure_quality=row[13] or 0.0,
        data_availability=row[14] or "not_stated",
        data_availability_statement=row[15],
        has_author_contributions=row[16] or False,
        contributions_statement=row[17],
        has_trial_registration=row[18] or False,
        trial_registry_ids=row[19] or [],
        risk_indicators=row[20] or [],
        strengths=row[21] or [],
        weaknesses=row[22] or [],
        is_retracted=row[23],
        retraction_reason=row[24],
        trial_sponsor_class=row[25],
        model_used=row[26],
        agent_version=row[27],
    )

    print(agent.format_assessment_summary(assessment))
    conn.close()


def cmd_export(args: argparse.Namespace) -> None:
    """Export assessments to file.

    Args:
        args: Parsed command line arguments.
    """
    conn = get_db_connection()
    agent = TransparencyAgent(show_model_info=False)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.document_id, d.title, d.doi,
                   a.transparency_score, a.risk_level, a.overall_confidence,
                   a.has_funding_disclosure, a.funding_sources,
                   a.is_industry_funded, a.funding_disclosure_quality,
                   a.has_coi_disclosure, a.coi_disclosure_quality,
                   a.data_availability, a.has_author_contributions,
                   a.has_trial_registration, a.trial_registry_ids,
                   a.risk_indicators, a.strengths, a.weaknesses,
                   a.is_retracted, a.trial_sponsor_class
            FROM transparency.assessments a
            JOIN public.document d ON d.id = a.document_id
            ORDER BY a.transparency_score ASC
            """
        )
        rows = cur.fetchall()

    if not rows:
        print("No assessments to export.")
        conn.close()
        return

    assessments = []
    for row in rows:
        assessment = TransparencyAssessment(
            document_id=str(row[0]),
            document_title=row[1] or "Unknown",
            doi=row[2],
            transparency_score=row[3] or 0.0,
            risk_level=row[4] or "unknown",
            overall_confidence=row[5] or 0.0,
            has_funding_disclosure=row[6] or False,
            funding_sources=row[7] or [],
            is_industry_funded=row[8],
            funding_disclosure_quality=row[9] or 0.0,
            has_coi_disclosure=row[10] or False,
            coi_disclosure_quality=row[11] or 0.0,
            data_availability=row[12] or "not_stated",
            has_author_contributions=row[13] or False,
            has_trial_registration=row[14] or False,
            trial_registry_ids=row[15] or [],
            risk_indicators=row[16] or [],
            strengths=row[17] or [],
            weaknesses=row[18] or [],
            is_retracted=row[19],
            trial_sponsor_class=row[20],
        )
        assessments.append(assessment)

    output_path = Path(args.output)
    if args.format == "csv" or output_path.suffix == ".csv":
        agent.export_to_csv(assessments, args.output)
    else:
        agent.export_to_json(assessments, args.output)

    print(f"Exported {len(assessments)} assessments to {args.output}")
    conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# Argument Parser
# ──────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        description="Transparency Analyzer - Detect undisclosed bias risk in biomedical papers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # assess command
    assess_parser = subparsers.add_parser("assess", help="Run transparency assessment")
    assess_parser.add_argument("--doc-id", type=int, help="Assess a specific document by ID")
    assess_parser.add_argument("--query", type=str, help="Search query to filter documents")
    assess_parser.add_argument("--has-fulltext", action="store_true",
                               help="Only assess documents with full text")
    assess_parser.add_argument("--limit", type=int, default=100,
                               help="Maximum documents to assess (default: 100)")
    assess_parser.add_argument("-o", "--output", type=str,
                               help="Export results to file (.json or .csv)")

    # stats command
    subparsers.add_parser("stats", help="Show assessment statistics")

    # show command
    show_parser = subparsers.add_parser("show", help="Show assessment for a document")
    show_parser.add_argument("--doc-id", type=int, required=True, help="Document ID")

    # export command
    export_parser = subparsers.add_parser("export", help="Export all assessments")
    export_parser.add_argument("-o", "--output", type=str, required=True,
                               help="Output file path (.json or .csv)")
    export_parser.add_argument("--format", choices=["json", "csv"], default="json",
                               help="Export format (default: json)")

    return parser


def main() -> None:
    """Main entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(args.verbose)

    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "assess": cmd_assess,
        "stats": cmd_stats,
        "show": cmd_show,
        "export": cmd_export,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
