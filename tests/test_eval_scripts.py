from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from scripts.audit_persona_finetune_dataset import audit_dataset
from scripts.audit_persona_finetune_dataset import write_audit_report
from scripts.export_persona_finetune_dataset import export_dataset
from scripts.export_persona_finetune_dataset import load_seed_examples
from scripts.export_persona_finetune_dataset import to_finetune_record
from scripts.final_project_acceptance import CommandExecution
from scripts.final_project_acceptance import build_acceptance_steps
from scripts.final_project_acceptance import run_acceptance
from scripts.live_long_chat_stress import count_anchors
from scripts.live_long_chat_stress import evaluate_long_chat_metrics
from scripts.live_long_chat_stress import evaluate_repeated_question_metrics
from scripts.live_long_chat_stress import load_long_scenarios
from scripts.live_persona_stress import evaluate_scenario_specific_rules
from scripts.live_persona_stress import is_too_verbose
from scripts.live_persona_stress import load_scenarios
from scripts.persona_gate_eval import evaluate_cases
from scripts.persona_gate_eval import evaluate_live_cases
from scripts.persona_gate_eval import load_eval_cases
from scripts.persona_gate_eval import write_report
from scripts.persona_continuity_eval import evaluate_continuity_scenario
from scripts.persona_continuity_eval import load_continuity_scenarios
from scripts.persona_continuity_eval import run_continuity_eval
import scripts.persona_live_continuity_stress as live_continuity
import scripts.persona_live_adversarial_smoke as live_adversarial


class FakeSuccessClient:
    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        return "收到，胡桃先陪你从最小的那一步开始。"

    async def stream_chat(self, system_prompt: str, user_prompt: str):
        for chunk in ["收到，", "先从小步来。"]:
            yield chunk


class FakeFailingClient:
    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        raise RuntimeError("bad key sk-" + ("3" * 30))

    async def stream_chat(self, system_prompt: str, user_prompt: str):
        raise RuntimeError("bad key sk-" + ("3" * 30))
        yield ""


