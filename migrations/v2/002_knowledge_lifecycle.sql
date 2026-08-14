-- S4 knowledge lifecycle persistence.
-- Apply after v2.001_hutao_chat_core_schema.

CREATE TABLE IF NOT EXISTS memory_candidates (
    id CHAR(36) NOT NULL,
    profile_id CHAR(36) NOT NULL,
    memory_key VARCHAR(191) NOT NULL,
    memory_value TEXT NOT NULL,
    scope ENUM('admin_private', 'profile_private', 'persona_specific', 'safe_preference') NOT NULL,
    source_type VARCHAR(64) NOT NULL,
    source_id VARCHAR(191) NOT NULL,
    idempotency_key CHAR(64) NULL,
    confidence DECIMAL(5,4) NOT NULL,
    persona_id VARCHAR(128) NULL,
    expires_at DATETIME(3) NULL,
    observation_quality DECIMAL(5,4) NULL,
    changes_authority BOOLEAN NOT NULL DEFAULT FALSE,
    state ENUM('candidate', 'active', 'superseded', 'revoked', 'expired', 'deleted') NOT NULL,
    created_at DATETIME(3) NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_memory_candidates_profile_state (profile_id, state, created_at),
    KEY idx_memory_candidates_source (source_type, source_id),
    UNIQUE KEY uq_memory_candidates_idempotency (profile_id, idempotency_key),
    CONSTRAINT fk_memory_candidates_profile
        FOREIGN KEY (profile_id) REFERENCES profiles(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS memory_records (
    id CHAR(36) NOT NULL,
    candidate_id CHAR(36) NOT NULL,
    profile_id CHAR(36) NOT NULL,
    memory_key VARCHAR(191) NOT NULL,
    memory_value TEXT NOT NULL,
    scope ENUM('admin_private', 'profile_private', 'persona_specific', 'safe_preference') NOT NULL,
    source_type VARCHAR(64) NOT NULL,
    source_id VARCHAR(191) NOT NULL,
    confidence DECIMAL(5,4) NOT NULL,
    state ENUM('candidate', 'active', 'superseded', 'revoked', 'expired', 'deleted') NOT NULL,
    persona_id VARCHAR(128) NULL,
    expires_at DATETIME(3) NULL,
    supersedes_id CHAR(36) NULL,
    state_reason VARCHAR(255) NOT NULL DEFAULT '',
    row_version BIGINT UNSIGNED NOT NULL DEFAULT 1,
    created_at DATETIME(3) NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_memory_records_candidate (candidate_id),
    KEY idx_memory_records_projection (profile_id, state, scope, expires_at),
    KEY idx_memory_records_conflict (profile_id, memory_key, persona_id, state),
    CONSTRAINT fk_memory_records_candidate
        FOREIGN KEY (candidate_id) REFERENCES memory_candidates(id),
    CONSTRAINT fk_memory_records_profile
        FOREIGN KEY (profile_id) REFERENCES profiles(id),
    CONSTRAINT fk_memory_records_supersedes
        FOREIGN KEY (supersedes_id) REFERENCES memory_records(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS memory_audit_events (
    id CHAR(36) NOT NULL,
    entity_type VARCHAR(32) NOT NULL,
    entity_id CHAR(36) NOT NULL,
    action VARCHAR(64) NOT NULL,
    actor_profile_id CHAR(36) NULL,
    reason VARCHAR(255) NOT NULL DEFAULT '',
    details_json JSON NULL,
    occurred_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_memory_audit_entity (entity_type, entity_id, occurred_at),
    KEY idx_memory_audit_actor (actor_profile_id, occurred_at),
    CONSTRAINT fk_memory_audit_actor
        FOREIGN KEY (actor_profile_id) REFERENCES profiles(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO schema_migrations (version, description, applied_at)
VALUES ('v2.002_knowledge_lifecycle', 'S4 knowledge lifecycle persistence', CURRENT_TIMESTAMP(3))
ON DUPLICATE KEY UPDATE description = VALUES(description);
