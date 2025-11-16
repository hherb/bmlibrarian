# Fact-Checker Statistical Analysis Guide

This guide explains how to use the comprehensive statistical analysis tool for the BMLibrarian fact-checker database.

## Overview

The `fact_checker_stats.py` script provides comprehensive statistical analysis for evaluating the performance and reliability of the fact-checking system. It calculates multiple metrics to assess:

- **Concordance rates**: Agreement between AI evaluations and expected answers or human annotations
- **Inter-rater reliability**: Agreement between different human annotators using Cohen's kappa
- **Performance metrics**: Confusion matrices, precision, recall, F1-scores
- **Confidence calibration**: How well AI confidence levels correspond to actual accuracy
- **Statistical significance**: Chi-square tests and t-tests for categorical and continuous data
- **Transition analysis**: Category-specific changes (Yes→No, No→Yes, certainty changes)

## Requirements

The script requires the following Python packages (automatically installed via `uv sync`):

- `numpy>=1.26.0`
- `pandas>=2.1.0`
- `scipy>=1.11.0`
- `matplotlib>=3.8.0`
- `seaborn>=0.13.0`

These have been added to `pyproject.toml` and will be installed when you run `uv sync`.

## Usage

### Basic Usage (Console Output Only)

```bash
uv run python fact_checker_stats.py
```

This will:
- Connect to the PostgreSQL database (using credentials from `~/.bmlibrarian/config.json` or environment variables)
- Query the `factcheck` schema tables
- Calculate all statistical metrics
- Print a comprehensive report to the console

### Export Results to CSV

```bash
uv run python fact_checker_stats.py --export-csv stats_output/
```

This will:
- Generate the statistical analysis
- Export raw data to CSV files in `stats_output/`:
  - `ai_vs_expected.csv`: AI evaluations vs expected answers
  - `ai_vs_human.csv`: AI evaluations vs human annotations
  - `human_pairs.csv`: Paired human annotations for inter-rater analysis
  - `summary_statistics.json`: Complete statistical results in JSON format

### Create Visualization Plots

```bash
uv run python fact_checker_stats.py --export-csv stats_output/ --plot
```

This will:
- Generate the statistical analysis
- Export CSV files (as above)
- Create PNG visualizations in `stats_output/`:
  - `confusion_matrix_ai_vs_expected.png`: Heatmap of AI vs expected confusion matrix
  - `confidence_calibration.png`: Confidence calibration curve with error bars
  - `transition_analysis.png`: Bar charts showing category transitions

## Output Sections

### 1. AI Evaluations vs Expected Answers

Compares AI-generated evaluations against ground truth expected answers from the training data.

**Metrics Calculated:**
- **Concordance Rate**: Percentage of exact matches with 95% Wilson score confidence interval
- **Cohen's Kappa (κ)**: Inter-rater reliability coefficient with standard error and interpretation
  - κ < 0.00: Poor (less than chance agreement)
  - 0.00-0.20: Slight agreement
  - 0.21-0.40: Fair agreement
  - 0.41-0.60: Moderate agreement
  - 0.61-0.80: Substantial agreement
  - 0.81-1.00: Almost perfect agreement
- **Confusion Matrix**: Cross-tabulation of expected vs AI evaluations
- **Per-Class Metrics**: Precision, recall, and F1-score for each category (yes/no/maybe)
- **Chi-Square Test**: Tests independence between expected and AI evaluations (p < 0.05 = significant)

**Confidence Calibration:**
- Analyzes how well AI confidence levels (low/medium/high) correlate with actual accuracy
- Provides 95% confidence intervals for each confidence level
- Helps identify overconfidence or underconfidence in AI predictions

**Transition Statistics:**
- Yes → No: Statements where expected was "yes" but AI evaluated as "no"
- No → Yes: Statements where expected was "no" but AI evaluated as "yes"
- To Maybe: Statements that became uncertain (moved to "maybe" from definite answer)
- Stable: Statements with unchanged evaluations

### 2. AI Evaluations vs Human Annotations

Compares AI evaluations against human expert annotations.

**Metrics Calculated:**
- Concordance rate with 95% CI
- Cohen's kappa with interpretation
- Confusion matrix (human as ground truth, AI as predictions)
- Accuracy and per-class metrics

### 3. Inter-Rater Agreement (Human Annotators)

Analyzes agreement between different human annotators for the same statements.

**Metrics Calculated:**
- Overall concordance rate for all annotation pairs
- Cohen's kappa for human-human agreement
- Per-annotator-pair breakdown showing individual agreement rates

