-- Migration: Add pgcrypto extension
-- Description: Enable pgcrypto extension for gen_random_bytes() function used in session token generation
-- Author: BMLibrarian
-- Date: 2025-11-22
-- Version: 1.0.0

-- ============================================================================
-- Enable pgcrypto extension
-- ============================================================================

-- pgcrypto provides cryptographic functions including gen_random_bytes()
-- which is used by bmlsettings.create_session() for secure token generation
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Log successful migration
DO $$
BEGIN
    RAISE NOTICE 'pgcrypto extension enabled successfully';
END $$;
