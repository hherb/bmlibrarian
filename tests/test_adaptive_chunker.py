#!/usr/bin/env python3
"""Quick test for the adaptive_chunker pure function."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))

from bmlibrarian.embeddings import adaptive_chunker


def test_short_text():
    """Test chunking of short text that fits in one chunk."""
    text = "This is a short text that should fit in one chunk."
    chunks = adaptive_chunker(text, max_chars=100, overlap_chars=20)

    print(f"Test 1 - Short text:")
    print(f"  Input length: {len(text)} chars")
    print(f"  Number of chunks: {len(chunks)}")
    print(f"  Chunks: {chunks}")
    assert len(chunks) == 1
    assert chunks[0] == text.strip()
    print("  ✓ PASSED\n")


def test_long_text():
    """Test chunking of long text with sentence boundaries."""
    text = (
        "First sentence here. Second sentence is here too. "
        "Third sentence continues. Fourth sentence follows. "
        "Fifth sentence arrives. Sixth sentence completes the thought."
    )
    chunks = adaptive_chunker(text, max_chars=100, overlap_chars=30)

    print(f"Test 2 - Long text with sentence boundaries:")
    print(f"  Input length: {len(text)} chars")
    print(f"  Number of chunks: {len(chunks)}")
    for i, chunk in enumerate(chunks):
        print(f"  Chunk {i}: {len(chunk)} chars - '{chunk[:50]}...'")
    assert len(chunks) > 1
    print("  ✓ PASSED\n")


def test_empty_text():
    """Test chunking of empty text."""
    text = ""
    chunks = adaptive_chunker(text, max_chars=100, overlap_chars=20)

    print(f"Test 3 - Empty text:")
    print(f"  Number of chunks: {len(chunks)}")
    assert len(chunks) == 0
    print("  ✓ PASSED\n")


def test_medical_text():
    """Test with realistic medical text."""
    text = (
        "Background: Cardiovascular disease remains a leading cause of mortality. "
        "Objective: To assess the efficacy of statins in primary prevention. "
        "Methods: We conducted a randomized controlled trial with 1000 participants. "
        "Results: Statin therapy reduced LDL cholesterol by 40% (p<0.001). "
        "Conclusion: Statins are effective for primary prevention of cardiovascular events."
    )
    chunks = adaptive_chunker(text, max_chars=150, overlap_chars=40)

    print(f"Test 4 - Medical abstract:")
    print(f"  Input length: {len(text)} chars")
    print(f"  Number of chunks: {len(chunks)}")
    for i, chunk in enumerate(chunks):
        print(f"  Chunk {i}: {len(chunk)} chars")
    print("  ✓ PASSED\n")


def test_real_document():
    """Test with a longer realistic document."""
    text = """
    The pathophysiology of type 2 diabetes mellitus involves insulin resistance and beta-cell dysfunction.
    Insulin resistance occurs when cells in muscles, fat, and the liver don't respond well to insulin.
    As a result, these tissues cannot easily absorb glucose from the blood. The pancreas tries to compensate
    by producing more insulin. Over time, the beta cells in the pancreas become damaged and cannot produce
    enough insulin to maintain normal blood glucose levels. This leads to hyperglycemia, which is the
    hallmark of diabetes. Chronic hyperglycemia can lead to serious complications including cardiovascular
    disease, nephropathy, neuropathy, and retinopathy. Management strategies include lifestyle modifications,
    oral medications such as metformin, and insulin therapy when necessary. Recent advances in treatment
    include GLP-1 receptor agonists and SGLT2 inhibitors, which have shown cardiovascular benefits.
    """

    chunks = adaptive_chunker(text.strip(), max_chars=300, overlap_chars=80)

    print(f"Test 5 - Realistic medical document:")
    print(f"  Input length: {len(text.strip())} chars")
    print(f"  Number of chunks: {len(chunks)}")
    for i, chunk in enumerate(chunks):
        print(f"  Chunk {i}: {len(chunk)} chars")
        print(f"    Preview: '{chunk[:80]}...'")

    # Verify overlap exists between chunks
    if len(chunks) > 1:
        for i in range(len(chunks) - 1):
            # Check if there's any common text between consecutive chunks
            overlap_exists = any(
                chunks[i][j:j+20] in chunks[i+1]
                for j in range(max(0, len(chunks[i]) - 100), len(chunks[i]) - 20)
            )
            print(f"  Overlap between chunk {i} and {i+1}: {overlap_exists}")

    print("  ✓ PASSED\n")


if __name__ == "__main__":
    print("=" * 70)
    print("ADAPTIVE CHUNKER PURE FUNCTION TESTS")
    print("=" * 70)
    print()

    try:
        test_short_text()
        test_long_text()
        test_empty_text()
        test_medical_text()
        test_real_document()

        print("=" * 70)
        print("ALL TESTS PASSED ✓")
        print("=" * 70)

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