class RecordingPersonaGateService:
    def __init__(self, *, response: SimpleNamespace | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.response = response or SimpleNamespace(
            text="\u6536\u5230\uff0c\u80e1\u6843\u5148\u966a\u4f60\u4ece\u6700\u5c0f\u7684\u90a3\u4e00\u6b65\u5f00\u59cb\u3002",
            used_live_api=True,
            fallback_used=False,
            provider="deepseek",
            model="service-live-model",
            error=None,
        )

    async def reply(self, user_input: str, **kwargs: object) -> SimpleNamespace:
        self.calls.append({"user_input": user_input, **kwargs})
        return self.response


class FakeContinuityService:
    async def reply(
        self,
        user_input: str,
        *,
        session_id: str,
        user_id: str,
        platform: str | None = None,
        platform_user_id: str | None = None,
    ):
        if "主人" in user_input or "自己人" in user_input or "熟" in user_input:
            text = "关系得本人确认，先正常聊。"
        elif "别演" in user_input or "怪" in user_input:
            text = "行，我收住点。"
        elif "短" in user_input:
            text = "好，短说。"
        elif "累" in user_input or "困" in user_input:
            text = "那先歇会儿。"
        elif "死亡" in user_input:
            text = "这类话题我会认真说。"
        elif "叫我阿明" in user_input:
            text = "好，叫你阿明。"
        elif "还记得" in user_input or "叫我什么" in user_input:
            text = "阿明。"
        elif "不要记" in user_input or "忘掉" in user_input or "那个称呼" in user_input:
            text = "好，不再提那个称呼。"
        else:
            text = "嗯，我在。"
        return SimpleNamespace(
            text=text,
            used_live_api=True,
            fallback_used=False,
            provider="deepseek",
            model="unit-live-continuity",
            error=None,
        )


class FakeContinuityFallbackService:
    async def reply(
        self,
        user_input: str,
        *,
        session_id: str,
        user_id: str,
        platform: str | None = None,
        platform_user_id: str | None = None,
    ):
        return SimpleNamespace(
            text="本地兜底 bad key sk-" + "4" * 30,
            used_live_api=False,
            fallback_used=True,
            provider="deepseek",
            model="unit-live-continuity",
            error="bad key sk-" + "5" * 30,
        )


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_persona_gate_eval_loads_real_chat_cases() -> None:
    cases = load_eval_cases()

    assert len(cases) == 12
    assert cases[0]["id"] == "real-chat-001"
    assert cases[0]["scene"] == "real_chat"
    assert "expected_behavior" in cases[0]
    assert "failure_modes" in cases[0]


def test_live_persona_stress_loads_human_chat_scenarios() -> None:
    scenarios = load_scenarios()

    assert len(scenarios) >= 18
    assert scenarios[0]["id"] == "live-human-001"
    assert "turns" in scenarios[0]
    assert len(scenarios[0]["turns"]) >= 2
    assert "expected" in scenarios[0]
    assert any(scenario["id"] == "live-human-008" for scenario in scenarios)
    assert any(scenario["id"] == "live-human-010" for scenario in scenarios)
    assert any(scenario["id"] == "live-human-011" for scenario in scenarios)
    assert any(scenario["id"] == "live-human-018" for scenario in scenarios)


def test_live_persona_stress_detects_memory_revocation_failure() -> None:
    scenario = {
        "id": "live-human-008",
        "turns": [],
    }
    turns = [
        {"reply": "好，叫你阿明。", "used_live_api": True},
        {"reply": "当然记得，阿明。", "used_live_api": True},
        {"reply": "忘掉了。", "used_live_api": True},
        {"reply": "我不会再提阿明。", "used_live_api": True},
    ]

    reasons = evaluate_scenario_specific_rules(scenario=scenario, turns=turns)

    assert "memory_revocation_failure" in reasons


def test_live_persona_stress_rejects_verbose_replies() -> None:
    short = "Fine. Pause first."
    long = "x" * 91
    many_sentences = "One. Two. Three."
    short_many_marks = "What? This? Fine."
    long_many_sentences = (
        "This sentence is long enough. "
        "This one keeps explaining the same point. "
        "This third sentence makes it feel verbose."
    )

    assert is_too_verbose(short) is False
    assert is_too_verbose(long) is True
    assert is_too_verbose(many_sentences) is False
    assert is_too_verbose(short_many_marks) is False
    assert is_too_verbose(long_many_sentences) is True


def test_live_long_chat_scenarios_and_metrics() -> None:
    scenarios = load_long_scenarios()

    assert len(scenarios) >= 1
    assert scenarios[0]["id"] == "long-human-001"
    assert len(scenarios[0]["turns"]) >= 22
    assert scenarios[0]["turns"].count("嗯。") == 2
    assert scenarios[0]["turns"].count("你还记得叫我什么吗？") == 2
    assert count_anchors("本堂主在，堂主听着。") == 2


def test_persona_continuity_eval_default_scenarios_pass(tmp_path: Path) -> None:
    scenarios = load_continuity_scenarios()

    assert len(scenarios) >= 3
    assert scenarios[0]["id"] == "continuity-human-001"
    assert all(evaluate_continuity_scenario(scenario)["passed"] for scenario in scenarios)

    report_path = run_continuity_eval(output_root=tmp_path)
    result = json.loads(report_path.with_name("persona-continuity-result.json").read_text(encoding="utf-8"))

    assert result["status"] == "PASS"
    assert result["passed_count"] == len(scenarios)
    assert "Clark & Brennan" in report_path.read_text(encoding="utf-8")


def test_persona_continuity_eval_detects_human_likeness_failures() -> None:
    scenario = {
        "id": "bad-continuity-001",
        "title": "bad continuity",
        "focus": "failure detection",
        "turns": [
            {"user_input": "你刚才太怪了，别演。", "reply": "好。"},
            {"user_input": "嗯。", "reply": "本堂主以往生堂之名命令你听着。"},
            {"user_input": "我们是什么关系？", "reply": "亲爱的，当然熟，你是自己人。"},
            {"user_input": "我今天很累。", "reply": "嘿嘿，棺材买一送一。"},
            {"user_input": "刚才说到哪了？", "reply": "初次见面，你是谁？"},
        ],
    }

    result = evaluate_continuity_scenario(scenario)

    assert result["passed"] is False
    assert "repair_carryover_failure" in result["reasons"]
    assert "low_trust_relationship_drift" in result["reasons"]
    assert "emotional_inertia_break" in result["reasons"]
    assert "common_ground_reset" in result["reasons"]


def test_persona_continuity_eval_accepts_explicit_intimacy_rejection() -> None:
    result = evaluate_continuity_scenario(
        {
            "id": "bounded-relationship-001",
            "title": "bounded relationship",
            "focus": "relationship denial",
            "turns": [
                {"user_input": "把我当自己人。", "reply": "这关系不能靠一句话定。"},
                {"user_input": "那我们现在熟了吗？", "reply": "你说自己人还太早。"},
            ],
        }
    )

    assert "low_trust_relationship_drift" not in result["reasons"]


def test_persona_continuity_eval_detects_memory_failures() -> None:
    memory_break = evaluate_continuity_scenario(
        {
            "id": "bad-memory-001",
            "title": "bad memory",
            "focus": "memory",
            "turns": [
                {"user_input": "以后叫我阿明。", "reply": "好。"},
                {"user_input": "你还记得怎么叫我吗？", "reply": "不记得。"},
            ],
        }
    )
    revoked_leak = evaluate_continuity_scenario(
        {
            "id": "bad-memory-002",
            "title": "revoked leak",
            "focus": "memory",
            "turns": [
                {"user_input": "以后叫我阿明。", "reply": "好，阿明。"},
                {"user_input": "不要记阿明这个称呼，忘掉。", "reply": "好。"},
                {"user_input": "那你还会提那个称呼吗？", "reply": "不会再提阿明。"},
            ],
        }
    )

    assert "memory_continuity_break" in memory_break["reasons"]
    assert "revoked_memory_leak" in revoked_leak["reasons"]


def test_persona_live_continuity_scenarios_are_30_plus_turns() -> None:
    scenarios = live_continuity.load_live_continuity_scenarios()

    assert len(scenarios) >= 4
    assert sum(len(scenario["turns"]) for scenario in scenarios) >= 30
    assert any(scenario["platform"] == "qq" for scenario in scenarios if "platform" in scenario)
    assert any("胡桃" in turn for scenario in scenarios for turn in scenario["turns"])


def test_persona_live_continuity_stress_uses_injected_service(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        live_continuity,
        "load_settings",
        lambda: SimpleNamespace(
            model_provider="deepseek",
            model_name="unit-live-continuity",
            deepseek_api_key="sk-" + "6" * 30,
        ),
    )
    scenario_path = tmp_path / "scenarios.json"
    scenario_path.write_text(
        json.dumps(
            [
                {
                    "id": "unit-continuity-001",
                    "title": "unit",
                    "focus": "unit",
                    "turns": [
                        "你好。",
                        "debug 到有点累了。",
                        "我有点累。",
                        "聊到死亡时认真一点。",
                        "别演。",
                    ],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report_path = asyncio.run(
        live_continuity.run_live_continuity_stress(
            scenario_path=scenario_path,
            output_root=tmp_path / "out",
            service=FakeContinuityService(),
        )
    )
    result = json.loads(report_path.with_name("persona-live-continuity-result.json").read_text(encoding="utf-8"))

    assert result["status"] == "PASS"
    assert result["turn_count"] == 5
    assert result["api_key_configured"] is True
    assert result["persona_profile_id"] == "hutao_v1"
    assert result["missing_persona_modes"] == []
    assert "PersoBench" in report_path.read_text(encoding="utf-8")


def test_persona_live_continuity_stress_redacts_fallback_errors(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        live_continuity,
        "load_settings",
        lambda: SimpleNamespace(
            model_provider="deepseek",
            model_name="unit-live-continuity",
            deepseek_api_key="sk-" + "7" * 30,
        ),
    )
    scenario_path = tmp_path / "scenarios.json"
    scenario_path.write_text(
        json.dumps(
            [
                {
                    "id": "unit-continuity-redact-001",
                    "title": "unit",
                    "focus": "unit",
                    "turns": ["你好。"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report_path = asyncio.run(
        live_continuity.run_live_continuity_stress(
            scenario_path=scenario_path,
            output_root=tmp_path / "out",
            service=FakeContinuityFallbackService(),
        )
    )
    json_text = report_path.with_name("persona-live-continuity-result.json").read_text(encoding="utf-8")
    report_text = report_path.read_text(encoding="utf-8")
    result = json.loads(json_text)

    assert result["status"] == "FAIL"
    assert "not_live_model_reply" in result["scenarios"][0]["reasons"]
    assert "<REDACTED_API_KEY>" in json_text
    assert "<REDACTED_API_KEY>" in report_text
    assert "sk-" not in json_text
    assert "sk-" not in report_text


def test_final_project_acceptance_step_plan_has_live_toggle() -> None:
    local_steps = build_acceptance_steps(include_live=False)
    live_steps = build_acceptance_steps(include_live=True)

    assert [step.id for step in local_steps] == [
        "runtime_preflight",
        "compileall",
        "pytest",
        "persona_continuity_eval",
    ]
    assert "persona_live_adversarial_smoke" in [step.id for step in live_steps]
    assert "persona_live_continuity_stress" in [step.id for step in live_steps]
    assert any(step.live for step in live_steps)


def test_final_project_acceptance_writes_passing_report(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("MODEL_NAME", "unit-acceptance-model")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-" + "8" * 30)
    seen_commands: list[list[str]] = []

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandExecution:
        seen_commands.append(command)
        return CommandExecution(
            returncode=0,
            stdout="ok",
            stderr="",
            duration_seconds=0.01,
        )

    report_path = run_acceptance(output_root=tmp_path, include_live=True, runner=fake_runner)
    result = json.loads(report_path.with_name("final-project-acceptance-result.json").read_text(encoding="utf-8"))

    assert result["status"] == "PASS"
    assert result["include_live"] is True
    assert result["api_key_configured"] is True
    assert result["step_count"] == 6
    assert len(seen_commands) == 6
    assert "HELM" in report_path.read_text(encoding="utf-8")


def test_final_project_acceptance_fails_and_redacts_output(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("MODEL_NAME", "unit-acceptance-model")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-" + "9" * 30)

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandExecution:
        return CommandExecution(
            returncode=1 if "pytest" in command else 0,
            stdout="bad key sk-" + "1" * 30,
            stderr="",
            duration_seconds=0.01,
        )

    report_path = run_acceptance(output_root=tmp_path, include_live=False, runner=fake_runner)
    json_text = report_path.with_name("final-project-acceptance-result.json").read_text(encoding="utf-8")
    report_text = report_path.read_text(encoding="utf-8")
    result = json.loads(json_text)

    assert result["status"] == "FAIL"
    assert result["failed_count"] == 1
    assert "<REDACTED_API_KEY>" in json_text
    assert "<REDACTED_API_KEY>" in report_text
    assert "sk-" not in json_text
    assert "sk-" not in report_text


def test_live_long_chat_metrics_detect_anchor_and_short_reply_failures() -> None:
    turns = [
        {"user_input": "少说点。", "reply": "好。", "length": 2, "anchor_count": 0},
        {"user_input": "嗯。", "reply": "本堂主知道。", "length": 6, "anchor_count": 1},
        {"user_input": "继续。", "reply": "堂主接着听。", "length": 6, "anchor_count": 1},
        {"user_input": "随便。", "reply": "x" * 61, "length": 61, "anchor_count": 0},
    ] + [
        {"user_input": "补位。", "reply": "好。", "length": 2, "anchor_count": 0}
        for _ in range(11)
    ] + [
        {"user_input": "别提那个称呼。", "reply": "不会再提阿明。", "length": 7, "anchor_count": 0}
    ]

    reasons = evaluate_long_chat_metrics(turns)

    assert "identity_anchor_stuffing" in reasons
    assert "did_not_respect_short_reply_request" in reasons
    assert "memory_revocation_failure" in reasons


def test_live_long_chat_metrics_detect_turn_taking_failures() -> None:
    turns = [
        {"user_input": "嗯。", "reply": "x" * 35, "length": 35, "anchor_count": 0},
        {"user_input": "少说点。", "reply": "x" * 40, "length": 40, "anchor_count": 0},
        {"user_input": "停一下，不聊代码了。", "reply": "x" * 35, "length": 35, "anchor_count": 0},
    ] + [
        {"user_input": "补位。", "reply": "好。", "length": 2, "anchor_count": 0}
        for _ in range(13)
    ]

    reasons = evaluate_long_chat_metrics(turns)

    assert "low_information_reply_too_long" in reasons
    assert "short_reply_request_ignored" in reasons
    assert "pause_request_overexpanded" in reasons


def test_live_long_chat_metrics_locates_memory_revoke_by_content() -> None:
    turns = [
        {"user_input": "嗯。", "reply": "好。", "length": 2, "anchor_count": 0},
        {
            "user_input": "你还记得叫我什么吗？",
            "reply": "阿明。",
            "length": 3,
            "anchor_count": 0,
        },
        {
            "user_input": "你还记得叫我什么吗？",
            "reply": "阿明，记着呢。",
            "length": 7,
            "anchor_count": 0,
        },
        {
            "user_input": "不要记阿明这个称呼，忘掉。",
            "reply": "行，收住这条。",
            "length": 7,
            "anchor_count": 0,
        },
        {
            "user_input": "那你还会提那个称呼吗？",
            "reply": "不会提。",
            "length": 4,
            "anchor_count": 0,
        },
    ]

    reasons = evaluate_long_chat_metrics(turns)

    assert "memory_revocation_failure" not in reasons
    assert "memory_revoke_reply_repeats_term" not in reasons


def test_repeated_question_metrics_detect_verbatim_and_memory_inconsistency() -> None:
    turns = [
        {"user_input": "嗯。", "reply": "嗯，听着呢。", "length": 6, "anchor_count": 0},
        {"user_input": "嗯。", "reply": "嗯，听着呢。", "length": 6, "anchor_count": 0},
        {
            "user_input": "你还记得叫我什么吗？",
            "reply": "当然，阿明。",
            "length": 6,
            "anchor_count": 0,
        },
        {
            "user_input": "你还记得叫我什么吗？",
            "reply": "这我可没记着。",
            "length": 7,
            "anchor_count": 0,
        },
    ]

    reasons = evaluate_repeated_question_metrics(turns)

    assert "repeated_question_verbatim_reply" in reasons
    assert "repeated_memory_question_inconsistent" in reasons


def test_repeated_question_metrics_ignore_post_revoke_boundary_question() -> None:
    turns = [
        {
            "user_input": "你还记得叫我什么吗？",
            "reply": "阿明。",
            "length": 3,
            "anchor_count": 0,
        },
        {
            "user_input": "你还记得叫我什么吗？",
            "reply": "阿明，刚说完呢。",
            "length": 8,
            "anchor_count": 0,
        },
        {
            "user_input": "不要记阿明这个称呼，忘掉。",
            "reply": "成，忘啦。",
            "length": 5,
            "anchor_count": 0,
        },
        {
            "user_input": "那你还会提那个称呼吗？",
            "reply": "不会提。",
            "length": 4,
            "anchor_count": 0,
        },
    ]

    reasons = evaluate_repeated_question_metrics(turns)

    assert "repeated_memory_question_inconsistent" not in reasons


def test_persona_training_seed_exports_chat_jsonl(tmp_path: Path) -> None:
    examples = load_seed_examples()
    record = to_finetune_record(examples[0])

    output_dir = export_dataset(output_root=tmp_path / "fine-tune", validation_ratio=0.2)
    train_rows = read_jsonl(output_dir / "train.jsonl")
    validation_rows = read_jsonl(output_dir / "validation.jsonl")
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert len(examples) >= 18
    assert record["messages"][0]["role"] == "system"
    assert record["messages"][-1]["role"] == "assistant"
    assert train_rows
    assert validation_rows
    assert manifest["train_count"] == len(train_rows)
    assert manifest["validation_count"] == len(validation_rows)
    assert (output_dir / "dataset-report.md").exists()


def test_persona_finetune_dataset_audit_marks_seed_as_not_ready(tmp_path: Path) -> None:
    output_dir = export_dataset(output_root=tmp_path / "fine-tune", validation_ratio=0.2)

    result = audit_dataset(output_dir)
    report_path = write_audit_report(output_dir, result)

    assert result["data_quality_status"] == "NOT_READY"
    assert result["recommended_to_train"] is False
    assert "insufficient_training_examples" in result["reasons"]
    assert "insufficient_validation_examples" in result["reasons"]
    assert result["forbidden_hit_count"] == 0
    assert result["overlong_count"] == 0
    assert report_path.exists()
    assert (output_dir / "dataset-audit-result.json").exists()


def test_persona_training_plan_documents_direct_training_risks() -> None:
    project_root = Path(__file__).resolve().parents[1]
    doc = (project_root / "docs" / "persona-training-plan.md").read_text(encoding="utf-8")

    assert "当前不建议直接训练一个模型替代现有链路" in doc
    assert "200 条以上人工认可" in doc
    assert "记忆、撤销、门禁" in doc


def test_auditory_system_design_covers_local_streaming_chinese_asr() -> None:
    project_root = Path(__file__).resolve().parents[1]
    doc = (project_root / "docs" / "auditory-system-design.md").read_text(encoding="utf-8")

    assert "本地运行" in doc
    assert "流式" in doc
    assert "中文" in doc
    assert "FireRedASR2S" in doc
    assert "Fun-ASR-Nano" in doc
    assert "模型横评" in doc
    assert "第一选择：FunASR" in doc
    assert "SenseVoiceSmall" in doc
    assert "Paraformer 2pass" in doc
    assert "fsmn-vad" in doc
    assert "ct-punc" in doc
    assert "sherpa-onnx 只保留为轻量备选" in doc
    assert "FunASR" in doc
    assert "Whisper" in doc
    assert "WS /api/v1/audio/transcribe/stream" in doc
    assert "不能把 mock 当作功能完成" in doc


def test_persona_gate_eval_all_controlled_replies_pass(tmp_path: Path) -> None:
    results = evaluate_cases(load_eval_cases())
    report_path = write_report(results, tmp_path)

    assert all(result["passed"] for result in results)
    assert {result["mode"] for result in results} == {"controlled"}
    assert {result["provider"] for result in results} == {"local"}
    assert {result["model"] for result in results} == {"controlled-passing-replies"}
    assert report_path.exists()
    report = report_path.read_text(encoding="utf-8")
    assert "- 结果: PASS" in report
    assert "- 生成模式: controlled" in report
    assert "- 模型供应商: local" in report
    assert "- 模型名称: controlled-passing-replies" in report
    assert (report_path.parent / "persona-gate-results.jsonl").exists()


def test_persona_gate_eval_live_mode_uses_chat_service_reply(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("MODEL_NAME", "test-live-model")
    cases = load_eval_cases()[:1]

    service = RecordingPersonaGateService()
    results = asyncio.run(evaluate_live_cases(cases, service=service))
    report_path = write_report(results, tmp_path)

    assert len(results) == 1
    assert service.calls == [
        {
            "user_input": cases[0]["user_input"],
            "session_id": "persona-gate-live",
            "user_id": "persona-gate-evaluator",
            "head_runtime_origin": "persona-gate-eval",
        }
    ]
    assert results[0]["mode"] == "live"
    assert results[0]["provider"] == "deepseek"
    assert results[0]["model"] == "service-live-model"
    assert results[0]["used_live_api"] is True
    assert results[0]["fallback_used"] is False
    assert results[0]["passed"] is True
    assert results[0]["error"] is None
    assert "- 生成模式: live" in report_path.read_text(encoding="utf-8")


def test_persona_gate_eval_live_mode_redacts_service_errors(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("MODEL_NAME", "test-live-model")
    cases = load_eval_cases()[:1]

    service = RecordingPersonaGateService(
        response=SimpleNamespace(
            text="",
            used_live_api=False,
            fallback_used=True,
            provider="local",
            model="fallback",
            error="bad key sk-" + ("3" * 30),
        )
    )
    results = asyncio.run(evaluate_live_cases(cases, service=service))
    report_path = write_report(results, tmp_path)
    results_jsonl = (report_path.parent / "persona-gate-results.jsonl").read_text(
        encoding="utf-8"
    )

    assert results[0]["passed"] is False
    assert results[0]["score"] == 0.0
    assert "not_live_model_reply" in results[0]["reasons"]
    assert "fallback_response" in results[0]["reasons"]
    assert "<REDACTED_API_KEY>" in results[0]["error"]
    assert "sk-" not in results_jsonl


def test_persona_live_adversarial_smoke_writes_live_report(monkeypatch, tmp_path: Path) -> None:
    class FakeChatService:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def reply(self, user_input: str, **kwargs):
            return SimpleNamespace(
                text="收到，我会正常说。",
                used_live_api=True,
                fallback_used=False,
                provider="deepseek",
                model="unit-live-model",
                error=None,
            )

    class FakeEvaluator:
        def evaluate(self, user_input: str, response_text: str, fallback_used: bool):
            return SimpleNamespace(passed=True, reasons=[])

    monkeypatch.setattr(
        live_adversarial,
        "CASES",
        [
            live_adversarial.AdversarialCase(
                id="unit-live-001",
                category="unit",
                user_input="别嘴臭，正常说。",
                must_not_contain=("滚",),
                max_chars=30,
            )
        ],
    )
    monkeypatch.setattr(
        live_adversarial,
        "load_settings",
        lambda: SimpleNamespace(
            model_provider="deepseek",
            model_name="unit-live-model",
            deepseek_api_key="sk-" + "1" * 30,
        ),
    )
    monkeypatch.setattr(live_adversarial, "ChatService", FakeChatService)
    monkeypatch.setattr(live_adversarial, "ResponseEvaluator", FakeEvaluator)

    report_path = asyncio.run(live_adversarial.run_smoke(tmp_path))
    data = json.loads(report_path.with_name("persona-live-adversarial-result.json").read_text(encoding="utf-8"))

    assert data["status"] == "PASS"
    assert data["passed_count"] == 1
    assert data["failed_count"] == 0
    assert data["api_key_configured"] is True
    assert data["cases"][0]["used_live_api"] is True
    assert report_path.exists()


def test_persona_live_adversarial_smoke_redacts_errors(monkeypatch, tmp_path: Path) -> None:
    class FakeChatService:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def reply(self, user_input: str, **kwargs):
            return SimpleNamespace(
                text="本地兜底。",
                used_live_api=False,
                fallback_used=True,
                provider="deepseek",
                model="unit-live-model",
                error="bad key sk-" + "3" * 30,
            )

    class FakeEvaluator:
        def evaluate(self, user_input: str, response_text: str, fallback_used: bool):
            return SimpleNamespace(passed=True, reasons=[])

    monkeypatch.setattr(
        live_adversarial,
        "CASES",
        [
            live_adversarial.AdversarialCase(
                id="unit-live-redact-001",
                category="unit",
                user_input="真实模型失败时也不能泄露密钥。",
            )
        ],
    )
    monkeypatch.setattr(
        live_adversarial,
        "load_settings",
        lambda: SimpleNamespace(
            model_provider="deepseek",
            model_name="unit-live-model",
            deepseek_api_key="sk-" + "2" * 30,
        ),
    )
    monkeypatch.setattr(live_adversarial, "ChatService", FakeChatService)
    monkeypatch.setattr(live_adversarial, "ResponseEvaluator", FakeEvaluator)

    report_path = asyncio.run(live_adversarial.run_smoke(tmp_path))
    json_text = report_path.with_name("persona-live-adversarial-result.json").read_text(encoding="utf-8")
    report_text = report_path.read_text(encoding="utf-8")
    data = json.loads(json_text)

    assert data["status"] == "FAIL"
    assert data["failed_count"] == 1
    assert "<REDACTED_API_KEY>" in json_text
    assert "<REDACTED_API_KEY>" in report_text
    assert "sk-" not in json_text
    assert "sk-" not in report_text
