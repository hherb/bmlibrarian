# OpenAthens API Migration Guide

This guide helps you migrate from the old OpenAthens API (v0.9.x) to the new secure API (v1.0+).

## What Changed?

The OpenAthens authentication module was completely rewritten to address critical security vulnerabilities and improve code quality:

### Security Improvements
- ✅ **Eliminated pickle vulnerability**: Replaced pickle with JSON serialization
- ✅ **File permissions**: Session files now created with 600 permissions (owner-only)
- ✅ **HTTPS enforcement**: Institution URLs must use HTTPS
- ✅ **Configurable parameters**: No more magic numbers, everything configurable
- ✅ **Network checks**: Pre-authentication connectivity validation
- ✅ **Session caching**: Performance optimization with TTL-based caching

### API Changes
- ✅ **Separated configuration**: New `OpenAthensConfig` class
- ✅ **Renamed methods**: `login()` → `login_interactive()`
- ✅ **Updated PDFManager**: Changed parameter names and structure

## Backward Compatibility

**Good news**: The old API still works with deprecation warnings. You can migrate gradually.

## Migration Path

### Option 1: Quick Migration (Recommended)

Update your code to use the new secure API:

#### Before (Old API - Deprecated)
```python
from bmlibrarian.utils.openathens_auth import OpenAthensAuth
from bmlibrarian.utils.pdf_manager import PDFManager

# Old way - still works but deprecated
auth = OpenAthensAuth(
    institution_url='https://institution.openathens.net/login',
    session_timeout_hours=24,
    headless=True
)

# Old PDFManager initialization
pdf_manager = PDFManager(
    openathens_config={
        'enabled': True,
        'institution_url': 'https://institution.openathens.net/login',
        'session_timeout_hours': 24
    }
)
```

#### After (New API - Secure)
```python
from bmlibrarian.utils.openathens_auth import OpenAthensConfig, OpenAthensAuth
from bmlibrarian.utils.pdf_manager import PDFManager

# New way - secure and recommended
config = OpenAthensConfig(
    institution_url='https://institution.openathens.net/login',
    session_max_age_hours=24,  # Renamed from session_timeout_hours
    headless=True,
    session_cache_ttl=60  # New: performance optimization
)

auth = OpenAthensAuth(config=config)

# New PDFManager initialization
pdf_manager = PDFManager(openathens_auth=auth)
```

### Option 2: Gradual Migration

Keep using the old API temporarily while you plan your migration:

```python
# This still works but shows deprecation warnings
from bmlibrarian.utils.openathens_auth import OpenAthensAuth
import warnings

# Suppress warnings temporarily (not recommended long-term)
with warnings.catch_warnings():
    warnings.filterwarnings('ignore', category=DeprecationWarning)
    auth = OpenAthensAuth(
        institution_url='https://institution.openathens.net/login',
        session_timeout_hours=24
    )
```

## Detailed Migration Steps

### Step 1: Update OpenAthensAuth Initialization

**Old Code**:
```python
auth = OpenAthensAuth(
    institution_url='https://institution.openathens.net/login',
    session_timeout_hours=24,
    headless=True
)
```

**New Code**:
```python
from bmlibrarian.utils.openathens_auth import OpenAthensConfig, OpenAthensAuth

config = OpenAthensConfig(
    institution_url='https://institution.openathens.net/login',
    session_max_age_hours=24,
    headless=True,
    # New optional parameters:
    auth_check_interval=1.0,  # Polling interval for auth checks
    cloudflare_wait=30,        # Max wait for Cloudflare
    page_timeout=60000,        # Page load timeout in ms
    session_cache_ttl=60       # Session validation cache TTL
)

auth = OpenAthensAuth(config=config)
```

### Step 2: Update Login Method Calls

**Old Code**:
```python
import asyncio

success = asyncio.run(auth.login(wait_for_login=300))
```

**New Code**:
```python
import asyncio

# Method renamed to login_interactive()
success = asyncio.run(auth.login_interactive())

# Note: wait_for_login parameter removed, uses configured timeouts
```

