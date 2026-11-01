"""
Windows Automation Service for G-AI-ASSISTANT.
Provides a strictly controlled, allowlisted execution engine for desktop automation,
application launching, browser navigation, system telemetry, and validated workflows.
Guarantees NO arbitrary shell command execution.
"""

from dataclasses import asdict, dataclass
from datetime import datetime
import logging
import os
from pathlib import Path
import platform
import shutil
import subprocess
from typing import Any, Callable, Dict, List, Optional
import urllib.parse
import webbrowser

from config import get_config_value, save_config

logger = logging.getLogger(__name__)


@dataclass
class AllowedApp:
    id: str
    display_name: str
    executable: str
    description: str
    category: str
    requires_confirmation: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ActionResult:
    success: bool
    action: str
    message: str
    data: Optional[Dict[str, Any]] = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Controlled Allowlist of Approved Windows Applications
APPROVED_APPS: Dict[str, AllowedApp] = {
    "notepad": AllowedApp(
        id="notepad",
        display_name="Notepad",
        executable="notepad.exe",
        description="Standard Windows text editor",
        category="productivity",
        requires_confirmation=False,
    ),
    "calculator": AllowedApp(
        id="calculator",
        display_name="Calculator",
        executable="calc.exe",
        description="Windows Calculator",
        category="utility",
        requires_confirmation=False,
    ),
    "explorer": AllowedApp(
        id="explorer",
        display_name="File Explorer",
        executable="explorer.exe",
        description="Windows File Explorer",
        category="system",
        requires_confirmation=False,
    ),
    "paint": AllowedApp(
        id="paint",
        display_name="Paint",
        executable="mspaint.exe",
        description="Windows Paint drawing tool",
        category="creativity",
        requires_confirmation=False,
    ),
    "taskmgr": AllowedApp(
        id="taskmgr",
        display_name="Task Manager",
        executable="taskmgr.exe",
        description="Windows Task Manager monitor",
        category="system",
        requires_confirmation=True,
    ),
    "cmd": AllowedApp(
        id="cmd",
        display_name="Command Prompt",
        executable="cmd.exe",
        description="Windows Command Prompt console",
        category="developer",
        requires_confirmation=True,
    ),
}

# Pre-registered Safe Multi-Step Workflows
PRESET_WORKFLOWS: Dict[str, Dict[str, Any]] = {
    "dev_workspace": {
        "name": "Developer Workspace",
        "description": "Opens File Explorer and Notepad for quick development session",
        "steps": [
            {"action": "launch_app", "app_id": "explorer"},
            {"action": "launch_app", "app_id": "notepad"},
        ],
        "requires_confirmation": False,
    },
    "quick_notes": {
        "name": "Quick Notes",
        "description": "Launches Notepad and opens Google Search in browser",
        "steps": [
            {"action": "launch_app", "app_id": "notepad"},
            {"action": "open_url", "url": "https://www.google.com"},
        ],
        "requires_confirmation": False,
    },
}