This section is crucial for:
- Establishing baseline inter-annotator agreement
- Identifying annotators who may need additional training
- Understanding inherent difficulty/ambiguity in certain statements

## Statistical Methods

### Concordance Rate Confidence Intervals

Uses the **Wilson score interval** for binomial proportions, which provides better coverage than the normal approximation, especially for small sample sizes or extreme proportions.

Formula:
```
CI = (p̂ + z²/2n ± z√[p̂(1-p̂)/n + z²/4n²]) / (1 + z²/n)
```

where:
- p̂ = observed concordance rate
- n = sample size
- z = 1.96 for 95% confidence

### Cohen's Kappa Standard Error

Calculated using the Fleiss et al. (1969) formula for multi-class classification:

```
SE(κ) = √[p_o(1-p_o) / (n(1-p_e)²)]
```

where:
- p_o = observed agreement
- p_e = expected agreement by chance
- n = number of observations

### Chi-Square Test for Independence

Tests whether two categorical variables are independent using:

```
χ² = Σ[(O_ij - E_ij)² / E_ij]
```

where O_ij are observed frequencies and E_ij are expected frequencies under independence.

**Interpretation:**
- p < 0.05: Reject null hypothesis of independence (significant association exists)
- p ≥ 0.05: Fail to reject null hypothesis (no significant association detected)

### Confusion Matrix Metrics

- **Accuracy**: (TP + TN) / (TP + TN + FP + FN)
- **Precision**: TP / (TP + FP) — of all positive predictions, what fraction was correct?
- **Recall**: TP / (TP + FN) — of all actual positives, what fraction was identified?
- **F1-Score**: 2 × (Precision × Recall) / (Precision + Recall) — harmonic mean of precision and recall

## Interpretation Guidelines

### Concordance Rate

- **80-100%**: Excellent agreement
- **60-80%**: Good agreement
- **40-60%**: Moderate agreement
- **20-40%**: Fair agreement
- **0-20%**: Poor agreement

### Cohen's Kappa (Landis & Koch, 1977)

- **κ < 0.00**: Less than chance agreement (poor)
- **0.00-0.20**: Slight agreement
- **0.21-0.40**: Fair agreement
- **0.41-0.60**: Moderate agreement
- **0.61-0.80**: Substantial agreement
- **0.81-1.00**: Almost perfect agreement

### Statistical Significance

- **p < 0.001**: Very strong evidence against null hypothesis
- **0.001 ≤ p < 0.01**: Strong evidence
- **0.01 ≤ p < 0.05**: Moderate evidence (conventional threshold)
- **p ≥ 0.05**: Insufficient evidence to reject null hypothesis

## Example Output

```
================================================================================
FACT-CHECKER STATISTICAL ANALYSIS REPORT
================================================================================
Generated: 2025-11-16 10:30:45

================================================================================
1. AI EVALUATIONS VS EXPECTED ANSWERS
================================================================================

Concordance Rate (AI vs Expected):
  Total statements: 1000
  Concordant: 850 (85.0%)
  Discordant: 150
  95% CI: [82.7%, 87.1%]
  Method: Wilson score interval

Cohen's Kappa:
  κ = 0.7650 ± 0.0215
  95% CI: [0.7228, 0.8072]
  Interpretation: Substantial agreement
  Observed agreement: 85.0%
  Expected agreement (chance): 35.2%

Confusion Matrix (Expected as rows, AI as columns):
         yes   no  maybe
yes      420   15     25
no        18  395     12
maybe     22   18     75

Accuracy: 89.0%

Per-class metrics:
  YES:
    Precision: 0.913
    Recall: 0.913
    F1-score: 0.913
  NO:
    Precision: 0.923
    Recall: 0.930
    F1-score: 0.927
  MAYBE:
    Precision: 0.670
    Recall: 0.652
    F1-score: 0.661

Chi-square Test for Independence:
  χ² = 1342.5678
  p-value = 0.000000
  df = 4
  Significant association (p = 0.0000 < 0.05)

Confidence Calibration:
  HIGH confidence (n=600):
    Accuracy: 92.3%
    95% CI: [90.0%, 94.2%]
  MEDIUM confidence (n=300):
    Accuracy: 78.7%
    95% CI: [73.9%, 82.9%]
  LOW confidence (n=100):
    Accuracy: 62.0%
    95% CI: [52.4%, 70.8%]

Category-Specific Transitions:
  Yes → No: 15 (1.5%)
  No → Yes: 18 (1.8%)
  To Maybe: 37 (3.7%)
  Stable: 850 (85.0%)
```