**Backward Compatibility**: The old `login()` method still exists as an alias but shows a deprecation warning.

### Step 3: Update PDFManager Initialization

**Old Code**:
```python
pdf_manager = PDFManager(
    base_dir='/path/to/pdfs',
    db_conn=conn,
    openathens_config={
        'enabled': True,
        'institution_url': 'https://institution.openathens.net/login',
        'session_timeout_hours': 24,
        'auto_login': True
    }
)
```

**New Code**:
```python
from bmlibrarian.utils.openathens_auth import OpenAthensConfig, OpenAthensAuth

# Create auth instance separately
config = OpenAthensConfig(
    institution_url='https://institution.openathens.net/login',
    session_max_age_hours=24
)
auth = OpenAthensAuth(config=config)

# Pass auth instance to PDFManager
pdf_manager = PDFManager(
    base_dir='/path/to/pdfs',
    db_conn=conn,
    openathens_auth=auth  # Changed from openathens_config dict
)
```

### Step 4: Update Session File Handling

**Old Behavior**:
- Session files: `~/.bmlibrarian/openathens_session.pkl`
- Format: Pickle (security risk)
- Permissions: Not enforced

**New Behavior**:
- Session files: `~/.bmlibrarian/openathens_session.json`
- Format: JSON (secure)
- Permissions: 600 (owner read/write only)

**Migration**: Old `.pkl` files won't be automatically migrated. You'll need to re-authenticate:

```bash
# Remove old pickle session file
rm ~/.bmlibrarian/openathens_session.pkl

# Re-authenticate with new JSON format
# (happens automatically on first login_interactive() call)
```

### Step 5: Update Configuration Files

If you have configuration files that reference OpenAthens:

**Old Config** (`config.json`):
```json
{
  "pdf_manager": {
    "openathens": {
      "enabled": true,
      "institution_url": "https://institution.openathens.net/login",
      "session_timeout_hours": 24,
      "headless": true
    }
  }
}
```

**New Config** (`config.json`):
```json
{
  "openathens": {
    "institution_url": "https://institution.openathens.net/login",
    "session_max_age_hours": 24,
    "headless": true,
    "auth_check_interval": 1.0,
    "cloudflare_wait": 30,
    "page_timeout": 60000,
    "session_cache_ttl": 60
  }
}
```

Then in code:
```python
import json
from bmlibrarian.utils.openathens_auth import OpenAthensConfig, OpenAthensAuth

with open('config.json') as f:
    config_data = json.load(f)

config = OpenAthensConfig(**config_data['openathens'])
auth = OpenAthensAuth(config=config)
```

## Complete Example Migration

### Before (v0.9.x)

```python
from bmlibrarian.utils.openathens_auth import OpenAthensAuth
from bmlibrarian.utils.pdf_manager import PDFManager
import asyncio

# Old API - all parameters passed directly
auth = OpenAthensAuth(
    institution_url='https://institution.openathens.net/login',
    session_timeout_hours=24,
    headless=False  # For 2FA visibility
)

# Old login method
if not auth.is_authenticated():
    success = asyncio.run(auth.login(wait_for_login=300))
    if not success:
        print("Login failed")
        exit(1)

# Old PDFManager with dict config
pdf_manager = PDFManager(
    base_dir='~/pdfs',
    openathens_config={
        'enabled': True,
        'institution_url': 'https://institution.openathens.net/login',
        'session_timeout_hours': 24,
        'auto_login': True
    }
)

# Download with authentication
pdf_path = pdf_manager.download_pdf(document)
```

### After (v1.0+)

```python
from bmlibrarian.utils.openathens_auth import OpenAthensConfig, OpenAthensAuth
from bmlibrarian.utils.pdf_manager import PDFManager
import asyncio

# New API - configuration object
config = OpenAthensConfig(
    institution_url='https://institution.openathens.net/login',
    session_max_age_hours=24,
    headless=False,  # For 2FA visibility
    session_cache_ttl=60  # Performance optimization
)

auth = OpenAthensAuth(config=config)

# New login method
if not auth.is_authenticated():
    success = asyncio.run(auth.login_interactive())
    if not success:
        print("Login failed")
        exit(1)

# New PDFManager with auth instance
pdf_manager = PDFManager(
    base_dir='~/pdfs',
    openathens_auth=auth  # Pass auth instance
)

# Download with authentication (same as before)
pdf_path = pdf_manager.download_pdf(document)
```