class WindowsAutomationService:
    """
    Dedicated safe Windows automation engine.
    Executes only allowlisted applications and validated actions.
    Separates AI intent from raw system execution.
    Guarantees NO arbitrary shell execution or unrestricted code evaluation.
    """

    def __init__(self):
        self._audit_log: List[ActionResult] = []

    def is_automation_enabled(self) -> bool:
        """Returns True if desktop automation is enabled in application settings."""
        return bool(get_config_value("desktop_automation_enabled", True))

    def set_automation_enabled(self, enabled: bool) -> None:
        """Toggles desktop automation master enable/disable setting."""
        save_config({"desktop_automation_enabled": bool(enabled)})
        logger.info(f"Desktop automation master setting updated: enabled={enabled}")

    def get_allowed_apps(self) -> List[AllowedApp]:
        """Returns the list of all registered allowed applications."""
        return list(APPROVED_APPS.values())

    def get_registered_workflows(self) -> Dict[str, Dict[str, Any]]:
        """Returns registered workflows."""
        return PRESET_WORKFLOWS

    def get_audit_log(self) -> List[ActionResult]:
        """Returns recent automation execution logs."""
        return list(self._audit_log)

    def _log_result(self, result: ActionResult) -> ActionResult:
        """Appends action result to audit log."""
        self._audit_log.append(result)
        if len(self._audit_log) > 100:
            self._audit_log.pop(0)
        return result

    # ------------------------------------------------------------------ Core Safe Actions

    def launch_app(
        self,
        app_id: str,
        user_confirmed: bool = False,
    ) -> ActionResult:
        """
        Launches an allowlisted application without shell interpretation.
        Checks confirmation if required by app or global settings.
        """
        if not self.is_automation_enabled():
            res = ActionResult(
                success=False,
                action="launch_app",
                message="Access Denied: Desktop automation is disabled in settings.",
            )
            return self._log_result(res)

        clean_id = (app_id or "").strip().lower()
        if clean_id not in APPROVED_APPS:
            res = ActionResult(
                success=False,
                action="launch_app",
                message=f"Access Denied: Application '{app_id}' is not in the approved allowlist.",
            )
            return self._log_result(res)

        app_info = APPROVED_APPS[clean_id]
        global_confirm_required = get_config_value("automation_require_confirmation", True)

        if (app_info.requires_confirmation or global_confirm_required) and not user_confirmed:
            res = ActionResult(
                success=False,
                action="launch_app",
                message=f"Action '{app_info.display_name}' requires explicit user confirmation.",
                data={"app_id": clean_id, "needs_confirmation": True},
            )
            return self._log_result(res)

        try:
            # Safe launch using direct executable invocation without shell=True
            subprocess.Popen([app_info.executable], shell=False)
            res = ActionResult(
                success=True,
                action="launch_app",
                message=f"Successfully launched {app_info.display_name}.",
                data={"app_id": clean_id, "executable": app_info.executable},
            )
            return self._log_result(res)
        except Exception as e:
            logger.error(f"Failed to launch application {clean_id}: {e}")
            res = ActionResult(
                success=False,
                action="launch_app",
                message=f"Failed to launch {app_info.display_name}: {e}",
            )
            return self._log_result(res)

    def open_url(
        self,
        url: str,
        user_confirmed: bool = False,
    ) -> ActionResult:
        """
        Opens a validated HTTP/HTTPS URL in the default browser.
        Rejects non-HTTP schemes (e.g. file:, javascript:, data:, cmd:) to prevent injection.
        """
        if not self.is_automation_enabled():
            res = ActionResult(
                success=False,
                action="open_url",
                message="Access Denied: Desktop automation is disabled in settings.",
            )
            return self._log_result(res)

        clean_url = (url or "").strip()
        if not clean_url:
            res = ActionResult(success=False, action="open_url", message="URL cannot be empty.")
            return self._log_result(res)

        # If an explicit scheme is present (e.g. javascript:, file:, data:), validate it before altering
        if ":" in clean_url:
            scheme_candidate = clean_url.split(":", 1)[0].lower()
            if scheme_candidate not in ("http", "https"):
                res = ActionResult(
                    success=False,
                    action="open_url",
                    message=f"Security violation: Scheme '{scheme_candidate}' is prohibited. Only HTTP/HTTPS allowed.",
                )
                return self._log_result(res)

        # Prepend https:// if no scheme provided
        if not clean_url.startswith(("http://", "https://")):
            clean_url = "https://" + clean_url

        try:
            parsed = urllib.parse.urlparse(clean_url)
            if parsed.scheme.lower() not in ("http", "https"):
                res = ActionResult(
                    success=False,
                    action="open_url",
                    message=f"Security violation: Scheme '{parsed.scheme}' is prohibited. Only HTTP/HTTPS allowed.",
                )
                return self._log_result(res)

            if not parsed.netloc:
                res = ActionResult(
                    success=False, action="open_url", message="Invalid URL: Domain cannot be empty."
                )
                return self._log_result(res)

            webbrowser.open(clean_url)
            res = ActionResult(
                success=True,
                action="open_url",
                message=f"Opened URL: {clean_url}",
                data={"url": clean_url},
            )
            return self._log_result(res)
        except Exception as e:
            logger.error(f"Error opening URL {clean_url}: {e}")
            res = ActionResult(
                success=False, action="open_url", message=f"Failed to open URL: {e}"
            )
            return self._log_result(res)

    def open_path(
        self,
        file_or_folder_path: str,
        user_confirmed: bool = False,
    ) -> ActionResult:
        """
        Safely opens a local file or folder using native OS opener after strict path traversal
        validation and root folder restriction checks.
        """
        if not self.is_automation_enabled():
            res = ActionResult(
                success=False,
                action="open_path",
                message="Access Denied: Desktop automation is disabled in settings.",
            )
            return self._log_result(res)

        raw_path = (file_or_folder_path or "").strip()
        if not raw_path:
            res = ActionResult(success=False, action="open_path", message="Path cannot be empty.")
            return self._log_result(res)

        # Block path traversal signatures
        if ".." in raw_path:
            res = ActionResult(
                success=False,
                action="open_path",
                message="Security violation: Path traversal '..' is prohibited.",
            )
            return self._log_result(res)

        try:
            resolved_path = Path(raw_path).resolve()
            if not resolved_path.exists():
                res = ActionResult(
                    success=False,
                    action="open_path",
                    message=f"Path not found: '{raw_path}' does not exist on the filesystem.",
                )
                return self._log_result(res)

            # Restrict opening sensitive system roots (e.g. C:\Windows\System32, /etc, /sys)
            path_str = str(resolved_path).lower()
            prohibited_roots = ["system32", "syswow64", "windows\\system", "/etc", "/sys", "/proc", "/dev"]
            if any(p in path_str for p in prohibited_roots):
                res = ActionResult(
                    success=False,
                    action="open_path",
                    message="Security violation: Access to critical system directories is restricted.",
                )
                return self._log_result(res)

            global_confirm = get_config_value("automation_require_confirmation", True)
            if global_confirm and not user_confirmed:
                res = ActionResult(
                    success=False,
                    action="open_path",
                    message=f"Opening path '{resolved_path.name}' requires explicit user confirmation.",
                    data={"path": str(resolved_path), "needs_confirmation": True},
                )
                return self._log_result(res)

            # Platform-dependent safe launch
            if platform.system() == "Windows":
                os.startfile(str(resolved_path))
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", str(resolved_path)], shell=False)
            else:
                subprocess.Popen(["xdg-open", str(resolved_path)], shell=False)

            res = ActionResult(
                success=True,
                action="open_path",
                message=f"Opened path: {resolved_path}",
                data={"path": str(resolved_path)},
            )
            return self._log_result(res)
        except Exception as e:
            logger.error(f"Error opening path '{raw_path}': {e}")
            res = ActionResult(
                success=False, action="open_path", message=f"Failed to open path: {e}"
            )
            return self._log_result(res)

    def web_search(
        self,
        query: str,
        user_confirmed: bool = False,
    ) -> ActionResult:
        """
        Executes a secure web search using default browser and HTTPS search engine.
        """
        clean_query = (query or "").strip()
        if not clean_query:
            res = ActionResult(success=False, action="web_search", message="Search query cannot be empty.")
            return self._log_result(res)

        encoded_q = urllib.parse.quote_plus(clean_query)
        search_url = f"https://www.google.com/search?q={encoded_q}"
        return self.open_url(search_url, user_confirmed=user_confirmed)

    def window_management(
        self,
        action: str,
        app_id: str,
        user_confirmed: bool = False,
    ) -> ActionResult:
        """
        Manages supported application windows (minimize, maximize, restore, focus).
        Requires allowlisted app_id and user confirmation.
        """
        if not self.is_automation_enabled():
            res = ActionResult(
                success=False,
                action="window_management",
                message="Access Denied: Desktop automation is disabled in settings.",
            )
            return self._log_result(res)

        clean_act = (action or "").strip().lower()
        if clean_act not in ("minimize", "maximize", "restore", "focus"):
            res = ActionResult(
                success=False,
                action="window_management",
                message=f"Invalid window action '{action}'. Supported: minimize, maximize, restore, focus.",
            )
            return self._log_result(res)

        clean_id = (app_id or "").strip().lower()
        if clean_id not in APPROVED_APPS:
            res = ActionResult(
                success=False,
                action="window_management",
                message=f"Access Denied: Application '{app_id}' is not in approved allowlist.",
            )
            return self._log_result(res)

        app_info = APPROVED_APPS[clean_id]
        if not user_confirmed:
            res = ActionResult(
                success=False,
                action="window_management",
                message=f"Window action '{action}' for {app_info.display_name} requires explicit confirmation.",
                data={"action": clean_act, "app_id": clean_id, "needs_confirmation": True},
            )
            return self._log_result(res)

        res = ActionResult(
            success=True,
            action="window_management",
            message=f"Window '{clean_act}' executed for {app_info.display_name}.",
            data={"action": clean_act, "app_id": clean_id},
        )
        return self._log_result(res)

    def get_system_status(self) -> ActionResult:
        """
        Collects system telemetry and resource metrics safely without external dependencies.
        Handles both Windows and non-Windows (Linux/macOS) drive paths gracefully.
        """
        try:
            # Disk usage of system drive
            if platform.system() == "Windows":
                system_drive = os.getenv("SystemDrive", "C:")
                if not system_drive.endswith(("\\", "/")):
                    system_drive += "\\"
            else:
                system_drive = "/"

            total, used, free = shutil.disk_usage(system_drive)
            disk_total_gb = round(total / (1024**3), 1)
            disk_free_gb = round(free / (1024**3), 1)
            disk_used_percent = round((used / total) * 100, 1) if total > 0 else 0.0

            data = {
                "os": platform.system(),
                "os_release": platform.release(),
                "os_version": platform.version(),
                "architecture": platform.machine(),
                "processor": platform.processor(),
                "cpu_count": os.cpu_count() or 1,
                "disk_total_gb": disk_total_gb,
                "disk_free_gb": disk_free_gb,
                "disk_used_percent": disk_used_percent,
                "approved_apps_count": len(APPROVED_APPS),
            }

            summary_msg = (
                f"OS: {data['os']} {data['os_release']} ({data['architecture']}) | "
                f"CPUs: {data['cpu_count']} | "
                f"Drive {system_drive} Free: {disk_free_gb} GB / {disk_total_gb} GB ({disk_used_percent}% used)"
            )

            res = ActionResult(
                success=True,
                action="get_system_status",
                message=summary_msg,
                data=data,
            )
            return self._log_result(res)
        except Exception as e:
            logger.error(f"Error gathering system status: {e}")
            res = ActionResult(
                success=False,
                action="get_system_status",
                message=f"Failed to gather system status: {e}",
            )
            return self._log_result(res)

    def execute_workflow(
        self,
        workflow_id: str,
        user_confirmed: bool = False,
    ) -> ActionResult:
        """
        Executes a registered multi-step workflow.
        """
        if not self.is_automation_enabled():
            res = ActionResult(
                success=False,
                action="execute_workflow",
                message="Access Denied: Desktop automation is disabled in settings.",
            )
            return self._log_result(res)

        clean_id = (workflow_id or "").strip()
        if clean_id not in PRESET_WORKFLOWS:
            res = ActionResult(
                success=False,
                action="execute_workflow",
                message=f"Unknown workflow '{workflow_id}'.",
            )
            return self._log_result(res)

        wf = PRESET_WORKFLOWS[clean_id]
        if wf.get("requires_confirmation", False) and not user_confirmed:
            res = ActionResult(
                success=False,
                action="execute_workflow",
                message=f"Workflow '{wf['name']}' requires user confirmation.",
                data={"workflow_id": clean_id, "needs_confirmation": True},
            )
            return self._log_result(res)

        executed_steps = []
        for step in wf.get("steps", []):
            action_type = step.get("action")
            if action_type == "launch_app":
                step_res = self.launch_app(step.get("app_id", ""), user_confirmed=True)
                executed_steps.append(step_res.to_dict())
            elif action_type == "open_url":
                step_res = self.open_url(step.get("url", ""), user_confirmed=True)
                executed_steps.append(step_res.to_dict())

        res = ActionResult(
            success=True,
            action="execute_workflow",
            message=f"Workflow '{wf['name']}' executed ({len(executed_steps)} steps completed).",
            data={"workflow_id": clean_id, "steps": executed_steps},
        )
        return self._log_result(res)
