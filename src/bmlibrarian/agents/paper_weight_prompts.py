"""
Paper Weight Assessment Prompts

LLM prompts for methodological quality and risk of bias assessment.
Separated from the assessor logic for maintainability.
"""


def build_methodological_quality_prompt(text: str) -> str:
    """
    Build prompt for methodological quality assessment.

    Args:
        text: Prepared document text

    Returns:
        Prompt string for LLM
    """
    return f"""You are an expert in biomedical research methodology. Analyze the following research paper and assess its methodological quality across six components.

PAPER TEXT:
{text}

TASK:
Analyze the methodological quality and provide assessments for each component:

1. RANDOMIZATION (0-2 points):
   - 0: No randomization or inadequate sequence generation
   - 1: Randomization mentioned but method unclear
   - 2: Proper random sequence generation (e.g., computer-generated, random number table)

2. BLINDING (0-3 points):
   - 0: No blinding
   - 1: Single-blind (participants OR assessors)
   - 2: Double-blind (participants AND assessors)
   - 3: Triple-blind (participants, assessors, AND data analysts)

3. ALLOCATION CONCEALMENT (0-1.5 points):
   - 0: No allocation concealment or inadequate
   - 0.75: Unclear or partially described
   - 1.5: Proper allocation concealment (e.g., sealed envelopes, central randomization)

4. PROTOCOL PREREGISTRATION (0-1.5 points):
   - 0: No protocol registration mentioned
   - 0.75: Protocol mentioned but not verified
   - 1.5: Protocol clearly registered before study (e.g., ClinicalTrials.gov, registry number provided)

5. ITT ANALYSIS (0-1 points):
   - 0: No ITT analysis or per-protocol only
   - 0.5: Modified ITT or unclear
   - 1: Clear intention-to-treat analysis

6. ATTRITION HANDLING (0-1 points):
   - Extract dropout/attrition rate
   - Assess quality of handling (imputation methods, sensitivity analysis)
   - Score based on rate and handling quality

OUTPUT FORMAT (JSON):
{{
  "randomization": {{
    "score": <0-2>,
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "blinding": {{
    "score": <0-3>,
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "allocation_concealment": {{
    "score": <0-1.5>,
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "protocol_preregistration": {{
    "score": <0-1.5>,
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "itt_analysis": {{
    "score": <0-1>,
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "attrition_handling": {{
    "score": <0-1>,
    "attrition_rate": <decimal or null>,
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }}
}}

CRITICAL REQUIREMENTS:
- Extract ONLY information that is ACTUALLY PRESENT in the text
- DO NOT invent, assume, or fabricate any information
- If information is unclear or not mentioned, score it as 0 and explain why
- Be specific and evidence-based in your assessment
- Provide exact quotes from the paper as evidence when available

Provide ONLY the JSON output, no additional text."""


def build_risk_of_bias_prompt(text: str) -> str:
    """
    Build prompt for risk of bias assessment.

    Args:
        text: Prepared document text

    Returns:
        Prompt string for LLM
    """
    return f"""You are an expert in biomedical research methodology and bias assessment. Analyze the following research paper and assess its risk of bias across four domains.

PAPER TEXT:
{text}

TASK:
Assess risk of bias using INVERTED SCALE (higher score = lower risk of bias):

1. SELECTION BIAS (0-2.5 points):
   - 0: High risk (convenience sampling, no clear criteria)
   - 1.25: Moderate risk (some limitations in sampling)
   - 2.5: Low risk (random/consecutive sampling, clear inclusion/exclusion criteria)

2. PERFORMANCE BIAS (0-2.5 points):
   - 0: High risk (no blinding, unstandardized interventions)
   - 1.25: Moderate risk (partial blinding or standardization)
   - 2.5: Low risk (proper blinding, standardized protocols)

3. DETECTION BIAS (0-2.5 points):
   - 0: High risk (unblinded outcome assessment)
   - 1.25: Moderate risk (partially blinded or objective outcomes only)
   - 2.5: Low risk (blinded outcome assessment for all outcomes)

4. REPORTING BIAS (0-2.5 points):
   - 0: High risk (selective reporting, outcomes not pre-specified)
   - 1.25: Moderate risk (some evidence of selective reporting)
   - 2.5: Low risk (all pre-specified outcomes reported, protocol available)

OUTPUT FORMAT (JSON):
{{
  "selection_bias": {{
    "score": <0-2.5>,
    "risk_level": "<high|moderate|low>",
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "performance_bias": {{
    "score": <0-2.5>,
    "risk_level": "<high|moderate|low>",
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "detection_bias": {{
    "score": <0-2.5>,
    "risk_level": "<high|moderate|low>",
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "reporting_bias": {{
    "score": <0-2.5>,
    "risk_level": "<high|moderate|low>",
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }}
}}

CRITICAL REQUIREMENTS:
- Extract ONLY information that is ACTUALLY PRESENT in the text
- DO NOT invent, assume, or fabricate any information
- If information is unclear or not mentioned, assume high risk (score 0) and explain why
- Be specific and evidence-based in your assessment
- Provide exact quotes from the paper as evidence when available

Provide ONLY the JSON output, no additional text."""


__all__ = [
    'build_methodological_quality_prompt',
    'build_risk_of_bias_prompt',
]
