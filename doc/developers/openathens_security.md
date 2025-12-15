# OpenAthens Authentication Security

This document covers the security architecture, threat model, and implementation details of BMLibrarian's OpenAthens authentication module.

## Security Overview

The OpenAthens authentication module implements multiple security layers to protect sensitive session data and institutional credentials.

### Security Goals

1. **Credential Protection**: Never store user passwords or credentials
2. **Session Security**: Protect authentication cookies from unauthorized access
3. **Data Integrity**: Prevent tampering with session data
4. **Code Safety**: Avoid code execution vulnerabilities
5. **Network Security**: Require encrypted connections

## Threat Model

### Threats Addressed

| Threat | Mitigation | Implementation |
|--------|-----------|----------------|
| **Code Injection** | JSON serialization instead of pickle | `_serialize_session_data()` |
| **File Access** | Restrictive permissions (600) | `chmod(S_IRUSR \| S_IWUSR)` |
| **Session Hijacking** | Secure file storage, HTTPS enforcement | `_validate_url()` |
| **Credential Exposure** | Never store passwords, only cookies | Session data structure |
| **MITM Attacks** | HTTPS-only requirement | URL validation |
| **Directory Traversal** | Fixed session directory | `~/.bmlibrarian/` |

### Threats NOT Addressed

❌ **Not Protected Against**:
- Physical access to user's home directory
- Root/administrator access to the system
- Memory dumps while session is loaded
- Browser-based attacks during login
- Malicious Playwright extensions

**Rationale**: These require system-level security controls outside the scope of this module.

## Security Implementation Details

### 1. Pickle Vulnerability ELIMINATED

**Problem**: Pickle can execute arbitrary code during deserialization.

**Solution**: Use JSON for session storage.

#### Before (Vulnerable):
```python
# ❌ Security Risk: Pickle allows code execution
import pickle
with open(self.session_file, 'wb') as f:
    pickle.dump(self.session_data, f)
```

**Attack Vector**:
```python
# Attacker creates malicious pickle file
import pickle
import os

class Exploit:
    def __reduce__(self):
        return (os.system, ('malicious_command',))

with open('session.pkl', 'wb') as f:
    pickle.dump(Exploit(), f)
```

#### After (Secure):
```python
# ✅ Secure: JSON cannot execute code
import json
with open(self.session_file, 'w') as f:
    serialized = self._serialize_session_data(self.session_data)
    json.dump(serialized, f, indent=2)
```

**Security Properties**:
- ✅ JSON only stores data, never code
- ✅ Deserialization cannot execute functions
- ✅ Datetime objects serialized as ISO 8601 strings
- ✅ Simple validation during load

### 2. File Permissions

**Requirement**: Session files must be readable/writable only by owner.

**Implementation**:
```python
import stat

# Set permissions: 600 (owner read/write only)
self.session_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
```

**Verification**:
```bash
# Check file permissions
ls -la ~/.bmlibrarian/openathens_session.json
# Output: -rw------- 1 user group ... openathens_session.json
#          ^^^ ^^^ ^^^
#          |   |   +-- Others: no access
#          |   +------ Group: no access
#          +---------- Owner: read + write
```

**Directory Permissions**:
```python
# Parent directory: 700 (owner access only)
session_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
```

### 3. URL Validation

**Security Check**: Reject non-HTTPS URLs.

**Implementation**:
```python
def _validate_url(self, url: str) -> str:
    parsed = urlparse(url)

    # Require HTTPS for security
    if parsed.scheme != 'https':
        raise ValueError(f"Institution URL must use HTTPS: {url}")

    # Require hostname
    if not parsed.netloc:
        raise ValueError(f"Invalid URL format: {url}")

    return url.rstrip('/')
```

**Why HTTPS is Required**:
- Prevents MITM attacks during authentication
- Protects credentials in transit
- Ensures server identity verification
- Industry standard for authentication

