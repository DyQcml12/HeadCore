-- Widen rate-limit subject kinds for the six-digit email-code endpoints
-- (verification-code and password-reset-code brute-force limits).
ALTER TABLE registration_attempts
    MODIFY COLUMN subject_kind ENUM(
        'email', 'ip_prefix', 'device', 'verification_code', 'password_reset_code'
    ) NOT NULL;
