#!/usr/bin/env python3
"""
Statistical Analysis for Fact-Checker Database

Calculates comprehensive statistics for fact-checking evaluations including:
- Concordance rates with 95% confidence intervals (binomial proportions)
- Cohen's kappa for inter-evaluator agreement with standard errors
- Confusion matrices comparing automated and human annotations
- Confidence calibration curves relating confidence levels to accuracy
- Statistical significance tests (chi-square and t-tests)
- Category-specific transition rates (Yes→No, No→Yes, certainty changes)

Usage:
    uv run python fact_checker_stats.py
    uv run python fact_checker_stats.py --export-csv stats_output/
    uv run python fact_checker_stats.py --plot
"""

import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import json

import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import chi2_contingency, ttest_ind, binom
import matplotlib.pyplot as plt
import seaborn as sns

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bmlibrarian.database import get_db_manager


@dataclass
class ConcordanceStats:
    """Concordance rate statistics with confidence intervals."""
    n_total: int
    n_concordant: int
    n_discordant: int
    concordance_rate: float
    ci_lower: float
    ci_upper: float
    method: str = "Wilson score interval"


@dataclass
class KappaStats:
    """Cohen's kappa statistics with standard error."""
    kappa: float
    std_error: float
    ci_lower: float
    ci_upper: float
    interpretation: str
    n_observations: int
    agreement_rate: float
    expected_agreement: float


@dataclass
class ConfusionMatrix:
    """Confusion matrix for classification comparison."""
    matrix: np.ndarray
    labels: List[str]
    accuracy: float
    precision: Dict[str, float]
    recall: Dict[str, float]
    f1_score: Dict[str, float]


@dataclass
class TransitionStats:
    """Category-specific transition statistics."""
    yes_to_no: int
    yes_to_no_pct: float
    no_to_yes: int
    no_to_yes_pct: float
    to_maybe: int
    to_maybe_pct: float
    stable: int
    stable_pct: float
    total: int


