"""
Unit tests for Windows Automation Service:
Allowlist enforcement, parameter validation, URL security, system telemetry, and audit logging.
"""

from unittest.mock import patch
import pytest

from automation_service import APPROVED_APPS, PRESET_WORKFLOWS, WindowsAutomationService


def test_approved_apps_allowlist():
    svc = WindowsAutomationService()
    allowed = svc.get_allowed_apps()
    assert len(allowed) >= 5
    app_ids = [a.id for a in allowed]
    assert "notepad" in app_ids
    assert "calculator" in app_ids
    assert "explorer" in app_ids


def test_unapproved_app_rejected():
    svc = WindowsAutomationService()
    res = svc.launch_app("malicious_tool.exe")
    assert res.success is False
    assert "Access Denied" in res.message


def test_sensitive_app_requires_confirmation():
    svc = WindowsAutomationService()
    # Task Manager requires confirmation by default
    res = svc.launch_app("taskmgr", user_confirmed=False)
    assert res.success is False
    assert "confirmation" in res.message.lower()


@patch("subprocess.Popen")
def test_safe_app_launch_mocked(mock_popen):
    svc = WindowsAutomationService()
    res = svc.launch_app("notepad", user_confirmed=True)
    assert res.success is True
    assert mock_popen.called
    # Ensure shell=False was used
    assert mock_popen.call_args.kwargs.get("shell") is False


def test_url_security_validation():
    svc = WindowsAutomationService()

    # Reject dangerous protocols
    res1 = svc.open_url("javascript:alert(1)")
    assert res1.success is False
    assert "Security violation" in res1.message

    res2 = svc.open_url("file:///C:/Windows/System32/cmd.exe")
    assert res2.success is False
    assert "Security violation" in res2.message

    # Empty URL
    res3 = svc.open_url("")
    assert res3.success is False


@patch("webbrowser.open")
def test_valid_url_launch_mocked(mock_web_open):
    svc = WindowsAutomationService()
    res = svc.open_url("https://github.com", user_confirmed=True)
    assert res.success is True
    assert mock_web_open.called
    assert "https://github.com" in mock_web_open.call_args[0][0]


def test_system_status():
    svc = WindowsAutomationService()
    res = svc.get_system_status()
    assert res.success is True
    assert "os" in res.data
    assert "cpu_count" in res.data
    assert "disk_total_gb" in res.data
    assert res.data["cpu_count"] > 0


def test_workflow_execution_mocked():
    svc = WindowsAutomationService()
    with patch.object(svc, "launch_app") as mock_launch, patch.object(svc, "open_url") as mock_url:
        mock_launch.return_value.success = True
        mock_launch.return_value.to_dict.return_value = {"success": True}
        mock_url.return_value.success = True
        mock_url.return_value.to_dict.return_value = {"success": True}

        res = svc.execute_workflow("dev_workspace", user_confirmed=True)
        assert res.success is True
        assert len(res.data["steps"]) == 2


def test_audit_log_tracking():
    svc = WindowsAutomationService()
    svc.launch_app("non_existent_app")
    svc.open_url("javascript:void(0)")
    logs = svc.get_audit_log()
    assert len(logs) == 2
    assert logs[0].action == "launch_app"
    assert logs[1].action == "open_url"
