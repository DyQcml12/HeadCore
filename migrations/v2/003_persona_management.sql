-- S5 persona management control-plane persistence.
-- This schema is intentionally separate from the legacy runtime persona tables.

CREATE TABLE IF NOT EXISTS persona_management_drafts (
    draft_id VARCHAR(128) NOT NULL,
    profile_id VARCHAR(64) NOT NULL,
    definition_json JSON NOT NULL,
    status ENUM('draft', 'schema_validated', 'offline_evaluated', 'approved', 'published', 'archived') NOT NULL,
    created_by_profile_id CHAR(36) NOT NULL,
    created_at DATETIME(3) NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (draft_id),
    KEY idx_persona_mgmt_drafts_profile_status (profile_id, status, updated_at),
    CONSTRAINT fk_persona_mgmt_drafts_actor
        FOREIGN KEY (created_by_profile_id) REFERENCES profiles(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS persona_management_validations (
    draft_id VARCHAR(128) NOT NULL,
    stage ENUM('schema', 'gate', 'regression', 'live_acceptance') NOT NULL,
    passed BOOLEAN NOT NULL,
    errors_json JSON NOT NULL,
    evaluated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (draft_id, stage),
    CONSTRAINT fk_persona_mgmt_validations_draft
        FOREIGN KEY (draft_id) REFERENCES persona_management_drafts(draft_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS persona_management_versions (
    version_id VARCHAR(128) NOT NULL,
    profile_id VARCHAR(64) NOT NULL,
    version_number INT UNSIGNED NOT NULL,
    definition_json JSON NOT NULL,
    source_draft_id VARCHAR(128) NOT NULL,
    approved_by_profile_id CHAR(36) NOT NULL,
    created_at DATETIME(3) NOT NULL,
    PRIMARY KEY (version_id),
    UNIQUE KEY uq_persona_mgmt_version_number (profile_id, version_number),
    UNIQUE KEY uq_persona_mgmt_version_draft (source_draft_id),
    CONSTRAINT fk_persona_mgmt_versions_draft
        FOREIGN KEY (source_draft_id) REFERENCES persona_management_drafts(draft_id),
    CONSTRAINT fk_persona_mgmt_versions_actor
        FOREIGN KEY (approved_by_profile_id) REFERENCES profiles(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS persona_management_releases (
    release_id CHAR(32) NOT NULL,
    profile_id VARCHAR(64) NOT NULL,
    version_id VARCHAR(128) NOT NULL,
    status ENUM('active', 'superseded', 'rolled_back', 'archived') NOT NULL,
    operation_id VARCHAR(128) NOT NULL,
    actor_profile_id CHAR(36) NOT NULL,
    replaced_release_id CHAR(32) NULL,
    rollback_of_release_id CHAR(32) NULL,
    active_profile_id VARCHAR(64)
        GENERATED ALWAYS AS (CASE WHEN status = 'active' THEN profile_id ELSE NULL END) STORED,
    created_at DATETIME(3) NOT NULL,
    PRIMARY KEY (release_id),
    UNIQUE KEY uq_persona_mgmt_release_operation (operation_id),
    UNIQUE KEY uq_persona_mgmt_active_profile (active_profile_id),
    KEY idx_persona_mgmt_releases_profile_created (profile_id, created_at),
    CONSTRAINT fk_persona_mgmt_releases_version
        FOREIGN KEY (version_id) REFERENCES persona_management_versions(version_id),
    CONSTRAINT fk_persona_mgmt_releases_actor
        FOREIGN KEY (actor_profile_id) REFERENCES profiles(id),
    CONSTRAINT fk_persona_mgmt_releases_replaced
        FOREIGN KEY (replaced_release_id) REFERENCES persona_management_releases(release_id),
    CONSTRAINT fk_persona_mgmt_releases_rollback
        FOREIGN KEY (rollback_of_release_id) REFERENCES persona_management_releases(release_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS persona_management_bindings (
    binding_id VARCHAR(128) NOT NULL,
    scope ENUM('global', 'platform', 'relationship', 'profile', 'conversation') NOT NULL,
    scope_key VARCHAR(255) NOT NULL,
    version_id VARCHAR(128) NOT NULL,
    surface_json JSON NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    updated_by_profile_id CHAR(36) NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (binding_id),
    UNIQUE KEY uq_persona_mgmt_binding_scope (scope, scope_key),
    KEY idx_persona_mgmt_bindings_lookup (enabled, scope, scope_key),
    CONSTRAINT fk_persona_mgmt_bindings_version
        FOREIGN KEY (version_id) REFERENCES persona_management_versions(version_id),
    CONSTRAINT fk_persona_mgmt_bindings_actor
        FOREIGN KEY (updated_by_profile_id) REFERENCES profiles(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS persona_management_operations (
    operation_id VARCHAR(128) NOT NULL,
    operation_type ENUM('publish', 'rollback') NOT NULL,
    profile_id VARCHAR(64) NOT NULL,
    version_id VARCHAR(128) NOT NULL,
    release_id CHAR(32) NOT NULL,
    actor_profile_id CHAR(36) NOT NULL,
    created_at DATETIME(3) NOT NULL,
    PRIMARY KEY (operation_id),
    KEY idx_persona_mgmt_operations_profile_created (profile_id, created_at),
    CONSTRAINT fk_persona_mgmt_operations_version
        FOREIGN KEY (version_id) REFERENCES persona_management_versions(version_id),
    CONSTRAINT fk_persona_mgmt_operations_release
        FOREIGN KEY (release_id) REFERENCES persona_management_releases(release_id),
    CONSTRAINT fk_persona_mgmt_operations_actor
        FOREIGN KEY (actor_profile_id) REFERENCES profiles(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO schema_migrations (version, description, applied_at)
VALUES ('v2.003_persona_management', 'S5 persona management control plane', CURRENT_TIMESTAMP(3))
ON DUPLICATE KEY UPDATE description = VALUES(description);