class FactCheckerStatistics:
    """Comprehensive statistical analysis for fact-checker database."""

    def __init__(self):
        """Initialize with database connection."""
        self.db_manager = get_db_manager()

    def _get_ai_vs_expected(self) -> pd.DataFrame:
        """
        Get AI evaluations vs expected answers.

        Returns:
            DataFrame with columns: ai_evaluation, expected_answer, confidence
        """
        with self.db_manager.get_connection() as conn:
            query = """
                SELECT
                    ae.evaluation as ai_evaluation,
                    s.expected_answer,
                    ae.confidence,
                    ae.documents_reviewed,
                    ae.supporting_citations + ae.contradicting_citations + ae.neutral_citations as total_citations
                FROM factcheck.ai_evaluations ae
                JOIN factcheck.statements s ON ae.statement_id = s.statement_id
                WHERE s.expected_answer IS NOT NULL
                    AND ae.version = (
                        SELECT MAX(version)
                        FROM factcheck.ai_evaluations
                        WHERE statement_id = s.statement_id
                    )
                ORDER BY ae.evaluation_id
            """
            return pd.read_sql_query(query, conn)

    def _get_ai_vs_human(self) -> pd.DataFrame:
        """
        Get AI evaluations vs human annotations.

        Returns:
            DataFrame with AI and human evaluations for same statements
        """
        with self.db_manager.get_connection() as conn:
            query = """
                SELECT
                    s.statement_id,
                    s.statement_text,
                    ae.evaluation as ai_evaluation,
                    ae.confidence as ai_confidence,
                    ha.annotation as human_annotation,
                    ha.confidence as human_confidence,
                    a.username as annotator
                FROM factcheck.statements s
                JOIN factcheck.ai_evaluations ae ON s.statement_id = ae.statement_id
                JOIN factcheck.human_annotations ha ON s.statement_id = ha.statement_id
                JOIN factcheck.annotators a ON ha.annotator_id = a.annotator_id
                WHERE ae.version = (
                    SELECT MAX(version)
                    FROM factcheck.ai_evaluations
                    WHERE statement_id = s.statement_id
                )
                ORDER BY s.statement_id, a.username
            """
            return pd.read_sql_query(query, conn)

    def _get_human_annotations_pairs(self) -> pd.DataFrame:
        """
        Get pairs of human annotations for inter-rater agreement.

        Returns:
            DataFrame with annotation pairs from different annotators
        """
        with self.db_manager.get_connection() as conn:
            query = """
                SELECT
                    ha1.statement_id,
                    a1.username as annotator1,
                    ha1.annotation as annotation1,
                    ha1.confidence as confidence1,
                    a2.username as annotator2,
                    ha2.annotation as annotation2,
                    ha2.confidence as confidence2
                FROM factcheck.human_annotations ha1
                JOIN factcheck.human_annotations ha2
                    ON ha1.statement_id = ha2.statement_id
                    AND ha1.annotator_id < ha2.annotator_id
                JOIN factcheck.annotators a1 ON ha1.annotator_id = a1.annotator_id
                JOIN factcheck.annotators a2 ON ha2.annotator_id = a2.annotator_id
                ORDER BY ha1.statement_id
            """
            return pd.read_sql_query(query, conn)

    def calculate_concordance(self, df: pd.DataFrame,
                             col1: str, col2: str,
                             confidence_level: float = 0.95) -> ConcordanceStats:
        """
        Calculate concordance rate with 95% CI using Wilson score interval.

        Args:
            df: DataFrame with evaluation columns
            col1: First column name
            col2: Second column name
            confidence_level: Confidence level for interval (default: 0.95)

        Returns:
            ConcordanceStats with concordance rate and CI
        """
        # Remove rows with missing values
        df_clean = df[[col1, col2]].dropna()

        n_total = len(df_clean)
        if n_total == 0:
            return ConcordanceStats(0, 0, 0, 0.0, 0.0, 0.0)

        n_concordant = (df_clean[col1] == df_clean[col2]).sum()
        n_discordant = n_total - n_concordant
        concordance_rate = n_concordant / n_total

        # Wilson score interval for binomial proportion
        z = stats.norm.ppf((1 + confidence_level) / 2)
        p = concordance_rate
        n = n_total

        denominator = 1 + z**2 / n
        center = (p + z**2 / (2 * n)) / denominator
        margin = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denominator

        ci_lower = max(0.0, center - margin)
        ci_upper = min(1.0, center + margin)

        return ConcordanceStats(
            n_total=n_total,
            n_concordant=n_concordant,
            n_discordant=n_discordant,
            concordance_rate=concordance_rate,
            ci_lower=ci_lower,
            ci_upper=ci_upper
        )

    def calculate_cohens_kappa(self, df: pd.DataFrame,
                               col1: str, col2: str) -> KappaStats:
        """
        Calculate Cohen's kappa with standard error and confidence interval.

        Args:
            df: DataFrame with evaluation columns
            col1: First rater column
            col2: Second rater column

        Returns:
            KappaStats with kappa, SE, and CI
        """
        # Remove rows with missing values
        df_clean = df[[col1, col2]].dropna()

        if len(df_clean) == 0:
            return KappaStats(0.0, 0.0, 0.0, 0.0, "No data", 0, 0.0, 0.0)

        # Get unique labels
        all_labels = sorted(set(df_clean[col1].unique()) | set(df_clean[col2].unique()))
        n = len(df_clean)

        # Create confusion matrix
        matrix = pd.crosstab(df_clean[col1], df_clean[col2],
                            rownames=[col1], colnames=[col2])

        # Ensure matrix is square with all labels
        for label in all_labels:
            if label not in matrix.index:
                matrix.loc[label] = 0
            if label not in matrix.columns:
                matrix[label] = 0
        matrix = matrix.loc[all_labels, all_labels]

        # Calculate observed agreement
        p_o = np.trace(matrix.values) / n

        # Calculate expected agreement
        row_sums = matrix.sum(axis=1).values
        col_sums = matrix.sum(axis=0).values
        p_e = np.sum(row_sums * col_sums) / (n ** 2)

        # Calculate kappa
        if p_e == 1.0:
            kappa = 1.0
            std_error = 0.0
        else:
            kappa = (p_o - p_e) / (1 - p_e)

            # Calculate standard error (Fleiss et al., 1969)
            # Simplified formula for binary/multi-class classification
            p_sum = np.sum(row_sums * col_sums / n**2)
            std_error = np.sqrt((p_o * (1 - p_o)) / (n * (1 - p_e)**2))

        # 95% confidence interval
        z = 1.96  # 95% CI
        ci_lower = kappa - z * std_error
        ci_upper = kappa + z * std_error

        # Interpret kappa (Landis & Koch, 1977)
        if kappa < 0:
            interpretation = "Poor (less than chance)"
        elif kappa < 0.20:
            interpretation = "Slight agreement"
        elif kappa < 0.40:
            interpretation = "Fair agreement"
        elif kappa < 0.60:
            interpretation = "Moderate agreement"
        elif kappa < 0.80:
            interpretation = "Substantial agreement"
        else:
            interpretation = "Almost perfect agreement"

        return KappaStats(
            kappa=kappa,
            std_error=std_error,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            interpretation=interpretation,
            n_observations=n,
            agreement_rate=p_o,
            expected_agreement=p_e
        )

    def create_confusion_matrix(self, df: pd.DataFrame,
                               true_col: str, pred_col: str) -> ConfusionMatrix:
        """
        Create confusion matrix with metrics.

        Args:
            df: DataFrame with evaluation columns
            true_col: Ground truth column
            pred_col: Predicted/comparison column

        Returns:
            ConfusionMatrix with metrics
        """
        # Remove rows with missing values
        df_clean = df[[true_col, pred_col]].dropna()

        if len(df_clean) == 0:
            return ConfusionMatrix(
                matrix=np.array([[]]),
                labels=[],
                accuracy=0.0,
                precision={},
                recall={},
                f1_score={}
            )

        # Get unique labels (sorted for consistency)
        labels = sorted(set(df_clean[true_col].unique()) | set(df_clean[pred_col].unique()))

        # Create confusion matrix
        matrix = pd.crosstab(
            df_clean[true_col],
            df_clean[pred_col],
            rownames=[true_col],
            colnames=[pred_col]
        )

        # Ensure matrix is square with all labels
        for label in labels:
            if label not in matrix.index:
                matrix.loc[label] = 0
            if label not in matrix.columns:
                matrix[label] = 0
        matrix = matrix.loc[labels, labels]

        # Convert to numpy array
        cm = matrix.values

        # Calculate metrics
        accuracy = np.trace(cm) / cm.sum() if cm.sum() > 0 else 0.0

        precision = {}
        recall = {}
        f1_score = {}

        for i, label in enumerate(labels):
            # Precision: TP / (TP + FP)
            tp = cm[i, i]
            fp = cm[:, i].sum() - tp
            precision[label] = tp / (tp + fp) if (tp + fp) > 0 else 0.0

            # Recall: TP / (TP + FN)
            fn = cm[i, :].sum() - tp
            recall[label] = tp / (tp + fn) if (tp + fn) > 0 else 0.0

            # F1 score
            p = precision[label]
            r = recall[label]
            f1_score[label] = 2 * p * r / (p + r) if (p + r) > 0 else 0.0

        return ConfusionMatrix(
            matrix=cm,
            labels=labels,
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1_score=f1_score
        )

    def calculate_transition_stats(self, df: pd.DataFrame,
                                   original_col: str,
                                   revised_col: str) -> TransitionStats:
        """
        Calculate category-specific transition statistics.

        Args:
            df: DataFrame with evaluation columns
            original_col: Original evaluation column
            revised_col: Revised/comparison evaluation column

        Returns:
            TransitionStats with transition counts and percentages
        """
        # Remove rows with missing values
        df_clean = df[[original_col, revised_col]].dropna()
        total = len(df_clean)

        if total == 0:
            return TransitionStats(0, 0.0, 0, 0.0, 0, 0.0, 0, 0.0, 0)

        # Count transitions
        yes_to_no = ((df_clean[original_col] == 'yes') &
                     (df_clean[revised_col] == 'no')).sum()
        no_to_yes = ((df_clean[original_col] == 'no') &
                     (df_clean[revised_col] == 'yes')).sum()

        # To "maybe" from any definite answer
        to_maybe = ((df_clean[original_col].isin(['yes', 'no'])) &
                    (df_clean[revised_col] == 'maybe')).sum()

        # Stable (unchanged)
        stable = (df_clean[original_col] == df_clean[revised_col]).sum()

        return TransitionStats(
            yes_to_no=yes_to_no,
            yes_to_no_pct=100.0 * yes_to_no / total,
            no_to_yes=no_to_yes,
            no_to_yes_pct=100.0 * no_to_yes / total,
            to_maybe=to_maybe,
            to_maybe_pct=100.0 * to_maybe / total,
            stable=stable,
            stable_pct=100.0 * stable / total,
            total=total
        )

    def chi_square_test(self, df: pd.DataFrame,
                       col1: str, col2: str) -> Dict[str, Any]:
        """
        Perform chi-square test for independence.

        Args:
            df: DataFrame with categorical columns
            col1: First column
            col2: Second column

        Returns:
            Dict with chi2 statistic, p-value, and interpretation
        """
        # Remove rows with missing values
        df_clean = df[[col1, col2]].dropna()

        if len(df_clean) == 0:
            return {
                'chi2': 0.0,
                'p_value': 1.0,
                'dof': 0,
                'significant': False,
                'interpretation': 'No data'
            }

        # Create contingency table
        contingency = pd.crosstab(df_clean[col1], df_clean[col2])

        # Perform chi-square test
        chi2, p_value, dof, expected = chi2_contingency(contingency)

        # Check significance at p < 0.05
        significant = p_value < 0.05

        if significant:
            interpretation = f"Significant association (p = {p_value:.4f} < 0.05)"
        else:
            interpretation = f"No significant association (p = {p_value:.4f} ≥ 0.05)"

        return {
            'chi2': chi2,
            'p_value': p_value,
            'dof': dof,
            'expected_frequencies': expected,
            'significant': significant,
            'interpretation': interpretation
        }

    def confidence_calibration(self, df: pd.DataFrame,
                               true_col: str, pred_col: str,
                               conf_col: str) -> pd.DataFrame:
        """
        Calculate confidence calibration (confidence vs accuracy).

        Args:
            df: DataFrame with predictions and confidence
            true_col: Ground truth column
            pred_col: Prediction column
            conf_col: Confidence level column

        Returns:
            DataFrame with confidence levels and corresponding accuracy
        """
        # Remove rows with missing values
        df_clean = df[[true_col, pred_col, conf_col]].dropna()

        if len(df_clean) == 0:
            return pd.DataFrame(columns=['confidence', 'n', 'accuracy', 'ci_lower', 'ci_upper'])

        # Calculate accuracy for each confidence level
        calibration = []
        for conf_level in ['low', 'medium', 'high']:
            df_conf = df_clean[df_clean[conf_col] == conf_level]
            n = len(df_conf)

            if n > 0:
                correct = (df_conf[true_col] == df_conf[pred_col]).sum()
                accuracy = correct / n

                # Calculate 95% CI using Wilson score interval
                p = accuracy
                z = 1.96
                denominator = 1 + z**2 / n
                center = (p + z**2 / (2 * n)) / denominator
                margin = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denominator

                ci_lower = max(0.0, center - margin)
                ci_upper = min(1.0, center + margin)
            else:
                accuracy = 0.0
                ci_lower = 0.0
                ci_upper = 0.0

            calibration.append({
                'confidence': conf_level,
                'n': n,
                'accuracy': accuracy,
                'ci_lower': ci_lower,
                'ci_upper': ci_upper
            })

        return pd.DataFrame(calibration)

    def generate_full_report(self, output_dir: Optional[Path] = None,
                           create_plots: bool = False) -> Dict[str, Any]:
        """
        Generate comprehensive statistical report.

        Args:
            output_dir: Directory to save CSV exports (optional)
            create_plots: Whether to create visualization plots

        Returns:
            Dictionary with all statistical results
        """
        print("=" * 80)
        print("FACT-CHECKER STATISTICAL ANALYSIS REPORT")
        print("=" * 80)
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        results = {}

        # 1. AI vs Expected Answer Analysis
        print("\n" + "=" * 80)
        print("1. AI EVALUATIONS VS EXPECTED ANSWERS")
        print("=" * 80)

        df_ai_expected = self._get_ai_vs_expected()

        if len(df_ai_expected) > 0:
            # Concordance rate
            concordance = self.calculate_concordance(
                df_ai_expected, 'ai_evaluation', 'expected_answer'
            )
            results['ai_vs_expected_concordance'] = asdict(concordance)

            print(f"\nConcordance Rate (AI vs Expected):")
            print(f"  Total statements: {concordance.n_total}")
            print(f"  Concordant: {concordance.n_concordant} ({concordance.concordance_rate:.1%})")
            print(f"  Discordant: {concordance.n_discordant}")
            print(f"  95% CI: [{concordance.ci_lower:.1%}, {concordance.ci_upper:.1%}]")
            print(f"  Method: {concordance.method}")

            # Cohen's kappa
            kappa = self.calculate_cohens_kappa(
                df_ai_expected, 'ai_evaluation', 'expected_answer'
            )
            results['ai_vs_expected_kappa'] = asdict(kappa)

            print(f"\nCohen's Kappa:")
            print(f"  κ = {kappa.kappa:.4f} ± {kappa.std_error:.4f}")
            print(f"  95% CI: [{kappa.ci_lower:.4f}, {kappa.ci_upper:.4f}]")
            print(f"  Interpretation: {kappa.interpretation}")
            print(f"  Observed agreement: {kappa.agreement_rate:.1%}")
            print(f"  Expected agreement (chance): {kappa.expected_agreement:.1%}")

            # Confusion matrix
            cm = self.create_confusion_matrix(
                df_ai_expected, 'expected_answer', 'ai_evaluation'
            )
            results['ai_vs_expected_confusion'] = {
                'matrix': cm.matrix.tolist(),
                'labels': cm.labels,
                'accuracy': cm.accuracy,
                'precision': cm.precision,
                'recall': cm.recall,
                'f1_score': cm.f1_score
            }

            print(f"\nConfusion Matrix (Expected as rows, AI as columns):")
            cm_df = pd.DataFrame(cm.matrix, index=cm.labels, columns=cm.labels)
            print(cm_df.to_string())
            print(f"\nAccuracy: {cm.accuracy:.1%}")
            print(f"\nPer-class metrics:")
            for label in cm.labels:
                print(f"  {label.upper()}:")
                print(f"    Precision: {cm.precision[label]:.3f}")
                print(f"    Recall: {cm.recall[label]:.3f}")
                print(f"    F1-score: {cm.f1_score[label]:.3f}")

            # Chi-square test
            chi2_result = self.chi_square_test(
                df_ai_expected, 'expected_answer', 'ai_evaluation'
            )
            results['ai_vs_expected_chi2'] = chi2_result

            print(f"\nChi-square Test for Independence:")
            print(f"  χ² = {chi2_result['chi2']:.4f}")
            print(f"  p-value = {chi2_result['p_value']:.6f}")
            print(f"  df = {chi2_result['dof']}")
            print(f"  {chi2_result['interpretation']}")

            # Confidence calibration
            calibration = self.confidence_calibration(
                df_ai_expected, 'expected_answer', 'ai_evaluation', 'confidence'
            )
            results['ai_confidence_calibration'] = calibration.to_dict('records')

            print(f"\nConfidence Calibration:")
            for _, row in calibration.iterrows():
                print(f"  {row['confidence'].upper()} confidence (n={row['n']}):")
                print(f"    Accuracy: {row['accuracy']:.1%}")
                print(f"    95% CI: [{row['ci_lower']:.1%}, {row['ci_upper']:.1%}]")

            # Transition statistics
            transitions = self.calculate_transition_stats(
                df_ai_expected, 'expected_answer', 'ai_evaluation'
            )
            results['transitions'] = asdict(transitions)

            print(f"\nCategory-Specific Transitions:")
            print(f"  Yes → No: {transitions.yes_to_no} ({transitions.yes_to_no_pct:.1f}%)")
            print(f"  No → Yes: {transitions.no_to_yes} ({transitions.no_to_yes_pct:.1f}%)")
            print(f"  To Maybe: {transitions.to_maybe} ({transitions.to_maybe_pct:.1f}%)")
            print(f"  Stable: {transitions.stable} ({transitions.stable_pct:.1f}%)")
        else:
            print("\nNo data available for AI vs Expected analysis.")
            results['ai_vs_expected_concordance'] = None

        # 2. AI vs Human Analysis
        print("\n" + "=" * 80)
        print("2. AI EVALUATIONS VS HUMAN ANNOTATIONS")
        print("=" * 80)

        df_ai_human = self._get_ai_vs_human()

        if len(df_ai_human) > 0:
            # Concordance rate
            concordance_ah = self.calculate_concordance(
                df_ai_human, 'ai_evaluation', 'human_annotation'
            )
            results['ai_vs_human_concordance'] = asdict(concordance_ah)

            print(f"\nConcordance Rate (AI vs Human):")
            print(f"  Total comparisons: {concordance_ah.n_total}")
            print(f"  Concordant: {concordance_ah.n_concordant} ({concordance_ah.concordance_rate:.1%})")
            print(f"  Discordant: {concordance_ah.n_discordant}")
            print(f"  95% CI: [{concordance_ah.ci_lower:.1%}, {concordance_ah.ci_upper:.1%}]")

            # Cohen's kappa
            kappa_ah = self.calculate_cohens_kappa(
                df_ai_human, 'ai_evaluation', 'human_annotation'
            )
            results['ai_vs_human_kappa'] = asdict(kappa_ah)

            print(f"\nCohen's Kappa:")
            print(f"  κ = {kappa_ah.kappa:.4f} ± {kappa_ah.std_error:.4f}")
            print(f"  95% CI: [{kappa_ah.ci_lower:.4f}, {kappa_ah.ci_upper:.4f}]")
            print(f"  Interpretation: {kappa_ah.interpretation}")

            # Confusion matrix
            cm_ah = self.create_confusion_matrix(
                df_ai_human, 'human_annotation', 'ai_evaluation'
            )
            results['ai_vs_human_confusion'] = {
                'matrix': cm_ah.matrix.tolist(),
                'labels': cm_ah.labels,
                'accuracy': cm_ah.accuracy,
                'precision': cm_ah.precision,
                'recall': cm_ah.recall,
                'f1_score': cm_ah.f1_score
            }

            print(f"\nConfusion Matrix (Human as rows, AI as columns):")
            cm_ah_df = pd.DataFrame(cm_ah.matrix, index=cm_ah.labels, columns=cm_ah.labels)
            print(cm_ah_df.to_string())
            print(f"\nAccuracy: {cm_ah.accuracy:.1%}")
        else:
            print("\nNo data available for AI vs Human analysis.")
            results['ai_vs_human_concordance'] = None

        # 3. Inter-Rater Agreement (Human annotators)
        print("\n" + "=" * 80)
        print("3. INTER-RATER AGREEMENT (HUMAN ANNOTATORS)")
        print("=" * 80)

        df_human_pairs = self._get_human_annotations_pairs()

        if len(df_human_pairs) > 0:
            # Concordance rate
            concordance_hh = self.calculate_concordance(
                df_human_pairs, 'annotation1', 'annotation2'
            )
            results['human_inter_rater_concordance'] = asdict(concordance_hh)

            print(f"\nConcordance Rate (Human-Human):")
            print(f"  Total pairs: {concordance_hh.n_total}")
            print(f"  Concordant: {concordance_hh.n_concordant} ({concordance_hh.concordance_rate:.1%})")
            print(f"  Discordant: {concordance_hh.n_discordant}")
            print(f"  95% CI: [{concordance_hh.ci_lower:.1%}, {concordance_hh.ci_upper:.1%}]")

            # Cohen's kappa
            kappa_hh = self.calculate_cohens_kappa(
                df_human_pairs, 'annotation1', 'annotation2'
            )
            results['human_inter_rater_kappa'] = asdict(kappa_hh)

            print(f"\nCohen's Kappa:")
            print(f"  κ = {kappa_hh.kappa:.4f} ± {kappa_hh.std_error:.4f}")
            print(f"  95% CI: [{kappa_hh.ci_lower:.4f}, {kappa_hh.ci_upper:.4f}]")
            print(f"  Interpretation: {kappa_hh.interpretation}")

            # Per-annotator-pair breakdown
            print(f"\nPer-Annotator-Pair Analysis:")
            for (ann1, ann2), group in df_human_pairs.groupby(['annotator1', 'annotator2']):
                pair_concordance = self.calculate_concordance(
                    group, 'annotation1', 'annotation2'
                )
                pair_kappa = self.calculate_cohens_kappa(
                    group, 'annotation1', 'annotation2'
                )
                print(f"  {ann1} vs {ann2}:")
                print(f"    n = {pair_concordance.n_total}")
                print(f"    Concordance: {pair_concordance.concordance_rate:.1%}")
                print(f"    κ = {pair_kappa.kappa:.4f}")
        else:
            print("\nNo paired human annotations available for inter-rater analysis.")
            results['human_inter_rater_concordance'] = None

        # 4. Export to CSV if requested
        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            print(f"\n" + "=" * 80)
            print(f"4. EXPORTING DATA TO CSV")
            print("=" * 80)

            if len(df_ai_expected) > 0:
                csv_path = output_dir / 'ai_vs_expected.csv'
                df_ai_expected.to_csv(csv_path, index=False)
                print(f"  Exported: {csv_path}")

            if len(df_ai_human) > 0:
                csv_path = output_dir / 'ai_vs_human.csv'
                df_ai_human.to_csv(csv_path, index=False)
                print(f"  Exported: {csv_path}")

            if len(df_human_pairs) > 0:
                csv_path = output_dir / 'human_pairs.csv'
                df_human_pairs.to_csv(csv_path, index=False)
                print(f"  Exported: {csv_path}")

            # Export summary statistics
            summary_path = output_dir / 'summary_statistics.json'
            with open(summary_path, 'w') as f:
                json.dump(results, f, indent=2, default=str)
            print(f"  Exported: {summary_path}")

        # 5. Create plots if requested
        if create_plots and output_dir:
            self._create_plots(results, df_ai_expected, df_ai_human,
                             df_human_pairs, output_dir)

        print("\n" + "=" * 80)
        print("ANALYSIS COMPLETE")
        print("=" * 80 + "\n")

        return results

    def _create_plots(self, results: Dict, df_ai_expected: pd.DataFrame,
                     df_ai_human: pd.DataFrame, df_human_pairs: pd.DataFrame,
                     output_dir: Path):
        """Create visualization plots for statistical analysis."""
        print(f"\n" + "=" * 80)
        print(f"5. CREATING VISUALIZATION PLOTS")
        print("=" * 80)

        sns.set_style("whitegrid")

        # Plot 1: Confusion matrix heatmap (AI vs Expected)
        if len(df_ai_expected) > 0 and results.get('ai_vs_expected_confusion'):
            cm_data = results['ai_vs_expected_confusion']
            plt.figure(figsize=(10, 8))
            sns.heatmap(
                cm_data['matrix'],
                annot=True,
                fmt='d',
                xticklabels=cm_data['labels'],
                yticklabels=cm_data['labels'],
                cmap='Blues',
                cbar_kws={'label': 'Count'}
            )
            plt.xlabel('AI Evaluation')
            plt.ylabel('Expected Answer')
            plt.title('Confusion Matrix: AI Evaluation vs Expected Answer')
            plt.tight_layout()

            plot_path = output_dir / 'confusion_matrix_ai_vs_expected.png'
            plt.savefig(plot_path, dpi=300, bbox_inches='tight')
            print(f"  Created: {plot_path}")
            plt.close()

        # Plot 2: Confidence calibration curve
        if results.get('ai_confidence_calibration'):
            cal_df = pd.DataFrame(results['ai_confidence_calibration'])

            plt.figure(figsize=(10, 6))

            # Map confidence to numeric values for plotting
            conf_map = {'low': 1, 'medium': 2, 'high': 3}
            cal_df['conf_num'] = cal_df['confidence'].map(conf_map)

            plt.errorbar(
                cal_df['conf_num'],
                cal_df['accuracy'],
                yerr=[cal_df['accuracy'] - cal_df['ci_lower'],
                      cal_df['ci_upper'] - cal_df['accuracy']],
                fmt='o-',
                linewidth=2,
                markersize=10,
                capsize=5,
                label='Observed accuracy'
            )

            # Add ideal calibration line
            plt.axhline(y=0.33, color='r', linestyle='--', alpha=0.3, label='Random (3-class)')
            plt.axhline(y=0.50, color='g', linestyle='--', alpha=0.3, label='Moderate')
            plt.axhline(y=1.00, color='b', linestyle='--', alpha=0.3, label='Perfect')

            plt.xticks([1, 2, 3], ['Low', 'Medium', 'High'])
            plt.xlabel('AI Confidence Level')
            plt.ylabel('Accuracy')
            plt.title('Confidence Calibration Curve')
            plt.ylim([0, 1.05])
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()

            plot_path = output_dir / 'confidence_calibration.png'
            plt.savefig(plot_path, dpi=300, bbox_inches='tight')
            print(f"  Created: {plot_path}")
            plt.close()

        # Plot 3: Transition sankey/bar chart
        if results.get('transitions'):
            trans = results['transitions']

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

            # Transition counts
            categories = ['Yes→No', 'No→Yes', 'To Maybe', 'Stable']
            counts = [trans['yes_to_no'], trans['no_to_yes'],
                     trans['to_maybe'], trans['stable']]
            colors = ['#d62728', '#2ca02c', '#ff7f0e', '#1f77b4']

            ax1.bar(categories, counts, color=colors, alpha=0.7, edgecolor='black')
            ax1.set_ylabel('Count')
            ax1.set_title('Transition Counts')
            ax1.grid(True, alpha=0.3, axis='y')

            for i, (cat, count) in enumerate(zip(categories, counts)):
                ax1.text(i, count, str(count), ha='center', va='bottom', fontweight='bold')

            # Transition percentages
            percentages = [trans['yes_to_no_pct'], trans['no_to_yes_pct'],
                          trans['to_maybe_pct'], trans['stable_pct']]

            ax2.bar(categories, percentages, color=colors, alpha=0.7, edgecolor='black')
            ax2.set_ylabel('Percentage (%)')
            ax2.set_title('Transition Percentages')
            ax2.grid(True, alpha=0.3, axis='y')
            ax2.set_ylim([0, max(percentages) * 1.15])

            for i, (cat, pct) in enumerate(zip(categories, percentages)):
                ax2.text(i, pct, f'{pct:.1f}%', ha='center', va='bottom', fontweight='bold')

            plt.tight_layout()

            plot_path = output_dir / 'transition_analysis.png'
            plt.savefig(plot_path, dpi=300, bbox_inches='tight')
            print(f"  Created: {plot_path}")
            plt.close()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Comprehensive statistical analysis for fact-checker database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run analysis and print to console
    uv run python fact_checker_stats.py

    # Export results to CSV files
    uv run python fact_checker_stats.py --export-csv stats_output/

    # Create visualization plots
    uv run python fact_checker_stats.py --export-csv stats_output/ --plot
"""
    )

    parser.add_argument('--export-csv', type=str, metavar='DIR',
                       help='Export results to CSV files in specified directory')
    parser.add_argument('--plot', action='store_true',
                       help='Create visualization plots (requires --export-csv)')

    args = parser.parse_args()

    # Validate arguments
    if args.plot and not args.export_csv:
        print("Error: --plot requires --export-csv to be specified")
        sys.exit(1)

    # Create analyzer
    analyzer = FactCheckerStatistics()

    # Generate report
    output_dir = Path(args.export_csv) if args.export_csv else None
    results = analyzer.generate_full_report(
        output_dir=output_dir,
        create_plots=args.plot
    )

    sys.exit(0)


if __name__ == '__main__':
    main()
