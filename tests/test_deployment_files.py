from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_staging_deployment_keeps_services_private_and_image_small() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (PROJECT_ROOT / "deploy" / "compose.staging.yml").read_text(encoding="utf-8")
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "USER hutao" in dockerfile
    assert "127.0.0.1:8000:8000" in compose
    assert "MYSQL_HOST: mysql" in compose
    assert "ports:" not in compose.split("  mysql:", 1)[1].split("volumes:", 1)[0]
    assert ".env" in dockerignore
    assert "model_training/" in dockerignore
    assert "external/" in dockerignore


def test_git_ignore_excludes_deployment_secrets_and_runtime_data() -> None:
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert ".env" in gitignore
    assert "deploy/.env.staging" in gitignore
    assert "model_training/" in gitignore
    assert "logs/" in gitignore


def test_current_environment_template_excludes_retired_bot_configuration() -> None:
    template = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    for retired_prefix in ("QQ_", "WEIXIN", "HERMES", "NAPCAT", "ONEBOT"):
        assert retired_prefix not in template
