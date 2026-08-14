-- Public Web authentication foundation.
-- Apply only after V2 schema migration 001, which creates profiles.
-- Raw browser/session and email-verification secrets are never persisted.

CREATE TABLE IF NOT EXISTS web_users (
    id CHAR(36) NOT NULL,
    profile_id CHAR(36) NOT NULL,
    email_normalized VARCHAR(320) NOT NULL,
    password_hash VARCHAR(512) NOT NULL,
    status ENUM('pending_email_verification', 'active', 'suspended', 'deleted')
        NOT NULL DEFAULT 'pending_email_verification',
    email_verified_at DATETIME(3) NULL,
    created_at DATETIME(3) NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_web_users_profile (profile_id),
    UNIQUE KEY uq_web_users_email (email_normalized),
    KEY idx_web_users_status_updated (status, updated_at),
    CONSTRAINT fk_web_users_profile
        FOREIGN KEY (profile_id) REFERENCES profiles (id)
        ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    token_hash CHAR(64) NOT NULL,
    expires_at DATETIME(3) NOT NULL,
    used_at DATETIME(3) NULL,
    created_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_email_verification_tokens_hash (token_hash),
    KEY idx_email_verification_tokens_user_expiry (user_id, expires_at),
    CONSTRAINT fk_email_verification_tokens_user
        FOREIGN KEY (user_id) REFERENCES web_users (id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS web_sessions (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    token_hash CHAR(64) NOT NULL,
    csrf_secret_hash CHAR(64) NOT NULL,
    expires_at DATETIME(3) NOT NULL,
    revoked_at DATETIME(3) NULL,
    last_seen_at DATETIME(3) NOT NULL,
    created_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_web_sessions_token_hash (token_hash),
    KEY idx_web_sessions_user_active (user_id, revoked_at, expires_at),
    CONSTRAINT fk_web_sessions_user
        FOREIGN KEY (user_id) REFERENCES web_users (id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS registration_attempts (
    id CHAR(36) NOT NULL,
    subject_kind ENUM('email', 'ip_prefix', 'device') NOT NULL,
    subject_hash CHAR(64) NOT NULL,
    window_started_at DATETIME(3) NOT NULL,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    blocked_until DATETIME(3) NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_registration_attempts_subject_window (subject_kind, subject_hash, window_started_at),
    KEY idx_registration_attempts_blocked (blocked_until)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS auth_audit_events (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NULL,
    event_type ENUM(
        'registration_attempt', 'email_verification_sent', 'email_verified',
        'login_attempt', 'login_succeeded', 'logout', 'session_revoked', 'rate_limited'
    ) NOT NULL,
    outcome ENUM('accepted', 'rejected', 'blocked', 'failed') NOT NULL,
    reason_code VARCHAR(64) NOT NULL,
    metadata JSON NULL,
    created_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_auth_audit_events_user_created (user_id, created_at),
    KEY idx_auth_audit_events_event_created (event_type, created_at),
    CONSTRAINT fk_auth_audit_events_user
        FOREIGN KEY (user_id) REFERENCES web_users (id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