**Rejected URLs**:
```python
# ❌ HTTP - Not encrypted
OpenAthensConfig(institution_url='http://institution.edu/login')

# ❌ Invalid format - No hostname
OpenAthensConfig(institution_url='not-a-url')

# ❌ Empty - No URL provided
OpenAthensConfig(institution_url='')
```

### 4. Cookie Pattern Security

**Purpose**: Detect authentication success via specific cookie patterns.

**Implementation**:
```python
# Specific patterns reduce false positives
self.auth_cookie_patterns = [
    r'openathens.*session',  # OpenAthens session cookies
    r'_saml_.*',             # SAML authentication
    r'shib.*session',        # Shibboleth sessions
    r'shibsession.*',        # Shibboleth variant
    r'_shibstate_.*'         # Shibboleth state
]

def _detect_auth_success(self, cookies: List[Dict]) -> bool:
    cookie_names = [c['name'] for c in cookies]
    for pattern in self.auth_cookie_patterns:
        for name in cookie_names:
            if re.search(pattern, name, re.IGNORECASE):
                return True
    return False
```

**Security Considerations**:
- ✅ Regex patterns are specific, not overly broad
- ✅ Case-insensitive matching for flexibility
- ✅ Configurable for institution-specific cookies
- ⚠️ Pattern too broad could cause false positives

**Recommended**: Add institution-specific patterns:
```python
config.auth_cookie_patterns.append(r'myinstitution_auth_.*')
```

### 5. Network Connectivity Check

**Purpose**: Detect network issues before attempting authentication.

**Implementation**:
```python
def _check_network_connectivity(self) -> bool:
    try:
        response = requests.head(
            self.config.institution_url,
            timeout=10,
            allow_redirects=True
        )
        return response.status_code < 400
    except Exception as e:
        logger.warning(f"Network connectivity check failed: {e}")
        return False
```

**Security Benefits**:
- ✅ Prevents exposing auth attempts on unreachable networks
- ✅ Early failure detection
- ✅ Reduces timeout delays
- ✅ Provides better error messages

#### OpenAthens Redirector URLs (Special Handling)

OpenAthens uses two different URL patterns that require different handling:

| URL Type | Pattern | Connectivity Check |
|----------|---------|-------------------|
| **Portal URLs** | `my.openathens.net/*` | ✅ Check required |
| **Redirector URLs** | `go.openathens.net/redirector/{domain}` | ❌ Skip check |

**Why Redirector URLs are special**:
- Redirector URLs don't respond to HEAD requests directly
- They only work when a target URL is appended: `?url={encoded_target}`
- Checking `go.openathens.net/redirector/jcu.edu.au` always fails, but the redirector works fine

**Implementation**:
```python
def _check_network_connectivity(self) -> bool:
    # Skip connectivity check for OpenAthens Redirector URLs
    # These URLs don't respond directly - they need a target URL parameter
    if 'go.openathens.net/redirector' in self.config.institution_url:
        logger.debug("Skipping connectivity check for OpenAthens Redirector URL")
        return True

    # Normal connectivity check for other URLs
    try:
        response = requests.head(self.config.institution_url, timeout=10)
        return response.status_code < 400
    except Exception as e:
        logger.warning(f"Network connectivity check failed: {e}")
        return False
```

**How Redirector URLs work**:
```
1. User visits: https://go.openathens.net/redirector/jcu.edu.au?url=https://link.springer.com/article/10.1007/example

2. OpenAthens:
   a. Identifies institution by domain (jcu.edu.au)
   b. Redirects to institution's SSO if not authenticated
   c. After auth, redirects to target URL with session cookies

3. Publisher receives request with OpenAthens cookies → grants access
```

### 6. Session Validation Caching

**Purpose**: Reduce overhead without compromising security.

