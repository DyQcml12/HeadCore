-- HutaoChatCore database v2 schema.
-- Target database name: hutao_chat_core.
-- Platform accounts are not people; profiles are people.
-- Personas are runtime configurations, not database/schema identities.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(128) NOT NULL,
    description VARCHAR(255) NOT NULL,
    applied_at DATETIME(3) NOT NULL,
    PRIMARY KEY (version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS personas (
    id CHAR(36) NOT NULL,
    code VARCHAR(64) NOT NULL,
    display_name VARCHAR(128) NOT NULL,
    description TEXT NULL,
    status ENUM('active', 'disabled', 'archived') NOT NULL DEFAULT 'active',
    default_for_admin BOOLEAN NOT NULL DEFAULT FALSE,
    default_for_normal_friend BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME(3) NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_personas_code (code),
    KEY idx_personas_status_updated (status, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS persona_versions (
    id CHAR(36) NOT NULL,
    persona_id CHAR(36) NOT NULL,
    version_label VARCHAR(64) NOT NULL,
    prompt_template TEXT NOT NULL,
    style_rules_json JSON NULL,
    safety_rules_json JSON NULL,
    memory_policy_json JSON NULL,
    active BOOLEAN NOT NULL DEFAULT FALSE,
    created_by_profile_id CHAR(36) NULL,
    created_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_persona_versions_label (persona_id, version_label),
    KEY idx_persona_versions_active (persona_id, active, created_at),
    CONSTRAINT fk_persona_versions_persona
        FOREIGN KEY (persona_id) REFERENCES personas (id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS profiles (
    id CHAR(36) NOT NULL,
    display_name VARCHAR(128) NOT NULL,
    relationship_type ENUM('admin_partner', 'normal_friend', 'blocked') NOT NULL,
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    trust_level TINYINT UNSIGNED NOT NULL DEFAULT 10,
    affection_level TINYINT UNSIGNED NOT NULL DEFAULT 10,
    notes TEXT NULL,
    status ENUM('active', 'merged', 'deleted') NOT NULL DEFAULT 'active',
    merged_into_profile_id CHAR(36) NULL,
    created_at DATETIME(3) NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_profiles_relationship_updated (relationship_type, updated_at),
    KEY idx_profiles_status_updated (status, updated_at),
    KEY idx_profiles_merged_into (merged_into_profile_id),
    CONSTRAINT fk_profiles_merged_into
        FOREIGN KEY (merged_into_profile_id) REFERENCES profiles (id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS admin_profile (
    singleton_id TINYINT NOT NULL,
    profile_id CHAR(36) NOT NULL,
    created_at DATETIME(3) NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (singleton_id),
    UNIQUE KEY uq_admin_profile_profile (profile_id),
    CONSTRAINT chk_admin_profile_singleton CHECK (singleton_id = 1),
    CONSTRAINT fk_admin_profile_profile
        FOREIGN KEY (profile_id) REFERENCES profiles (id)
        ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS platform_accounts (
    id CHAR(36) NOT NULL,
    profile_id CHAR(36) NOT NULL,
    platform ENUM('qq', 'wechat') NOT NULL,
    platform_user_id VARCHAR(128) NOT NULL,
    platform_group_id VARCHAR(128) NOT NULL DEFAULT '',
    display_name VARCHAR(128) NOT NULL,
    account_label ENUM('main', 'alt', 'work', 'old', 'group_member', 'unknown') NOT NULL DEFAULT 'unknown',
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    status ENUM('active', 'blocked', 'disabled', 'unbound') NOT NULL DEFAULT 'active',
    confidence TINYINT UNSIGNED NOT NULL DEFAULT 50,
    verified_by_profile_id CHAR(36) NULL,
    last_seen_at DATETIME(3) NULL,
    created_at DATETIME(3) NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_platform_accounts_identity (platform, platform_user_id, platform_group_id),
    KEY idx_platform_accounts_profile (profile_id),
    KEY idx_platform_accounts_status_seen (status, last_seen_at),
    KEY idx_platform_accounts_verified_by (verified_by_profile_id),
    CONSTRAINT fk_platform_accounts_profile
        FOREIGN KEY (profile_id) REFERENCES profiles (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_platform_accounts_verified_by
        FOREIGN KEY (verified_by_profile_id) REFERENCES profiles (id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS persona_runtime_bindings (
    id CHAR(36) NOT NULL,
    persona_id CHAR(36) NOT NULL,
    scope ENUM('global', 'relationship_type', 'profile', 'platform', 'conversation') NOT NULL,
    relationship_type ENUM('admin_partner', 'normal_friend', 'blocked') NULL,
    profile_id CHAR(36) NULL,
    platform ENUM('core', 'qq', 'wechat') NULL,
    platform_thread_id VARCHAR(128) NULL,
    priority SMALLINT NOT NULL DEFAULT 100,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME(3) NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_persona_runtime_bindings_lookup (
        enabled,
        scope,
        relationship_type,
        profile_id,
        platform,
        platform_thread_id,
        priority
    ),
    KEY idx_persona_runtime_bindings_persona (persona_id),
    CONSTRAINT fk_persona_runtime_bindings_persona
        FOREIGN KEY (persona_id) REFERENCES personas (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_persona_runtime_bindings_profile
        FOREIGN KEY (profile_id) REFERENCES profiles (id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS profile_social_labels (
    id CHAR(36) NOT NULL,
    profile_id CHAR(36) NOT NULL,
    label_type ENUM('friend', 'relative', 'classmate', 'coworker', 'online_friend', 'unknown', 'user_claim') NOT NULL,
    label_text VARCHAR(128) NOT NULL,
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    verified_by_profile_id CHAR(36) NULL,
    source ENUM('admin_set', 'user_claim', 'migration', 'platform', 'system') NOT NULL,
    created_at DATETIME(3) NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_profile_social_labels_profile (profile_id),
    KEY idx_profile_social_labels_type_verified (label_type, verified),
    CONSTRAINT fk_profile_social_labels_profile
        FOREIGN KEY (profile_id) REFERENCES profiles (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_profile_social_labels_verified_by
        FOREIGN KEY (verified_by_profile_id) REFERENCES profiles (id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS relationship_events (
    id CHAR(36) NOT NULL,
    profile_id CHAR(36) NOT NULL,
    platform VARCHAR(32) NULL,
    platform_user_id VARCHAR(128) NULL,
    event_type ENUM(
        'create',
        'bind',
        'merge',
        'set_role',
        'block',
        'unblock',
        'verify',
        'unverify',
        'set_label',
        'account_block',
        'account_unblock'
    ) NOT NULL,
    old_value JSON NULL,
    new_value JSON NULL,
    changed_by_profile_id CHAR(36) NULL,
    reason TEXT NULL,
    created_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_relationship_events_profile_created (profile_id, created_at),
    KEY idx_relationship_events_changed_by (changed_by_profile_id),
    KEY idx_relationship_events_type_created (event_type, created_at),
    CONSTRAINT fk_relationship_events_profile
        FOREIGN KEY (profile_id) REFERENCES profiles (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_relationship_events_changed_by
        FOREIGN KEY (changed_by_profile_id) REFERENCES profiles (id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS relationship_pending_claims (
    id CHAR(36) NOT NULL,
    platform ENUM('qq', 'wechat') NOT NULL,
    platform_user_id VARCHAR(128) NOT NULL,
    claimed_name VARCHAR(128) NOT NULL,
    claimed_relation_text VARCHAR(255) NOT NULL,
    status ENUM('pending', 'approved', 'rejected') NOT NULL DEFAULT 'pending',
    reviewed_by_profile_id CHAR(36) NULL,
    created_at DATETIME(3) NOT NULL,
    reviewed_at DATETIME(3) NULL,
    PRIMARY KEY (id),
    KEY idx_relationship_pending_claims_status_created (status, created_at),
    KEY idx_relationship_pending_claims_platform_user (platform, platform_user_id),
    CONSTRAINT fk_relationship_pending_claims_reviewed_by
        FOREIGN KEY (reviewed_by_profile_id) REFERENCES profiles (id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS profile_portraits (
    profile_id CHAR(36) NOT NULL,
    preferred_name VARCHAR(128) NULL,
    public_alias VARCHAR(128) NULL,
    communication_style TEXT NULL,
    safe_preferences_json JSON NULL,
    boundaries_json JSON NULL,
    known_context_summary TEXT NULL,
    last_interaction_summary TEXT NULL,
    created_at DATETIME(3) NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (profile_id),
    CONSTRAINT fk_profile_portraits_profile
        FOREIGN KEY (profile_id) REFERENCES profiles (id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS admin_private_profile (
    profile_id CHAR(36) NOT NULL,
    preferred_call_names_json JSON NULL,
    voice_preference_json JSON NULL,
    intimacy_style TEXT NULL,
    comfort_style TEXT NULL,
    taboo_topics_json JSON NULL,
    privacy_rules_json JSON NULL,
    project_context TEXT NULL,
    important_dates_json JSON NULL,
    created_at DATETIME(3) NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (profile_id),
    CONSTRAINT fk_admin_private_profile_profile
        FOREIGN KEY (profile_id) REFERENCES profiles (id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS profile_emotional_state (
    profile_id CHAR(36) NOT NULL,
    recent_mood ENUM('unknown', 'calm', 'happy', 'upset', 'anxious', 'angry', 'sad', 'tired') NOT NULL DEFAULT 'unknown',
    support_need_level TINYINT UNSIGNED NOT NULL DEFAULT 0,
    conflict_level TINYINT UNSIGNED NOT NULL DEFAULT 0,
    warmth_level TINYINT UNSIGNED NOT NULL DEFAULT 0,
    last_detected_at DATETIME(3) NULL,
    decay_after DATETIME(3) NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (profile_id),
    KEY idx_profile_emotional_state_decay (decay_after),
    CONSTRAINT fk_profile_emotional_state_profile
        FOREIGN KEY (profile_id) REFERENCES profiles (id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS conversations (
    id CHAR(36) NOT NULL,
    platform ENUM('core', 'qq', 'wechat') NOT NULL,
    conversation_type ENUM('private', 'group', 'system') NOT NULL,
    platform_thread_id VARCHAR(128) NOT NULL,
    owner_profile_id CHAR(36) NULL,
    title VARCHAR(255) NOT NULL,
    created_at DATETIME(3) NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_conversations_thread (platform, conversation_type, platform_thread_id),
    KEY idx_conversations_owner_updated (owner_profile_id, updated_at),
    CONSTRAINT fk_conversations_owner_profile
        FOREIGN KEY (owner_profile_id) REFERENCES profiles (id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS conversation_persona_state (
    conversation_id CHAR(36) NOT NULL,
    persona_id CHAR(36) NOT NULL,
    active_persona_version_id CHAR(36) NULL,
    state_json JSON NULL,
    last_switched_by_profile_id CHAR(36) NULL,
    last_switched_at DATETIME(3) NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (conversation_id),
    KEY idx_conversation_persona_state_persona (persona_id),
    CONSTRAINT fk_conversation_persona_state_conversation
        FOREIGN KEY (conversation_id) REFERENCES conversations (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_conversation_persona_state_persona
        FOREIGN KEY (persona_id) REFERENCES personas (id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_conversation_persona_state_version
        FOREIGN KEY (active_persona_version_id) REFERENCES persona_versions (id)
        ON DELETE SET NULL,
    CONSTRAINT fk_conversation_persona_state_switched_by
        FOREIGN KEY (last_switched_by_profile_id) REFERENCES profiles (id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS model_invocations (
    id CHAR(36) NOT NULL,
    conversation_id CHAR(36) NULL,
    profile_id CHAR(36) NULL,
    provider VARCHAR(64) NOT NULL,
    model VARCHAR(128) NOT NULL,
    used_live_api BOOLEAN NOT NULL,
    fallback_used BOOLEAN NOT NULL,
    latency_ms DECIMAL(10, 2) NOT NULL,
    prompt_hash CHAR(64) NOT NULL,
    response_hash CHAR(64) NOT NULL,
    error TEXT NULL,
    request_metadata_json JSON NOT NULL,
    created_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_model_invocations_conversation_created (conversation_id, created_at),
    KEY idx_model_invocations_profile_created (profile_id, created_at),
    KEY idx_model_invocations_provider_model_created (provider, model, created_at),
    CONSTRAINT fk_model_invocations_conversation
        FOREIGN KEY (conversation_id) REFERENCES conversations (id)
        ON DELETE SET NULL,
    CONSTRAINT fk_model_invocations_profile
        FOREIGN KEY (profile_id) REFERENCES profiles (id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS messages (
    id CHAR(36) NOT NULL,
    conversation_id CHAR(36) NOT NULL,
    profile_id CHAR(36) NULL,
    platform_account_id CHAR(36) NULL,
    persona_id CHAR(36) NULL,
    platform ENUM('core', 'qq', 'wechat') NOT NULL,
    platform_message_id VARCHAR(128) NULL,
    direction ENUM('inbound', 'outbound', 'internal') NOT NULL,
    role ENUM('user', 'assistant', 'system') NOT NULL,
    content_type ENUM(
        'text',
        'command',
        'attachment_summary',
        'vision_context',
        'voice',
        'safety_replacement',
        'system_event'
    ) NOT NULL,
    content TEXT NOT NULL,
    content_hash CHAR(64) NOT NULL,
    reply_to_message_id CHAR(36) NULL,
    model_invocation_id CHAR(36) NULL,
    safety_status ENUM('not_checked', 'passed', 'replaced', 'blocked') NOT NULL DEFAULT 'not_checked',
    memory_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    visible_to_admin BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_messages_conversation_created (conversation_id, created_at),
    KEY idx_messages_profile_created (profile_id, created_at),
    KEY idx_messages_account_created (platform_account_id, created_at),
    KEY idx_messages_persona_created (persona_id, created_at),
    KEY idx_messages_platform_message (platform, platform_message_id),
    KEY idx_messages_model_invocation (model_invocation_id),
    KEY idx_messages_reply_to (reply_to_message_id),
    CONSTRAINT fk_messages_conversation
        FOREIGN KEY (conversation_id) REFERENCES conversations (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_messages_profile
        FOREIGN KEY (profile_id) REFERENCES profiles (id)
        ON DELETE SET NULL,
    CONSTRAINT fk_messages_platform_account
        FOREIGN KEY (platform_account_id) REFERENCES platform_accounts (id)
        ON DELETE SET NULL,
    CONSTRAINT fk_messages_persona
        FOREIGN KEY (persona_id) REFERENCES personas (id)
        ON DELETE SET NULL,
    CONSTRAINT fk_messages_model_invocation
        FOREIGN KEY (model_invocation_id) REFERENCES model_invocations (id)
        ON DELETE SET NULL,
    CONSTRAINT fk_messages_reply_to
        FOREIGN KEY (reply_to_message_id) REFERENCES messages (id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS message_attachments (
    id CHAR(36) NOT NULL,
    message_id CHAR(36) NOT NULL,
    platform ENUM('qq', 'wechat') NOT NULL,
    attachment_type ENUM('image', 'file', 'voice', 'video', 'sticker', 'location', 'forward', 'unknown') NOT NULL,
    display_name VARCHAR(255) NULL,
    mime_type VARCHAR(128) NULL,
    size_bytes BIGINT NULL,
    local_cache_path VARCHAR(512) NULL,
    remote_url_hash CHAR(64) NULL,
    metadata_json JSON NULL,
    created_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_message_attachments_message (message_id),
    KEY idx_message_attachments_type_created (attachment_type, created_at),
    CONSTRAINT fk_message_attachments_message
        FOREIGN KEY (message_id) REFERENCES messages (id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS persona_evaluations (
    id CHAR(36) NOT NULL,
    message_id CHAR(36) NOT NULL,
    model_invocation_id CHAR(36) NULL,
    passed BOOLEAN NOT NULL,
    score DECIMAL(5, 4) NULL,
    evaluator_provider VARCHAR(64) NOT NULL,
    evaluator_model VARCHAR(128) NOT NULL,
    reasons_json JSON NOT NULL,
    created_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_persona_evaluations_message_created (message_id, created_at),
    KEY idx_persona_evaluations_passed_created (passed, created_at),
    CONSTRAINT fk_persona_evaluations_message
        FOREIGN KEY (message_id) REFERENCES messages (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_persona_evaluations_model_invocation
        FOREIGN KEY (model_invocation_id) REFERENCES model_invocations (id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS safety_guard_events (
    id CHAR(36) NOT NULL,
    message_id CHAR(36) NULL,
    profile_id CHAR(36) NULL,
    guard_name VARCHAR(64) NOT NULL,
    action ENUM('pass', 'replace', 'block', 'ignore') NOT NULL,
    reason_code VARCHAR(64) NOT NULL,
    details_json JSON NULL,
    created_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_safety_guard_events_message (message_id),
    KEY idx_safety_guard_events_profile_created (profile_id, created_at),
    KEY idx_safety_guard_events_action_created (action, created_at),
    CONSTRAINT fk_safety_guard_events_message
        FOREIGN KEY (message_id) REFERENCES messages (id)
        ON DELETE SET NULL,
    CONSTRAINT fk_safety_guard_events_profile
        FOREIGN KEY (profile_id) REFERENCES profiles (id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS memories (
    id CHAR(36) NOT NULL,
    profile_id CHAR(36) NOT NULL,
    persona_id CHAR(36) NULL,
    memory_type VARCHAR(64) NOT NULL,
    visibility_scope ENUM('admin_private', 'profile_private', 'persona_specific', 'safe_preference') NOT NULL DEFAULT 'profile_private',
    content TEXT NOT NULL,
    content_hash CHAR(64) NOT NULL,
    source_message_id CHAR(36) NULL,
    confidence DECIMAL(5, 4) NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    expires_at DATETIME(3) NULL,
    deleted_at DATETIME(3) NULL,
    created_at DATETIME(3) NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_memories_profile_type_active_updated (profile_id, memory_type, active, updated_at),
    KEY idx_memories_persona_scope_updated (persona_id, visibility_scope, updated_at),
    KEY idx_memories_source_message (source_message_id),
    KEY idx_memories_expiry (expires_at),
    CONSTRAINT fk_memories_profile
        FOREIGN KEY (profile_id) REFERENCES profiles (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_memories_persona
        FOREIGN KEY (persona_id) REFERENCES personas (id)
        ON DELETE SET NULL,
    CONSTRAINT fk_memories_source_message
        FOREIGN KEY (source_message_id) REFERENCES messages (id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS memory_events (
    id CHAR(36) NOT NULL,
    memory_id CHAR(36) NULL,
    profile_id CHAR(36) NOT NULL,
    event_type ENUM('create', 'update', 'revoke', 'soft_delete', 'restore', 'expire') NOT NULL,
    old_value JSON NULL,
    new_value JSON NULL,
    changed_by_profile_id CHAR(36) NULL,
    reason TEXT NULL,
    created_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_memory_events_memory_created (memory_id, created_at),
    KEY idx_memory_events_profile_created (profile_id, created_at),
    CONSTRAINT fk_memory_events_memory
        FOREIGN KEY (memory_id) REFERENCES memories (id)
        ON DELETE SET NULL,
    CONSTRAINT fk_memory_events_profile
        FOREIGN KEY (profile_id) REFERENCES profiles (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_memory_events_changed_by
        FOREIGN KEY (changed_by_profile_id) REFERENCES profiles (id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS qq_inbound_events (
    id CHAR(36) NOT NULL,
    message_id CHAR(36) NULL,
    platform_account_id CHAR(36) NULL,
    platform_message_id VARCHAR(128) NULL,
    event_type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    raw_event_redacted_json JSON NULL,
    error_redacted TEXT NULL,
    created_at DATETIME(3) NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_qq_inbound_events_message (message_id),
    KEY idx_qq_inbound_events_account_created (platform_account_id, created_at),
    CONSTRAINT fk_qq_inbound_events_message
        FOREIGN KEY (message_id) REFERENCES messages (id)
        ON DELETE SET NULL,
    CONSTRAINT fk_qq_inbound_events_account
        FOREIGN KEY (platform_account_id) REFERENCES platform_accounts (id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS qq_outbound_events (
    id CHAR(36) NOT NULL,
    message_id CHAR(36) NULL,
    platform_account_id CHAR(36) NULL,
    platform_message_id VARCHAR(128) NULL,
    event_type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    raw_event_redacted_json JSON NULL,
    error_redacted TEXT NULL,
    created_at DATETIME(3) NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_qq_outbound_events_message (message_id),
    KEY idx_qq_outbound_events_account_created (platform_account_id, created_at),
    CONSTRAINT fk_qq_outbound_events_message
        FOREIGN KEY (message_id) REFERENCES messages (id)
        ON DELETE SET NULL,
    CONSTRAINT fk_qq_outbound_events_account
        FOREIGN KEY (platform_account_id) REFERENCES platform_accounts (id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS wechat_inbound_events (
    id CHAR(36) NOT NULL,
    message_id CHAR(36) NULL,
    platform_account_id CHAR(36) NULL,
    platform_message_id VARCHAR(128) NULL,
    event_type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    raw_event_redacted_json JSON NULL,
    error_redacted TEXT NULL,
    created_at DATETIME(3) NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_wechat_inbound_events_message (message_id),
    KEY idx_wechat_inbound_events_account_created (platform_account_id, created_at),
    CONSTRAINT fk_wechat_inbound_events_message
        FOREIGN KEY (message_id) REFERENCES messages (id)
        ON DELETE SET NULL,
    CONSTRAINT fk_wechat_inbound_events_account
        FOREIGN KEY (platform_account_id) REFERENCES platform_accounts (id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS wechat_outbound_events (
    id CHAR(36) NOT NULL,
    message_id CHAR(36) NULL,
    platform_account_id CHAR(36) NULL,
    platform_message_id VARCHAR(128) NULL,
    event_type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    raw_event_redacted_json JSON NULL,
    error_redacted TEXT NULL,
    created_at DATETIME(3) NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_wechat_outbound_events_message (message_id),
    KEY idx_wechat_outbound_events_account_created (platform_account_id, created_at),
    CONSTRAINT fk_wechat_outbound_events_message
        FOREIGN KEY (message_id) REFERENCES messages (id)
        ON DELETE SET NULL,
    CONSTRAINT fk_wechat_outbound_events_account
        FOREIGN KEY (platform_account_id) REFERENCES platform_accounts (id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS platform_command_events (
    id CHAR(36) NOT NULL,
    message_id CHAR(36) NULL,
    actor_profile_id CHAR(36) NULL,
    command_name VARCHAR(64) NOT NULL,
    platform VARCHAR(32) NOT NULL,
    target_platform_user_id VARCHAR(128) NULL,
    status ENUM('accepted', 'rejected', 'failed') NOT NULL,
    reason_code VARCHAR(64) NULL,
    details_json JSON NULL,
    created_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_platform_command_events_actor_created (actor_profile_id, created_at),
    KEY idx_platform_command_events_command_created (command_name, created_at),
    CONSTRAINT fk_platform_command_events_message
        FOREIGN KEY (message_id) REFERENCES messages (id)
        ON DELETE SET NULL,
    CONSTRAINT fk_platform_command_events_actor
        FOREIGN KEY (actor_profile_id) REFERENCES profiles (id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
