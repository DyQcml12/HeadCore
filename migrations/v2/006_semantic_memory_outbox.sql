-- Derived semantic-memory index synchronization.
-- MySQL memory_records remains the sole source of truth. Qdrant is rebuildable.

CREATE TABLE IF NOT EXISTS semantic_memory_outbox (
    id CHAR(36) NOT NULL,
    memory_record_id CHAR(36) NOT NULL,
    profile_id CHAR(36) NOT NULL,
    operation ENUM('upsert', 'delete') NOT NULL,
    state ENUM('pending', 'processing', 'completed', 'retry') NOT NULL DEFAULT 'pending',
    attempts INT UNSIGNED NOT NULL DEFAULT 0,
    available_at DATETIME(3) NOT NULL,
    lease_expires_at DATETIME(3) NULL,
    worker_id VARCHAR(128) NULL,
    last_error VARCHAR(64) NULL,
    created_at DATETIME(3) NOT NULL,
    completed_at DATETIME(3) NULL,
    PRIMARY KEY (id),
    KEY idx_semantic_memory_outbox_claim (state, available_at, lease_expires_at, created_at),
    KEY idx_semantic_memory_outbox_record (memory_record_id, created_at),
    CONSTRAINT fk_semantic_memory_outbox_record
        FOREIGN KEY (memory_record_id) REFERENCES memory_records(id) ON DELETE CASCADE,
    CONSTRAINT fk_semantic_memory_outbox_profile
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DELIMITER $$

CREATE TRIGGER trg_memory_records_semantic_insert
AFTER INSERT ON memory_records
FOR EACH ROW
BEGIN
    INSERT INTO semantic_memory_outbox (
        id, memory_record_id, profile_id, operation, state, attempts,
        available_at, created_at
    ) VALUES (
        UUID(), NEW.id, NEW.profile_id,
        IF(NEW.state = 'active', 'upsert', 'delete'), 'pending', 0,
        CURRENT_TIMESTAMP(3), CURRENT_TIMESTAMP(3)
    );
END$$

CREATE TRIGGER trg_memory_records_semantic_update
AFTER UPDATE ON memory_records
FOR EACH ROW
BEGIN
    INSERT INTO semantic_memory_outbox (
        id, memory_record_id, profile_id, operation, state, attempts,
        available_at, created_at
    ) VALUES (
        UUID(), NEW.id, NEW.profile_id,
        IF(NEW.state = 'active', 'upsert', 'delete'), 'pending', 0,
        CURRENT_TIMESTAMP(3), CURRENT_TIMESTAMP(3)
    );
END$$

DELIMITER ;

INSERT INTO schema_migrations (version, description, applied_at)
VALUES (
    'v2.006_semantic_memory_outbox',
    'Derived semantic memory index outbox',
    CURRENT_TIMESTAMP(3)
)
ON DUPLICATE KEY UPDATE description = VALUES(description);