**Implementation**:
```python
def is_authenticated(self) -> bool:
    # Check cache first
    if self._last_validation_time:
        cache_age = (datetime.now() - self._last_validation_time).total_seconds()
        if cache_age < self.config.session_cache_ttl:
            return self._last_validation_result

    # Perform validation
    result = self.is_session_valid()

    # Update cache
    self._last_validation_time = datetime.now()
    self._last_validation_result = result

    return result
```

**Security Properties**:
- ✅ Short TTL (default: 60 seconds) balances performance and security
- ✅ Cache invalidated on session changes
- ✅ Full validation on cache miss
- ⚠️ Very long TTL could miss session expiration

**Performance Impact**:
```python
# Without caching: 100 downloads = 100 validation checks
for doc in documents:  # 100 iterations
    if pdf_manager.openathens_auth.is_authenticated():  # Check every time
        pdf_manager.download_pdf(doc)

# With caching (60s TTL): 100 downloads = ~2 validation checks
# (Assuming downloads take <60s total)
```

### 7. Browser Cleanup and Crash Handling

**Purpose**: Prevent resource leaks and handle browser crashes gracefully.

**Implementation**:
```python
async def _cleanup_browser(self):
    """Cleanup browser resources with error handling."""
    try:
        if self.browser:
            await self.browser.close()
            self.browser = None
    except Exception as e:
        logger.debug(f"Error closing browser: {e}")

    try:
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
    except Exception as e:
        logger.debug(f"Error stopping playwright: {e}")
```

**Exception Handling**:
```python
try:
    # Browser operations
    await page.goto(url)
except Exception as e:
    logger.error(f"Navigation failed: {e}")
    await context.close()
    await self._cleanup_browser()  # Always cleanup
    return False
```

**Security Benefits**:
- ✅ Prevents resource exhaustion
- ✅ Handles browser crashes without exposing state
- ✅ Ensures cleanup on errors
- ✅ Logs errors for debugging without exposing sensitive data

## Data Flow Security

### Authentication Flow

```
1. User → Config Creation
   ├─ HTTPS URL validation
   └─ Parameter sanitization

2. Config → OpenAthensAuth
   ├─ Session file path validation
   └─ Load existing session (JSON)

3. Check Network Connectivity
   ├─ HEAD request to institution URL
   └─ Verify reachability

4. Launch Browser (Playwright)
   ├─ Stealth settings
   └─ Isolated context

5. User Login (Interactive)
   ├─ User enters credentials
   └─ Browser handles auth flow

6. Cookie Detection
   ├─ Poll for auth cookies
   └─ Match against patterns

7. Session Capture
   ├─ Extract cookies
   ├─ Capture user agent
   └─ Create session data

8. Session Save
   ├─ Serialize to JSON
   ├─ Write to file
   └─ Set permissions (600)

9. Browser Cleanup
   ├─ Close context
   ├─ Close browser
   └─ Stop Playwright
```

### Download Flow with Authentication

```
1. PDFManager.download_pdf()
   └─ Check if openathens_auth exists

2. If auth available:
   ├─ Check is_authenticated() [cached]
   ├─ Get user agent
   └─ Get cookies

3. Prepare HTTP Request
   ├─ Add User-Agent header
   ├─ Add cookies
   └─ HTTPS URL

4. Execute Download
   ├─ requests.get() with auth
   └─ Stream PDF content

5. Save PDF
   └─ Write to year-based directory
```

## Session Data Structure

### JSON Schema

```json
{
  "created_at": "2025-01-15T10:30:00.123456",
  "cookies": [
    {
      "name": "openathens_session_id",
      "value": "enc_abc123...",
      "domain": ".example.com",
      "path": "/",
      "expires": 1737028200.0,
      "httpOnly": true,
      "secure": true,
      "sameSite": "Lax"
    }
  ],
  "institution_url": "https://institution.openathens.net/login",
  "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)..."
}
```

### Field Security