## Breaking Changes (Summary)

| Component | Old API | New API | Backward Compatible? |
|-----------|---------|---------|----------------------|
| OpenAthensAuth init | `institution_url` param | `config` param | ✅ Yes (with warning) |
| Login method | `.login()` | `.login_interactive()` | ✅ Yes (alias exists) |
| PDFManager init | `openathens_config` dict | `openathens_auth` instance | ✅ Yes (with warning) |
| Session file | `.pkl` (pickle) | `.json` (JSON) | ❌ No (re-auth required) |
| File permissions | Not enforced | 600 (owner-only) | N/A |

## Deprecation Timeline

- **v1.0**: New API introduced, old API deprecated but supported
- **v1.1**: Deprecation warnings added
- **v2.0**: Old API will be removed (future)

**Recommendation**: Migrate to the new API now to avoid breaking changes in v2.0.

## Testing Your Migration

After migrating, run these tests:

```python
from bmlibrarian.utils.openathens_auth import OpenAthensConfig, OpenAthensAuth
from bmlibrarian.utils.pdf_manager import PDFManager

# Test 1: Config validation
config = OpenAthensConfig(
    institution_url='https://test.example.edu/login'
)
assert config.institution_url == 'https://test.example.edu/login'
assert config.session_max_age_hours == 24  # Default
print("✓ Config validation passed")

# Test 2: Auth initialization
auth = OpenAthensAuth(config=config)
assert auth.config == config
print("✓ Auth initialization passed")

# Test 3: PDFManager integration
pdf_manager = PDFManager(openathens_auth=auth)
assert pdf_manager.openathens_auth == auth
print("✓ PDFManager integration passed")

# Test 4: Session validation (should be False before login)
assert not auth.is_authenticated()
print("✓ Session validation passed")

print("\n✅ All migration tests passed!")
```

## Troubleshooting

### Issue: "TypeError: __init__() got an unexpected keyword argument"

**Cause**: Passing old-style parameters to new API.

**Solution**: Use the compatibility layer:
```python
# Option 1: Update to new API
config = OpenAthensConfig(institution_url='...')
auth = OpenAthensAuth(config=config)

# Option 2: Use old API with compatibility
auth = OpenAthensAuth(institution_url='...')  # Still works
```

### Issue: "DeprecationWarning" messages in logs

**Cause**: Using old API.

**Solution**: Migrate to new API or suppress warnings temporarily:
```python
import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)
```

### Issue: Session file not found after migration

**Cause**: Old `.pkl` files not compatible with new `.json` format.

**Solution**: Delete old session and re-authenticate:
```bash
rm ~/.bmlibrarian/openathens_session.pkl
# Then run your code to re-authenticate
```

### Issue: "Institution URL must use HTTPS"

**Cause**: New API enforces HTTPS for security.

**Solution**: Update your URL:
```python
# Wrong
config = OpenAthensConfig(institution_url='http://...')  # ❌

# Correct
config = OpenAthensConfig(institution_url='https://...')  # ✅
```

## Getting Help

- **Documentation**: `doc/users/openathens_guide.md`
- **Security Details**: `doc/developers/openathens_security.md`
- **Examples**: `examples/openathens_*.py` (if available)
- **GitHub Issues**: Report migration issues with the `migration` label

## Summary

✅ **Migrate now**: Use new OpenAthensConfig + OpenAthensAuth API
✅ **Backward compatible**: Old API still works with warnings
✅ **More secure**: JSON serialization, file permissions, HTTPS enforcement
✅ **Better performance**: Session caching, configurable timeouts
✅ **Future-proof**: Prepares for v2.0 when old API will be removed

**Recommended migration time**: < 30 minutes for typical use cases.
