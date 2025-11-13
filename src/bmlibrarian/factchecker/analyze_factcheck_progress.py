#!/usr/bin/env python3
"""
Analyze fact-checking progress from ongoing batch processing.

This script safely reads and analyzes fact-checking results while the
FactCheckerAgent is still writing to the file. It handles incomplete
or corrupted JSON gracefully and provides real-time statistics.

Usage:
    python analyze_factcheck_progress.py results.json
    python analyze_factcheck_progress.py results.json --watch
"""

import json
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime


class ProgressAnalyzer:
    """Analyze fact-checking progress with safe file handling."""

    def __init__(self, results_file: str):
        self.results_file = Path(results_file)

    def safe_read_results(self) -> Optional[List[Dict[str, Any]]]:
        """
        Safely read results from file, handling incomplete JSON.

        Returns:
            List of result dicts, or None if file cannot be read
        """
        if not self.results_file.exists():
            return None

        try:
            # Read file content
            with open(self.results_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Try to parse as complete JSON
            try:
                data = json.loads(content)
                return data.get('results', [])
            except json.JSONDecodeError:
                # File might be incomplete - try to extract results manually
                return self._extract_results_manually(content)

        except Exception as e:
            print(f"Warning: Error reading file: {e}")
            return None

    def _extract_results_manually(self, content: str) -> List[Dict[str, Any]]:
        """
        Extract results from potentially incomplete JSON.

        Parses line by line to extract individual result objects,
        even if the overall JSON structure is incomplete.

        Args:
            content: Raw file content

        Returns:
            List of successfully parsed result dicts
        """
        results = []

        # Try to find the results array
        if '"results": [' not in content:
            return results

        # Split by result boundaries (each result starts with statement field)
        # Look for complete result objects
        lines = content.split('\n')
        current_obj = []
        in_results = False
        brace_count = 0

        for line in lines:
            if '"results": [' in line:
                in_results = True
                continue

            if not in_results:
                continue

            # Track braces to find complete objects
            brace_count += line.count('{') - line.count('}')
            current_obj.append(line)

            # When we close an object at depth 0, try to parse it
            if brace_count == 0 and current_obj:
                obj_text = '\n'.join(current_obj).strip()
                if obj_text.endswith(','):
                    obj_text = obj_text[:-1]  # Remove trailing comma

                # Try to parse this object
                try:
                    result = json.loads(obj_text)
                    if 'statement' in result:  # Verify it's a result object
                        results.append(result)
                except json.JSONDecodeError:
                    pass  # Skip malformed objects

                current_obj = []

        return results

    def analyze_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze results and compute statistics.

        Args:
            results: List of result dictionaries

        Returns:
            Dictionary with analysis statistics
        """
        stats = {
            'total_checked': len(results),
            'evaluations': {'yes': 0, 'no': 0, 'maybe': 0, 'error': 0},
            'confidence': {'high': 0, 'medium': 0, 'low': 0},
            'has_expected': 0,
            'matches': 0,
            'mismatches': 0,
            'concordance_pct': 0.0,
            'discordance_pct': 0.0,
            'avg_documents': 0.0,
            'avg_citations': 0.0,
            'latest_timestamp': None
        }

        total_docs = 0
        total_citations = 0

        for result in results:
            # Count evaluations
            evaluation = result.get('evaluation', 'unknown')
            if evaluation in stats['evaluations']:
                stats['evaluations'][evaluation] += 1

            # Count confidence levels
            confidence = result.get('confidence', 'low')
            if confidence in stats['confidence']:
                stats['confidence'][confidence] += 1

            # Check expected answer matching
            expected = result.get('expected_answer')
            if expected:
                stats['has_expected'] += 1
                matches = result.get('matches_expected')

                if matches is True:
                    stats['matches'] += 1
                elif matches is False:
                    stats['mismatches'] += 1

            # Accumulate metadata
            metadata = result.get('metadata', {})
            total_docs += metadata.get('documents_reviewed', 0)

            # Count citations from evidence list
            evidence_list = result.get('evidence_list', [])
            total_citations += len(evidence_list)

            # Track latest timestamp
            timestamp = metadata.get('timestamp')
            if timestamp:
                if not stats['latest_timestamp'] or timestamp > stats['latest_timestamp']:
                    stats['latest_timestamp'] = timestamp

        # Calculate percentages
        if stats['has_expected'] > 0:
            stats['concordance_pct'] = round(
                (stats['matches'] / stats['has_expected']) * 100, 2
            )
            stats['discordance_pct'] = round(
                (stats['mismatches'] / stats['has_expected']) * 100, 2
            )

        # Calculate averages
        if stats['total_checked'] > 0:
            stats['avg_documents'] = round(total_docs / stats['total_checked'], 1)
            stats['avg_citations'] = round(total_citations / stats['total_checked'], 1)

        return stats

    def format_report(self, stats: Dict[str, Any]) -> str:
        """
        Format statistics into a readable report.

        Args:
            stats: Statistics dictionary from analyze_results

        Returns:
            Formatted report string
        """
        report = []
        report.append("=" * 70)
        report.append("FACT-CHECKING PROGRESS REPORT")
        report.append("=" * 70)

        # Check if file exists
        if stats['total_checked'] == 0:
            report.append("\n⚠️  No results found in file yet.")
            return "\n".join(report)

        # Overall progress
        report.append(f"\n📊 OVERALL PROGRESS")
        report.append(f"   Statements Checked: {stats['total_checked']}")
        if stats['latest_timestamp']:
            try:
                dt = datetime.fromisoformat(stats['latest_timestamp'].replace('Z', '+00:00'))
                report.append(f"   Latest Update: {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            except:
                pass

        # Evaluation breakdown
        report.append(f"\n📋 EVALUATION BREAKDOWN")
        total = stats['total_checked']
        for eval_type in ['yes', 'no', 'maybe', 'error']:
            count = stats['evaluations'][eval_type]
            pct = (count / total * 100) if total > 0 else 0
            report.append(f"   {eval_type.upper():8s}: {count:4d} ({pct:5.1f}%)")

        # Confidence levels
        report.append(f"\n🎯 CONFIDENCE LEVELS")
        for conf_level in ['high', 'medium', 'low']:
            count = stats['confidence'][conf_level]
            pct = (count / total * 100) if total > 0 else 0
            report.append(f"   {conf_level.capitalize():8s}: {count:4d} ({pct:5.1f}%)")

        # Validation statistics
        if stats['has_expected'] > 0:
            report.append(f"\n✅ VALIDATION AGAINST EXPECTED ANSWERS")
            report.append(f"   Statements with Expected Answer: {stats['has_expected']}")
            report.append(f"   Concordance (Matches):  {stats['matches']:4d} ({stats['concordance_pct']:5.1f}%)")
            report.append(f"   Discordance (Mismatch): {stats['mismatches']:4d} ({stats['discordance_pct']:5.1f}%)")

            # Show accuracy if we have matches/mismatches
            if stats['matches'] + stats['mismatches'] > 0:
                accuracy = stats['matches'] / (stats['matches'] + stats['mismatches']) * 100
                report.append(f"   Accuracy: {accuracy:.1f}%")

        # Processing statistics
        report.append(f"\n📈 PROCESSING STATISTICS")
        report.append(f"   Avg Documents Reviewed: {stats['avg_documents']}")
        report.append(f"   Avg Citations Extracted: {stats['avg_citations']}")

        report.append("\n" + "=" * 70)

        return "\n".join(report)

    def run_once(self) -> bool:
        """
        Run analysis once and print report.

        Returns:
            True if analysis succeeded, False otherwise
        """
        results = self.safe_read_results()

        if results is None:
            print(f"❌ Cannot read file: {self.results_file}")
            return False

        stats = self.analyze_results(results)
        report = self.format_report(stats)
        print(report)

        return True

    def watch(self, interval: int = 30):
        """
        Continuously watch file and update report.

        Args:
            interval: Seconds between updates
        """
        print(f"👀 Watching {self.results_file} (updating every {interval}s)")
        print("Press Ctrl+C to stop\n")

        try:
            while True:
                # Clear screen (works on Unix/Linux/Mac)
                print("\033[2J\033[H", end="")

                self.run_once()
                time.sleep(interval)

        except KeyboardInterrupt:
            print("\n\n✋ Stopped watching.")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Analyze fact-checking progress from ongoing batch processing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Analyze once and exit
    python analyze_factcheck_progress.py results.json

    # Watch and update every 30 seconds
    python analyze_factcheck_progress.py results.json --watch

    # Watch with custom interval
    python analyze_factcheck_progress.py results.json --watch --interval 60
"""
    )

    parser.add_argument('results_file', help='Path to fact-checking results JSON file')
    parser.add_argument('--watch', action='store_true',
                       help='Continuously watch file and update statistics')
    parser.add_argument('--interval', type=int, default=30,
                       help='Update interval in seconds for watch mode (default: 30)')

    args = parser.parse_args()

    # Validate file exists (for watch mode, it might not exist yet)
    if not args.watch and not Path(args.results_file).exists():
        print(f"❌ Error: File not found: {args.results_file}")
        sys.exit(1)

    # Create analyzer
    analyzer = ProgressAnalyzer(args.results_file)

    # Run analysis
    if args.watch:
        analyzer.watch(args.interval)
    else:
        success = analyzer.run_once()
        sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