| Field | Sensitivity | Storage | Transmission |
|-------|-------------|---------|--------------|
| `created_at` | Low | Plaintext | N/A |
| `cookies[].name` | Low | Plaintext | HTTPS |
| `cookies[].value` | **HIGH** | Plaintext | HTTPS |
| `cookies[].domain` | Low | Plaintext | N/A |
| `institution_url` | Low | Plaintext | N/A |
| `user_agent` | Low | Plaintext | HTTPS |

**Most Sensitive**: Cookie values - these authenticate requests.

### Why Plaintext Storage is Acceptable

**Context**: Session files are stored in `~/.bmlibrarian/` with 600 permissions.

**Security Model**:
- ✅ File permissions prevent other users from reading
- ✅ Similar to browser cookie storage model
- ✅ Encryption at rest requires key management (added complexity)
- ✅ Session expiration limits exposure window

**Comparison to Browser Storage**:
```
Browser Cookies:
- Stored in SQLite database
- Minimal encryption (varies by browser)
- Similar permission model (user-only access)
- BMLibrarian follows same security model
```

**When Encryption Would Be Required**:
- ❌ Multi-user systems with shared home directories
- ❌ Cloud storage of session files
- ❌ Regulatory compliance requirements (HIPAA, etc.)
- ✅ In these cases, use institutional VPN/proxy instead

## Configuration Security

### Secure Configuration Example

```python
config = OpenAthensConfig(
    # ✅ HTTPS only
    institution_url='https://institution.openathens.net/login',

    # ✅ Reasonable session lifetime
    session_max_age_hours=24,

    # ✅ Responsive polling without DOS
    auth_check_interval=1.0,

    # ✅ Adequate timeout for legitimate use
    cloudflare_wait=30,

    # ✅ Reasonable page timeout
    page_timeout=60000,

    # ✅ Headless for production
    headless=True,

    # ✅ Short cache TTL
    session_cache_ttl=60
)
```

### Insecure Configurations

```python
# ❌ HTTP - credentials transmitted in clear
institution_url='http://...'

# ❌ Excessive session lifetime
session_max_age_hours=720  # 30 days - too long

# ❌ Aggressive polling (potential DOS)
auth_check_interval=0.01  # 10ms - too fast

# ❌ Very long cache TTL
session_cache_ttl=3600  # 1 hour - may miss expiration
```

## Security Testing

### Test Coverage

The test suite includes security-focused tests:

1. **URL Validation Tests**:
   ```python
   test_url_validation_requires_https()
   test_url_validation_requires_valid_url()
   test_url_validation_requires_non_empty()
   ```

2. **Serialization Tests**:
   ```python
   test_serialize_deserialize_session_data()
   test_save_and_load_session()
   test_load_session_handles_corrupted_file()
   ```

3. **File Permission Tests**:
   ```python
   # Verify 600 permissions
   file_mode = temp_session_file.stat().st_mode
   assert file_mode & stat.S_IRUSR  # Owner read
   assert file_mode & stat.S_IWUSR  # Owner write
   assert not (file_mode & stat.S_IRGRP)  # No group read
   ```

4. **Cookie Detection Tests**:
   ```python
   test_detect_auth_success_with_openathens_cookie()
   test_detect_auth_success_with_saml_cookie()
   test_detect_auth_success_no_auth_cookies()
   ```

### Manual Security Testing

#### Test 1: File Permissions
```bash
# Run authentication
python -c "from bmlibrarian.utils.openathens_auth import *; ..."

# Check permissions
ls -la ~/.bmlibrarian/openathens_session.json

# Expected: -rw------- (600)
# If different, FAIL
```

#### Test 2: JSON Safety
```bash
# Create session file with malicious code
echo '{"__reduce__": ["os.system", ["echo EXPLOITED"]]}' > ~/.bmlibrarian/openathens_session.json

# Load session
python -c "from bmlibrarian.utils.openathens_auth import OpenAthensAuth; ..."

# Expected: Error or None, NOT "EXPLOITED"
# If "EXPLOITED" appears, FAIL (code execution)
```

