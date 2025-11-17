"""OpenAthens Authentication Demo

Demonstrates how to use OpenAthens proxy authentication for accessing
paywalled journal articles through institutional subscriptions.
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.bmlibrarian.utils.openathens_auth import OpenAthensAuth, create_openathens_auth
from src.bmlibrarian.utils.pdf_manager import PDFManager
from src.bmlibrarian.config import get_openathens_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def demo_basic_auth():
    """Demo: Basic OpenAthens authentication."""
    print("\n" + "="*80)
    print("DEMO 1: Basic OpenAthens Authentication")
    print("="*80 + "\n")

    # Create authenticator
    # NOTE: Replace with your actual institution URL
    auth = OpenAthensAuth(
        institution_url="https://yourinstitution.openathens.net",
        headless=False  # Show browser for 2FA
    )

    # Check if already authenticated
    if auth.is_authenticated():
        print("✅ Already authenticated!")
        print(f"Session info: {auth.get_session_info()}")
    else:
        print("Not authenticated, please login...")
        print("Browser will open for you to complete login (including 2FA)")

        # Perform login
        if auth.login_sync(wait_for_login=300):  # 5 minute timeout
            print("\n✅ Login successful!")
            print(f"Session info: {auth.get_session_info()}")
        else:
            print("\n❌ Login failed")
            return

    # Construct proxy URL for accessing a journal article
    original_url = "https://www.nature.com/articles/s41586-024-example.pdf"
    proxy_url = auth.construct_proxy_url(original_url)

    print(f"\nOriginal URL: {original_url}")
    print(f"Proxy URL: {proxy_url}")


def demo_pdf_manager_integration():
    """Demo: Using OpenAthens with PDFManager."""
    print("\n" + "="*80)
    print("DEMO 2: PDFManager with OpenAthens Integration")
    print("="*80 + "\n")

    # Create PDF manager with OpenAthens configuration
    openathens_config = {
        'enabled': True,
        'institution_url': 'https://yourinstitution.openathens.net',  # Replace with your URL
        'session_timeout_hours': 24,
        'auto_login': True,  # Automatically login if session expired
        'login_timeout': 300,  # 5 minute timeout
        'headless': False  # Show browser for 2FA
    }

    pdf_manager = PDFManager(
        base_dir="~/knowledgebase/pdf",
        openathens_config=openathens_config
    )

    # Check OpenAthens status
    status = pdf_manager.get_openathens_status()
    print(f"OpenAthens status: {status}")

    if not status.get('authenticated'):
        print("\n⚠️ Not authenticated - browser will open for login")
        if not pdf_manager.login_openathens():
            print("❌ Login failed")
            return

    # Example: Download a PDF using OpenAthens proxy
    document = {
        'id': 12345,
        'title': 'Example Paper',
        'pdf_url': 'https://www.nature.com/articles/s41586-024-example.pdf',
        'doi': '10.1038/s41586-024-example',
        'publication_date': '2024-01-01'
    }

    print(f"\nAttempting to download: {document['title']}")
    print(f"URL: {document['pdf_url']}")

    # Download will automatically use OpenAthens proxy
    pdf_path = pdf_manager.download_pdf(document)

    if pdf_path:
        print(f"\n✅ PDF downloaded successfully to: {pdf_path}")
    else:
        print("\n❌ PDF download failed")


def demo_config_file():
    """Demo: Using OpenAthens with configuration file."""
    print("\n" + "="*80)
    print("DEMO 3: Using OpenAthens from config.json")
    print("="*80 + "\n")

    # Load OpenAthens config from ~/.bmlibrarian/config.json
    # First, you need to edit your config.json:
    # {
    #   "openathens": {
    #     "enabled": true,
    #     "institution_url": "https://yourinstitution.openathens.net",
    #     "session_timeout_hours": 24,
    #     "auto_login": true,
    #     "login_timeout": 300,
    #     "headless": false
    #   }
    # }

    openathens_config = get_openathens_config()
    print(f"Loaded config: {openathens_config}")

    if not openathens_config.get('enabled'):
        print("\n⚠️ OpenAthens is disabled in config.json")
        print("Edit ~/.bmlibrarian/config.json to enable it")
        return

    # Create PDF manager using config
    pdf_manager = PDFManager(openathens_config=openathens_config)

    status = pdf_manager.get_openathens_status()
    print(f"\nOpenAthens status: {status}")

    if status.get('authenticated'):
        print("\n✅ Ready to download PDFs with OpenAthens proxy!")
    else:
        print("\n⚠️ Not authenticated yet")


def demo_session_management():
    """Demo: OpenAthens session management."""
    print("\n" + "="*80)
    print("DEMO 4: OpenAthens Session Management")
    print("="*80 + "\n")

    auth = create_openathens_auth(
        institution_url="https://yourinstitution.openathens.net",
        auto_login=False  # Don't auto-login for this demo
    )

    # Get session info
    info = auth.get_session_info()
    print(f"Session info: {info}")

    if info.get('authenticated'):
        print(f"\n✅ Authenticated")
        print(f"Created: {info.get('created_at')}")
        print(f"Expires: {info.get('expires_at')}")
        print(f"Time remaining: {info.get('time_remaining_hours'):.1f} hours")
        print(f"Cookies: {info.get('cookie_count')}")

        # Session is stored at: ~/.bmlibrarian/openathens_session.pkl
        print(f"\nSession file: ~/.bmlibrarian/openathens_session.pkl")

        # Clear session if needed
        choice = input("\nClear session? (y/n): ")
        if choice.lower() == 'y':
            auth.clear_session()
            print("✅ Session cleared")
    else:
        print("\n⚠️ No active session")
        print("Run with auto_login=True to authenticate")


def main():
    """Run all demos."""
    print("\n" + "="*80)
    print("OpenAthens Authentication Demo")
    print("="*80)

    print("\nAvailable demos:")
    print("1. Basic OpenAthens authentication")
    print("2. PDFManager with OpenAthens integration")
    print("3. Using OpenAthens from config.json")
    print("4. Session management")
    print("5. Run all demos")

    try:
        choice = input("\nSelect demo (1-5): ").strip()

        if choice == '1':
            demo_basic_auth()
        elif choice == '2':
            demo_pdf_manager_integration()
        elif choice == '3':
            demo_config_file()
        elif choice == '4':
            demo_session_management()
        elif choice == '5':
            demo_basic_auth()
            demo_pdf_manager_integration()
            demo_config_file()
            demo_session_management()
        else:
            print("Invalid choice")

        print("\n" + "="*80)
        print("Demo completed!")
        print("="*80 + "\n")

    except KeyboardInterrupt:
        print("\n\nDemo interrupted")
    except Exception as e:
        logger.error(f"Demo failed: {e}", exc_info=True)


if __name__ == "__main__":
    main()
