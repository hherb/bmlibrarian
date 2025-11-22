# PaperChecker Verdict Analysis User Guide

## Overview

The verdict analysis is the final step in PaperChecker's fact-checking workflow. After searching for counter-evidence and generating reports, the system analyzes whether the evidence supports, contradicts, or is undecided about the original research claims.

## Understanding Verdicts

### Verdict Categories

PaperChecker classifies each statement into one of three categories:

#### Contradicts
The counter-evidence **contradicts** the original statement when:
- Multiple studies provide evidence against the original claim
- High-quality research directly challenges the statement
- The counter-claim is well-supported by literature

**Example:**
> **Original:** "Metformin is superior to GLP-1 agonists for type 2 diabetes"
>
> **Verdict:** CONTRADICTS (high confidence)
>
> **Rationale:** "Multiple randomized controlled trials demonstrate superior glycemic control with GLP-1 receptor agonists compared to metformin. A 2023 meta-analysis showed consistent HbA1c reductions across all studies (p<0.001)."

#### Supports
The counter-evidence **supports** the original statement when:
- The search failed to find contradictory evidence
- Found studies actually confirm the original claim
- The counter-claim lacks literature support

**Example:**
> **Original:** "Regular exercise improves cardiovascular health"
>
> **Verdict:** SUPPORTS (high confidence)
>
> **Rationale:** "The counter-evidence search found no studies contradicting this claim. All identified literature supports the cardiovascular benefits of regular exercise."

#### Undecided
The evidence is **undecided** when:
- Some evidence supports and some contradicts
- Too few studies available for conclusions
- Studies have significant limitations
- Evidence is only tangentially related

**Example:**
> **Original:** "Vitamin D supplementation prevents fractures in elderly patients"
>
> **Verdict:** UNDECIDED (low confidence)
>
> **Rationale:** "Evidence is mixed with some studies showing benefit and others showing no effect. Study populations and dosing protocols varied significantly."

### Confidence Levels

Each verdict includes a confidence level:

| Level | Meaning | When Assigned |
|-------|---------|---------------|
| **High** | Strong, reliable evidence | Multiple high-quality studies, consistent results |
| **Medium** | Moderate evidence | Good studies with some limitations or minor inconsistencies |
| **Low** | Weak or uncertain | Few studies, significant limitations, conflicting results |

## Interpreting Results

### Overall Assessment

After analyzing all statements from an abstract, PaperChecker provides an overall assessment summarizing the findings:

**All Statements Supported:**
> "All 2 statement(s) from the original abstract were supported by the literature search with high confidence. No contradictory evidence was found, suggesting the claims are well-supported by existing research."

**All Statements Contradicted:**
> "All 2 statement(s) from the original abstract were contradicted by evidence found in the literature with high confidence. Significant counter-evidence exists that challenges these claims."

**Mixed Results:**
> "Mixed results across 3 statements: 1 supported by literature, 1 contradicted, 1 undecided or with insufficient evidence. The abstract contains claims with varying levels of literature support."

### What Verdicts Mean for Your Research

| Verdict | Interpretation | Recommended Action |
|---------|----------------|-------------------|
| **Contradicts** (high) | Strong evidence against the claim | Review the counter-evidence carefully; consider revising claims |
| **Contradicts** (medium/low) | Some contrary evidence exists | Acknowledge limitations; investigate further |
| **Supports** (any) | No contradictory evidence found | Claim appears consistent with literature |
| **Undecided** (any) | Evidence is insufficient | More research may be needed; be cautious about strong claims |

## Example Output

### JSON Output Format

```json
{
  "verdict": "contradicts",
  "confidence": "high",
  "rationale": "Multiple high-quality RCTs demonstrate superior glycemic control with GLP-1 agonists compared to metformin. The meta-analysis shows consistent results (p<0.001)."
}
```

### Markdown Report Format

```markdown
### Statement 1

**Claim:** Metformin is superior to GLP-1 agonists for glycemic control

**Type:** finding

**Verdict:** CONTRADICTS

**Confidence:** high

**Rationale:** Multiple high-quality RCTs demonstrate superior glycemic control with GLP-1 agonists compared to metformin. The meta-analysis shows consistent results (p<0.001).

## Counter-Evidence Summary

Evidence from several randomized controlled trials contradicts this claim...

## References

1. Smith J, Johnson A. GLP-1 vs Metformin study. JAMA. 2023;329(5):401-410. [PMID: 12345678]
```

## Important Considerations

### What Verdict Analysis Does
- Evaluates counter-evidence objectively
- Bases conclusions only on found literature
- Considers both quantity and quality of evidence
- Provides transparent rationale

### What Verdict Analysis Does NOT Do
- Replace expert human review
- Add external knowledge beyond found citations
- Make absolute determinations of truth
- Guarantee complete literature coverage

### Limitations to Keep in Mind

1. **Database Coverage**: Verdicts are limited by what's in the literature database
2. **Search Effectiveness**: Counter-evidence search may miss relevant studies
3. **LLM Interpretation**: AI-based analysis may have biases
4. **Recency**: Very recent publications may not be indexed

## Best Practices

### For Researchers
1. **Review Rationales**: Always read the rationale, not just the verdict
2. **Check Citations**: Verify the cited evidence supports the verdict
3. **Consider Confidence**: Low confidence verdicts warrant extra scrutiny
4. **Don't Over-rely**: Use verdicts as guidance, not absolute truth

### For Research Quality Assessment
1. **Pattern Recognition**: Multiple "contradicts" verdicts suggest concerns
2. **Confidence Distribution**: Many "low" confidence verdicts indicate uncertain areas
3. **Statement Types**: Pay attention to contradicted "findings" vs "hypotheses"

## Troubleshooting

### Common Issues

**"Undecided" verdict when evidence seems clear:**
- Check if citations directly address the claim
- Evidence may be tangentially related
- Database may lack relevant studies

**Low confidence despite many citations:**
- Studies may have limitations
- Results may be inconsistent
- Evidence may not directly address the claim

**Unexpected "supports" verdict:**
- Counter-evidence search genuinely found no contradictions
- Original claim may be well-established
- Search terms may need refinement

## Related Guides

- [PaperChecker Overview](paperchecker_overview.md)
- [Understanding Search Results](paperchecker_search_guide.md)
- [Counter-Report Interpretation](paperchecker_report_guide.md)