#### Test 3: HTTPS Enforcement
```python
# Try HTTP URL
from bmlibrarian.utils.openathens_auth import OpenAthensConfig

try:
    config = OpenAthensConfig(institution_url='http://example.com')
    print("FAIL: HTTP allowed")
except ValueError as e:
    print("PASS: HTTP rejected")
```

#### Test 4: Session Expiration
```python
# Create old session
from datetime import datetime, timedelta
auth.session_data = {
    'created_at': datetime.now() - timedelta(hours=25),
    'cookies': [],
    'institution_url': '...',
    'user_agent': '...'
}

# Check authentication
assert not auth.is_authenticated()  # Should be False
```

## Security Recommendations

### For Developers

1. **Never log session data**:
   ```python
   # ❌ Don't do this
   logger.info(f"Session: {auth.session_data}")

   # ✅ Do this
   logger.info(f"Session valid: {auth.is_session_valid()}")
   ```

2. **Validate configuration**:
   ```python
   # ✅ Validate before use
   try:
       config = OpenAthensConfig(url=user_input)
   except ValueError as e:
       logger.error(f"Invalid config: {e}")
       raise
   ```

3. **Handle errors gracefully**:
   ```python
   # ✅ Don't expose internal state
   try:
       await auth.login_interactive()
   except Exception as e:
       logger.error("Login failed")  # Generic message
       # Don't: logger.error(f"Login failed: {auth.session_data}")
   ```

4. **Clear sessions on errors**:
   ```python
   # ✅ Clear compromised sessions
   try:
       validate_session(auth)
   except SecurityError:
       auth.clear_session()
       raise
   ```

### For Users

1. **Use strong institutional passwords**
2. **Enable 2FA if available**
3. **Don't share session files**
4. **Use secure networks for authentication**
5. **Clear sessions when done**: `auth.clear_session()`
6. **Don't commit session files to git**:
   ```bash
   # Add to .gitignore
   echo ".bmlibrarian/openathens_session.json" >> .gitignore
   ```

### For System Administrators

1. **Ensure home directory encryption** (full disk encryption)
2. **Monitor for unusual authentication patterns**
3. **Implement institutional access policies**
4. **Regular security audits of session files**
5. **Network-level security** (VPN, firewalls)

## Compliance Considerations

### FERPA (Educational Records)

- ✅ Session data doesn't contain educational records
- ✅ Only authentication cookies stored
- ⚠️ Ensure institutional compliance for research use

### HIPAA (Healthcare)

- ❌ Current implementation NOT suitable for PHI access
- ⚠️ Would require encryption at rest
- ⚠️ Would require audit logging
- ✅ Use institutional VPN/proxy for HIPAA compliance

### GDPR (Data Protection)

- ✅ Minimal data collection (no PII)
- ✅ User controls data (clear_session)
- ✅ Secure storage (file permissions)
- ⚠️ Ensure institutional data processing agreements

## Vulnerability Disclosure

If you discover a security vulnerability:

1. **Do NOT** open a public GitHub issue
2. **Do** email security details to [project maintainer]
3. **Include**:
   - Description of vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

4. **Wait** for response before public disclosure

## Security Audit History

- **2025-01-17**: Initial security implementation
  - Replaced pickle with JSON
  - Added file permissions (600)
  - Implemented HTTPS validation
  - Added network connectivity checks
  - Implemented session validation caching
  - Added browser cleanup handling

## References

- [OWASP Deserialization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Deserialization_Cheat_Sheet.html)
- [Python pickle Security](https://docs.python.org/3/library/pickle.html#module-pickle)
- [File Permissions Best Practices](https://wiki.archlinux.org/title/File_permissions_and_attributes)
- [OpenAthens Security Documentation](https://www.openathens.net/security/)