## Database Requirements

The script queries the following tables in the `factcheck` schema:

### Required Tables
- `factcheck.statements`: Biomedical statements to fact-check
- `factcheck.ai_evaluations`: AI-generated evaluations
- `factcheck.human_annotations`: Human expert annotations
- `factcheck.annotators`: Annotator metadata

### Required Columns

**statements:**
- `statement_id`, `statement_text`, `expected_answer`

**ai_evaluations:**
- `evaluation_id`, `statement_id`, `evaluation`, `confidence`, `version`
- `documents_reviewed`, `supporting_citations`, `contradicting_citations`, `neutral_citations`

**human_annotations:**
- `annotation_id`, `statement_id`, `annotator_id`, `annotation`, `confidence`

**annotators:**
- `annotator_id`, `username`

## Troubleshooting

### Database Connection Errors

If you see "connection refused" or similar errors:

1. Ensure PostgreSQL is running
2. Check database credentials in `~/.bmlibrarian/config.json` or environment variables
3. Verify the `factcheck` schema exists: `psql -d knowledgebase -c "\dt factcheck.*"`

### No Data Available

If you see "No data available for analysis":

1. Verify statements exist: `SELECT COUNT(*) FROM factcheck.statements;`
2. Check for AI evaluations: `SELECT COUNT(*) FROM factcheck.ai_evaluations;`
3. Ensure expected answers are populated: `SELECT COUNT(*) FROM factcheck.statements WHERE expected_answer IS NOT NULL;`

### Import Errors

If you see import errors for numpy, pandas, scipy, etc.:

1. Run `uv sync` to install dependencies
2. Verify installation: `uv run python -c "import pandas, numpy, scipy, matplotlib, seaborn"`

## Advanced Usage

### Programmatic Access

You can use the `FactCheckerStatistics` class programmatically in your own scripts:

```python
from fact_checker_stats import FactCheckerStatistics

# Create analyzer
analyzer = FactCheckerStatistics()

# Calculate specific metrics
df_ai_expected = analyzer._get_ai_vs_expected()
concordance = analyzer.calculate_concordance(df_ai_expected, 'ai_evaluation', 'expected_answer')
kappa = analyzer.calculate_cohens_kappa(df_ai_expected, 'ai_evaluation', 'expected_answer')

print(f"Concordance: {concordance.concordance_rate:.1%} [{concordance.ci_lower:.1%}, {concordance.ci_upper:.1%}]")
print(f"Cohen's κ: {kappa.kappa:.4f} ± {kappa.std_error:.4f}")
```

### Custom Analyses

You can extend the `FactCheckerStatistics` class to add custom analyses:

```python
class CustomStatistics(FactCheckerStatistics):
    def analyze_by_confidence(self):
        """Custom analysis grouped by confidence level."""
        df = self._get_ai_vs_expected()
        for conf in ['low', 'medium', 'high']:
            df_conf = df[df['confidence'] == conf]
            concordance = self.calculate_concordance(df_conf, 'ai_evaluation', 'expected_answer')
            print(f"{conf.upper()}: {concordance.concordance_rate:.1%}")
```

## References

1. **Wilson Score Interval**: Wilson, E.B. (1927). "Probable inference, the law of succession, and statistical inference". Journal of the American Statistical Association.

2. **Cohen's Kappa**: Cohen, J. (1960). "A coefficient of agreement for nominal scales". Educational and Psychological Measurement.

3. **Kappa Interpretation**: Landis, J.R. & Koch, G.G. (1977). "The measurement of observer agreement for categorical data". Biometrics.

4. **Chi-Square Test**: Pearson, K. (1900). "On the criterion that a given system of deviations from the probable in the case of a correlated system of variables is such that it can be reasonably supposed to have arisen from random sampling". Philosophical Magazine.

## See Also

- `fact_checker_cli.py`: Batch fact-checking tool
- `fact_checker_review_gui.py`: Human annotation interface
- `export_review_package.py`: Distribution system for external reviewers
- `doc/users/fact_checker_guide.md`: Fact-checker user guide
- `FACT_CHECKER_DISTRIBUTION_QUICKSTART.md`: Inter-rater reliability workflow

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review the fact-checker documentation in `doc/users/`
3. Report issues at https://github.com/anthropics/bmlibrarian/issues
