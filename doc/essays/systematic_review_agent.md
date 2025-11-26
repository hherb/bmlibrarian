# Toward AI-Assisted Systematic Literature Review: An Open Collaboration

*A call for collaboration on BMLibrarian's SystematicReviewAgent*

## The Problem We All Know Too Well

If you've ever conducted a systematic review, you know the burden. The average systematic review takes 67 weeks from registration to publication, with the literature search and screening phases consuming a substantial portion of that time. A single reviewer screening 1,000 abstracts—a modest number for many clinical topics—faces days of concentrated work just to reach the full-text review stage.

And yet, despite this investment, we miss relevant papers. We exclude papers we shouldn't. We disagree with our co-reviewers on borderline cases. The process is simultaneously exhausting and error-prone.

The consequence is not merely inconvenience. Systematic reviews inform clinical guidelines, shape research priorities, and influence patient care. When we miss a relevant study—particularly one that contradicts the prevailing evidence—we risk perpetuating incomplete or biased conclusions.

## What If We Had a Tireless Research Assistant?

BMLibrarian's **SystematicReviewAgent** is an attempt to address this challenge. Not to replace human judgment—systematic reviews are too important for that—but to augment it. Not to support academic laziness, but to improve productivity and efficiency and ease the tedium aspects of scientific rigor. To handle the mechanical burden of searching, screening, and organizing while preserving human oversight where it matters most.

The agent accepts what any systematic review begins with:
- A research question
- Inclusion and exclusion criteria (the system can assist you with suggestions)
- The types of studies you're looking for

From there, it does what would take a human team weeks:

1. **Generates diverse search strategies** using both semantic understanding and traditional keyword approaches
2. **Screens thousands of abstracts** against your criteria, documenting every decision
3. **Assesses study quality** using established frameworks (study design classification, risk of bias, PICO extraction, PRISMA compliance for included reviews)
4. **Produces a ranked list** of papers with full rationale for every inclusion and exclusion

The key word is *rationale*. Every decision is documented. Every excluded paper includes an explanation. The output is not a black box but an auditable trail that a human reviewer can verify, challenge, and refine.

## How It Works

The agent operates with what we call "checkpoint-based autonomy." It does not run unsupervised from start to finish. Instead, it pauses at critical decision points:

- After generating its search strategy (before executing queries)
- After initial screening (before detailed quality assessment)
- After quality evaluation (before final ranking)

At each checkpoint, you can review what the agent has done, adjust its approach, or override its decisions. Think of it as a very capable research assistant that checks in before making major commitments.

The underlying technology combines large language models with structured biomedical knowledge. The agent doesn't merely pattern-match keywords—it understands that "myocardial infarction" and "heart attack" refer to the same condition, that an RCT carries different evidential weight than a case series, that a study's sample size and follow-up duration matter for interpreting its findings.

## Why We Need Your Help

Building the agent is one challenge. Validating it is another—and arguably more important.

We need collaborators who can help us answer the essential question: *Does this actually work?*

Specifically, we are seeking:

### Benchmark Contributions
If you have conducted a systematic review with a well-documented search strategy and final paper list, your data could serve as a gold standard for validation. We would run our agent against your original research question and criteria, then measure how well it reproduces your findings.

We are particularly interested in:
- Cochrane reviews with published search strategies
- Systematic reviews in any biomedical domain with clear inclusion/exclusion criteria
- Reviews where the full list of screened and included papers is available

### Domain Expertise for Edge Case Analysis
The hardest papers to classify are the borderline cases—studies that partially meet inclusion criteria, or where the relevance depends on nuanced interpretation. We need domain experts who can review the agent's decisions on difficult cases and help us understand where it succeeds and fails.

### Validation Across Specialties
Medicine is not monolithic. A search strategy that works for cardiovascular outcomes may fail for rare diseases or surgical interventions. We need collaborators across specialties to test the agent's generalizability.

### Critical Feedback
We are not looking for cheerleaders. We need collaborators who will find the failures, identify the blind spots, and push back when the approach falls short. The goal is a tool that actually helps researchers, not one that merely appears impressive in demonstrations.

## What We Offer in Return

This is an open-source project. Contributors will:
- Have early access to the tool as it develops
- Be acknowledged in any resulting publications
- Help shape the direction of development based on real-world needs
- Gain a tool that, if successful, could save them significant time in future reviews

We are also open to formal research collaborations. If your institution is interested in a more structured partnership—including co-authorship on validation studies—we welcome that conversation.

## The Larger Vision

The SystematicReviewAgent is part of BMLibrarian, a broader effort to make biomedical literature more accessible through AI assistance. The project includes tools for:

- Sophisticated search strategies (semantic, expanded keywords, re-ranking …) across millions of abstracts
- Automated quality assessment of individual studies by generally accepted and transparent criteria
- Citation extraction and evidence synthesis (with full audit trail of provenance and rationale)
- Fact-checking claims against the literature

All of this is built on a foundation of local, privacy-preserving AI. Your queries and documents never leave your infrastructure. The models run on your own hardware, using your institution's literature database.

## How to Get Involved

If you're interested in contributing, we want to hear from you:

1. **Share a benchmark dataset**: If you have a completed systematic review with documented methodology, contact us about using it for validation.

2. **Test the tool**: Once we reach the validation phase, we'll need researchers willing to run the agent on real research questions and report their experience.

3. **Provide domain expertise**: If you're willing to review the agent's decisions on papers in your specialty, that expertise is invaluable.

4. **Contribute code**: If you're technically inclined, the project is open source and welcomes contributions.

The project repository is at: **github.com/hherb/bmlibrarian**

For collaboration inquiries, open an issue on GitHub or reach out through the repository's discussion forum.

## Closing Thoughts

Systematic reviews are the backbone of evidence-based medicine. They're also a bottleneck—too slow, too labor-intensive, and too often out of date by the time they're published.

We don't claim to have solved this problem. What we have is a prototype (presenty > 120,000 lines of well documented and mostly tested) and a detaild implementation plan. The prototype shows promise, but promise is not proof. That's why we're writing this: to find the collaborators who can help us move from promising to proven.

If you've ever wished for a better way to conduct systematic reviews—or if you're skeptical that AI can help and want to see it tested rigorously—we'd like to work with you.

The literature isn't getting any smaller. Let's build tools that help us make sense of it.

---

*BMLibrarian is an open-source project focused on AI-assisted biomedical literature analysis. The SystematicReviewAgent is currently in the planning phase, with implementation expected to proceed through 2025/mid 2026. For technical details, see the planning documentation in the project repository.*
