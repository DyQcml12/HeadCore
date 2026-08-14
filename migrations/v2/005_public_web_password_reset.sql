-- Public Web password-reset foundation.
-- Apply only after 004_public_web_auth.sql.
-- Raw reset tokens are never persisted.

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    token_hash CHAR(64) NOT NULL,
    expires_at DATETIME(3) NOT NULL,
    used_at DATETIME(3) NULL,
    created_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_password_reset_tokens_hash (token_hash),
    KEY idx_password_reset_tokens_user_active (user_id, used_at, expires_at),
    CONSTRAINT fk_password_reset_tokens_user
        FOREIGN KEY (user_id) REFERENCES web_users (id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE auth_audit_events
    MODIFY COLUMN event_type ENUM(
        'registration_attempt', 'email_verification_sent', 'email_verified',
        'login_attempt', 'login_succeeded', 'logout', 'session_revoked', 'rate_limited',
        'password_reset_requested', 'password_reset_completed'
    ) NOT NULL;
