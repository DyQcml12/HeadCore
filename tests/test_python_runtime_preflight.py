from scripts.python_runtime_preflight import classify_import_error


def test_runtime_preflight_classifies_policy_and_missing_module_errors() -> None:
    assert classify_import_error(
        ImportError("DLL load failed: 应用程序控制策略已阻止此文件")
    ) == "code_integrity_blocked"
    assert classify_import_error(
        ModuleNotFoundError("No module named 'fastapi'")
    ) == "module_missing"
