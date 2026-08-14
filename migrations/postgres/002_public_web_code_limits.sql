-- Widen rate-limit subject kinds for the six-digit email-code endpoints
-- (verification-code and password-reset-code brute-force limits).
ALTER TABLE registration_attempts ALTER COLUMN subject_kind TYPE VARCHAR(24);
ALTER TABLE registration_attempts DROP CONSTRAINT registration_attempts_subject_kind_check;
ALTER TABLE registration_attempts ADD CONSTRAINT registration_attempts_subject_kind_check
    CHECK (subject_kind IN ('email', 'ip_prefix', 'device', 'verification_code', 'password_reset_code'));
