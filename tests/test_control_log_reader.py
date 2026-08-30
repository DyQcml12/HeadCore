from app.control.log_reader import LOG_TARGETS
from app.control.service_manager import SERVICE_SPECS


def test_control_log_targets_match_managed_service_log_names() -> None:
    for service_id, spec in SERVICE_SPECS.items():
        if service_id not in LOG_TARGETS:
            continue
        assert LOG_TARGETS[service_id].name == spec.log_name
