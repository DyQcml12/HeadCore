from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class HeadAction(StrEnum):
    ANSWER = "answer"
    CLARIFY = "clarify"
    CONTINUE_TASK = "continue_task"
    REPAIR = "repair"
    SUPPORT = "support"
    REFUSE = "refuse"


class CommunicationAct(StrEnum):
    ANSWER_QUESTION = "answer_question"
    ACKNOWLEDGE = "acknowledge"
    CLARIFY = "clarify"
    EMOTIONAL_SUPPORT = "emotional_support"
    ACCEPT_CORRECTION = "accept_correction"
    CONTINUE_TASK = "continue_task"
    TOPIC_WITHDRAWAL = "topic_withdrawal"
    REQUEST_ADVICE = "request_advice"
    AVOID_ADVICE = "avoid_advice"


class FeedbackOutcome(StrEnum):
    ACCEPTED = "accepted"
    CORRECTED = "corrected"
    ADVICE_REJECTED = "advice_rejected"
    CONTINUED = "continued"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


class CognitiveFactStatus(StrEnum):
    ACTIVE = "active"
    CONFLICTED = "conflicted"
    STALE = "stale"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"


class CognitiveFactKind(StrEnum):
    OBSERVATION = "observation"
    BELIEF = "belief"
    HYPOTHESIS = "hypothesis"


class CognitiveFactSourceKind(StrEnum):
    WORLD_EVIDENCE = "world_evidence"
    USER_REPORT = "user_report"
    MODEL_INFERENCE = "model_inference"


class HeadEpisodeKind(StrEnum):
    TASK_STARTED = "task_started"
    TASK_UPDATED = "task_updated"
    QUESTION_ASKED = "question_asked"
    QUESTION_ANSWERED = "question_answered"
    FEEDBACK_RECEIVED = "feedback_received"


class WorldAssertionStatus(StrEnum):
    ACTIVE = "active"
    CONFLICTED = "conflicted"
    STALE = "stale"


class LongTermPlanStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


class PlanStepStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class ExecutionEvidenceSource(StrEnum):
    TEST_RUNNER = "test_runner"
    TOOL_RESULT = "tool_result"
    USER_CONFIRMATION = "user_confirmation"
    WORLD_EVENT = "world_event"
    MODEL_CLAIM = "model_claim"


@dataclass(frozen=True)
class HeadExecutionEvidence:
    evidence_id: str
    source: ExecutionEvidenceSource
    reference: str
    observed_at: str
    succeeded: bool
    expires_at: str | None = None


@dataclass(frozen=True)
class HeadPlanStep:
    step_id: str
    objective: str
    depends_on: tuple[str, ...] = ()
    completion_criteria: str = ""
    status: PlanStepStatus = PlanStepStatus.PENDING
    attempts: int = 0
    max_attempts: int = 2
    evidence: tuple[HeadExecutionEvidence, ...] = ()
    failure_reason: str | None = None


@dataclass(frozen=True)
class HeadLongTermPlan:
    plan_id: str
    goal: str
    steps: tuple[HeadPlanStep, ...]
    status: LongTermPlanStatus = LongTermPlanStatus.PENDING
    version: int = 1
    replan_count: int = 0
    max_replans: int = 2
    current_step_id: str | None = None


@dataclass(frozen=True)
class WorldEntity:
    entity_id: str
    entity_type: str
    name: str


@dataclass(frozen=True)
class WorldRelation:
    relation_id: str
    subject_id: str
    predicate: str
    object_id: str
    source_id: str
    valid_from: str
    valid_until: str | None
    confidence: float
    status: WorldAssertionStatus = WorldAssertionStatus.ACTIVE


@dataclass(frozen=True)
class WorldEvent:
    event_id: str
    event_type: str
    actor_ids: tuple[str, ...]
    occurred_at: str
    source_id: str
    summary: str
    confidence: float


@dataclass(frozen=True)
class CausalHypothesis:
    hypothesis_id: str
    cause_event_id: str
    effect_event_id: str
    rationale: str
    confidence: float
    evidence_ids: tuple[str, ...]
    confirmed: bool = False


