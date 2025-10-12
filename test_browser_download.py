#!/usr/bin/env python3
"""Quick test script for browser-based PDF downloader."""

import sys
import logging
from pathlib import Path

# Add src directory to path
src_path = Path(__file__).parent / 'src'
sys.path.insert(0, str(src_path))

from bmlibrarian.utils.browser_downloader import download_pdf_with_browser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_simple_pdf():
    """Test downloading a simple PDF (no Cloudflare)."""
    print("=" * 70)
    print("Test 1: Simple PDF Download")
    print("=" * 70)

    # Test with a direct PDF link (W3C specification)
    test_url = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
    test_path = Path("/tmp/test_simple.pdf")

    print(f"URL: {test_url}")
    print(f"Save to: {test_path}")
    print()

    result = download_pdf_with_browser(
        url=test_url,
        save_path=test_path,
        headless=True,
        timeout=30000
    )

    print(f"Result: {result['status']}")
    if result['status'] == 'success':
        print(f"✓ Downloaded: {result['path']}")
        print(f"  Size: {result['size']:,} bytes")

        # Verify file exists and is PDF
        if test_path.exists():
            with open(test_path, 'rb') as f:
                magic = f.read(4)
                is_pdf = magic == b'%PDF'
                print(f"  Valid PDF: {is_pdf}")

            # Clean up
            test_path.unlink()
            print("  Test file deleted")
    else:
        print(f"✗ Failed: {result.get('error', 'Unknown error')}")

    print()


def test_cloudflare_protected():
    """Test downloading from a Cloudflare-protected site."""
    print("=" * 70)
    print("Test 2: Cloudflare-Protected Site")
    print("=" * 70)
    print("Note: This test requires a real Cloudflare-protected URL")
    print("      Provide one as command line argument to test")
    print()

    if len(sys.argv) > 1:
        test_url = sys.argv[1]
        test_path = Path("/tmp/test_cloudflare.pdf")

        print(f"URL: {test_url}")
        print(f"Save to: {test_path}")
        print()

        result = download_pdf_with_browser(
            url=test_url,
            save_path=test_path,
            headless=True,
            timeout=60000
        )

        print(f"Result: {result['status']}")
        if result['status'] == 'success':
            print(f"✓ Downloaded: {result['path']}")
            print(f"  Size: {result['size']:,} bytes")

            if test_path.exists():
                print(f"  File exists: {test_path.exists()}")
                print(f"  File size: {test_path.stat().st_size:,} bytes")
                test_path.unlink()
                print("  Test file deleted")
        else:
            print(f"✗ Failed: {result.get('error', 'Unknown error')}")
    else:
        print("Skipped (no URL provided)")

    print()


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("Browser Downloader Test Suite")
    print("=" * 70)
    print()

    try:
        # Check if playwright is installed
        import playwright
        print("✓ Playwright installed")
    except ImportError:
        print("✗ Playwright not installed")
        print("\nInstall with:")
        print("  uv add playwright")
        print("  uv run python -m playwright install chromium")
        sys.exit(1)

    print()

    # Run tests
    test_simple_pdf()
    test_cloudflare_protected()

    print("=" * 70)
    print("Tests completed")
    print("=" * 70)


if __name__ == "__main__":
    main()
