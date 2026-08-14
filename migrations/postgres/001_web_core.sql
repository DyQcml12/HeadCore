-- HutaoChatCore PostgreSQL web-core schema.
-- This schema owns web accounts, browser sessions, messages, and user-visible memories.
-- Qdrant stores semantic indexes only and must never replace these transactional records.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(128) PRIMARY KEY,
    description VARCHAR(255) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS profiles (
    id VARCHAR(36) PRIMARY KEY,
    display_name VARCHAR(128) NOT NULL,
    relationship_type VARCHAR(32) NOT NULL DEFAULT 'normal_friend',
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS web_users (
    id VARCHAR(36) PRIMARY KEY,
    profile_id VARCHAR(36) NOT NULL UNIQUE REFERENCES profiles(id) ON DELETE RESTRICT,
    email_normalized VARCHAR(320) NOT NULL UNIQUE,
    password_hash VARCHAR(512) NOT NULL,
    status VARCHAR(32) NOT NULL,
    email_verified_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (status IN ('pending_email_verification', 'active', 'suspended', 'deleted'))
);

CREATE INDEX IF NOT EXISTS idx_web_users_status_updated ON web_users(status, updated_at);

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES web_users(id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_email_verification_user_expiry
    ON email_verification_tokens(user_id, expires_at);

CREATE TABLE IF NOT EXISTS web_sessions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES web_users(id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE,
    csrf_secret_hash CHAR(64) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_web_sessions_user_active
    ON web_sessions(user_id, revoked_at, expires_at);

CREATE TABLE IF NOT EXISTS registration_attempts (
    id VARCHAR(36) PRIMARY KEY,
    subject_kind VARCHAR(16) NOT NULL,
    subject_hash CHAR(64) NOT NULL,
    window_started_at TIMESTAMPTZ NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    blocked_until TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE(subject_kind, subject_hash, window_started_at),
    CHECK (subject_kind IN ('email', 'ip_prefix', 'device'))
);

CREATE TABLE IF NOT EXISTS auth_audit_events (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NULL REFERENCES web_users(id) ON DELETE SET NULL,
    event_type VARCHAR(64) NOT NULL,
    outcome VARCHAR(16) NOT NULL,
    reason_code VARCHAR(64) NOT NULL,
    metadata TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (outcome IN ('accepted', 'rejected', 'blocked', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_auth_audit_events_user_created
    ON auth_audit_events(user_id, created_at);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES web_users(id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user_active
    ON password_reset_tokens(user_id, used_at, expires_at);

CREATE TABLE IF NOT EXISTS sessions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(128) NOT NULL,
    client_session_id VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE(user_id, client_session_id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_updated ON sessions(user_id, updated_at);

CREATE TABLE IF NOT EXISTS model_invocations (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id VARCHAR(128) NOT NULL,
    provider VARCHAR(64) NOT NULL,
    model VARCHAR(128) NOT NULL,
    used_live_api BOOLEAN NOT NULL,
    fallback_used BOOLEAN NOT NULL,
    latency_ms NUMERIC(10, 2) NOT NULL,
    prompt_hash CHAR(64) NOT NULL,
    response_hash CHAR(64) NOT NULL,
    error TEXT NULL,
    request_metadata_json TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_model_invocations_session_created
    ON model_invocations(session_id, created_at);

CREATE TABLE IF NOT EXISTS messages (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id VARCHAR(128) NOT NULL,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    content_hash CHAR(64) NOT NULL,
    model_invocation_id VARCHAR(36) NULL REFERENCES model_invocations(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (role IN ('user', 'assistant'))
);

CREATE INDEX IF NOT EXISTS idx_messages_session_created ON messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_user_created ON messages(user_id, created_at);

CREATE TABLE IF NOT EXISTS persona_evaluations (
    id VARCHAR(36) PRIMARY KEY,
    message_id VARCHAR(36) NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    model_invocation_id VARCHAR(36) NULL REFERENCES model_invocations(id) ON DELETE SET NULL,
    passed BOOLEAN NOT NULL,
    score NUMERIC(5, 4) NULL,
    evaluator_provider VARCHAR(64) NOT NULL,
    evaluator_model VARCHAR(128) NOT NULL,
    reasons_json TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_persona_evaluations_message_created
    ON persona_evaluations(message_id, created_at);

CREATE TABLE IF NOT EXISTS memories (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(128) NOT NULL,
    session_id VARCHAR(36) NULL REFERENCES sessions(id) ON DELETE SET NULL,
    memory_type VARCHAR(64) NOT NULL,
    content TEXT NOT NULL,
    content_hash CHAR(64) NOT NULL,
    source_message_id VARCHAR(36) NULL REFERENCES messages(id) ON DELETE SET NULL,
    confidence NUMERIC(5, 4) NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memories_user_updated ON memories(user_id, updated_at);

CREATE TABLE IF NOT EXISTS contacts (
    id VARCHAR(36) PRIMARY KEY,
    display_name VARCHAR(128) NOT NULL,
    relationship_role VARCHAR(32) NOT NULL,
    authority_level INTEGER NOT NULL,
    affection_level INTEGER NOT NULL,
    trust_level INTEGER NOT NULL,
    notes TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS platform_identities (
    id VARCHAR(36) PRIMARY KEY,
    contact_id VARCHAR(36) NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    platform VARCHAR(32) NOT NULL,
    platform_user_id VARCHAR(128) NOT NULL,
    platform_group_id VARCHAR(128) NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE(platform, platform_user_id)
);

CREATE TABLE IF NOT EXISTS relationship_events (
    id VARCHAR(36) PRIMARY KEY,
    contact_id VARCHAR(36) NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    old_role VARCHAR(32) NOT NULL,
    new_role VARCHAR(32) NOT NULL,
    changed_by_contact_id VARCHAR(36) NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS relationship_claims (
    id VARCHAR(36) PRIMARY KEY,
    platform VARCHAR(32) NOT NULL,
    platform_user_id VARCHAR(128) NOT NULL,
    claimed_role VARCHAR(32) NOT NULL,
    claimed_name VARCHAR(128) NOT NULL,
    evidence_text TEXT NOT NULL,
    status VARCHAR(16) NOT NULL,
    reviewer_platform_user_id VARCHAR(128) NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (status IN ('pending', 'approved', 'rejected'))
);

CREATE INDEX IF NOT EXISTS idx_relationship_claims_status_created
    ON relationship_claims(status, created_at);