@dataclass(frozen=True)
class HeadWorldModel:
    entities: tuple[WorldEntity, ...] = ()
    relations: tuple[WorldRelation, ...] = ()
    events: tuple[WorldEvent, ...] = ()
    causal_hypotheses: tuple[CausalHypothesis, ...] = ()
    uncertainties: tuple[str, ...] = ()


@dataclass(frozen=True)
class CognitiveFact:
    fact_id: str
    key: str
    value: str
    source_id: str
    observed_at: str
    expires_at: str
    confidence: float
    version: int = 1
    status: CognitiveFactStatus = CognitiveFactStatus.ACTIVE
    kind: CognitiveFactKind = CognitiveFactKind.OBSERVATION
    source_kind: CognitiveFactSourceKind = CognitiveFactSourceKind.WORLD_EVIDENCE
    supporting_source_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class LatentIntentHypothesis:
    kind: str
    confidence: float
    evidence: str
    needs_confirmation: bool = True


@dataclass(frozen=True)
class TurnTakingPolicy:
    response_length: str
    initiative: str
    question_budget: int
    advice_budget: int
    persona_intensity: float
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommunicationState:
    primary_act: CommunicationAct
    secondary_acts: tuple[CommunicationAct, ...]
    hypotheses: tuple[LatentIntentHypothesis, ...]
    turn_policy: TurnTakingPolicy


@dataclass(frozen=True)
class HeadReflection:
    mistake_type: str
    cause: str
    evidence: tuple[str, ...]
    better_action: str
    policy_candidate: str


@dataclass(frozen=True)
class HeadFeedback:
    previous_action: str
    outcome: FeedbackOutcome
    signals: tuple[str, ...]
    reflection: HeadReflection | None = None


@dataclass(frozen=True)
class HeadEventRecord:
    content: str
    created_at: str


@dataclass(frozen=True)
class HeadEpisodicEvent:
    event_id: str
    kind: HeadEpisodeKind
    summary: str
    occurred_at: str
    source_message_id: str


@dataclass(frozen=True)
class HeadAdaptivePolicy:
    active: bool = False
    version: int = 0
    evidence_count: int = 0
    advice_budget_cap: int | None = None
    clarification_bias: bool = False
    persona_intensity_cap: float | None = None
    reasons: tuple[str, ...] = ()
    expires_at: str | None = None


@dataclass(frozen=True)
class HeadDecision:
    action: HeadAction
    reason: str
    objective: str


@dataclass(frozen=True)
class HeadActionScore:
    intent_fit: float
    task_progress: float
    relationship_fit: float
    fact_reliability: float
    persona_consistency: float
    boundary_risk: float
    moralizing_risk: float
    fabrication_risk: float
    total: float


@dataclass(frozen=True)
class HeadCandidateAction:
    action: HeadAction
    reason: str
    objective: str
    score: HeadActionScore


@dataclass(frozen=True)
class HeadPlan:
    complex_scene: bool
    candidates: tuple[HeadCandidateAction, ...]
    selected_index: int
    rationale: str


@dataclass(frozen=True)
class HeadState:
    subject_id: str
    relationship_role: str
    current_topic: str
    user_state: str
    self_mood: str
    social_boundary: str
    active_task: str
    pending_question: str
    known_context: tuple[str, ...]
    uncertainties: tuple[str, ...]
    communication: CommunicationState
    feedback: HeadFeedback
    adaptive_policy: HeadAdaptivePolicy
    world_model: HeadWorldModel
    long_term_plan: HeadLongTermPlan | None
    plan: HeadPlan
    decision: HeadDecision


@dataclass(frozen=True)
class HeadEventContext:
    active_task: str = "none"
    pending_question: str = "none"
    last_action: str = "none"
    last_feedback: str = "none"
    feedback_events: tuple[HeadEventRecord, ...] = ()
    episodic_events: tuple[HeadEpisodicEvent, ...] = ()
    policy_reset_at: str | None = None
    cognitive_facts: tuple[CognitiveFact, ...] = ()
    world_model: HeadWorldModel = HeadWorldModel()
    long_term_plan: HeadLongTermPlan | None = None
