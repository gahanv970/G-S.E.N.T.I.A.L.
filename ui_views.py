"""
Rich Liquid Glass UI Views for G-AI-ASSISTANT (JARVIS AI).
Contains dedicated, fully-functional view widgets for:
- Task Management (TaskManagementWidget)
- Memory & Personalization (MemoryManagementWidget)
- Gmail Integration (EmailManagementWidget)
- Windows Automation (AutomationManagementWidget)
"""

import asyncio
from datetime import datetime
import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from qasync import asyncSlot

from automation_service import APPROVED_APPS, PRESET_WORKFLOWS, WindowsAutomationService
from gmail_service import EmailDetail, EmailSummary, GmailService, generate_reply_draft, summarize_and_classify_email
from gui_components import LiquidGlassCard
from memory_service import MemoryService
from task_service import Task, TaskService
from utils import show_error_message, show_info_message

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# 1. TASK MANAGEMENT WIDGET
# ----------------------------------------------------------------------

class TaskManagementWidget(QWidget):
    """
    Dedicated view for managing persistent tasks (CRUD, priority, due dates, filters, search).
    """

    task_count_updated = Signal(int, int)  # (pending_count, completed_count)

    def __init__(self, task_service: TaskService, parent=None):
        super().__init__(parent)
        self.task_service = task_service
        self._setup_ui()
        self.refresh_tasks()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # Header Card
        header_card = LiquidGlassCard(self, corner_radius=18)
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(18, 12, 18, 12)

        title_box = QVBoxLayout()
        title = QLabel("<h2 style='color: #00C8FF; margin: 0;'>Task Management</h2>")
        self.stats_label = QLabel("Track and organize your personal and development tasks")
        self.stats_label.setStyleSheet("color: #A0AEC0; font-size: 13px;")
        title_box.addWidget(title)
        title_box.addWidget(self.stats_label)
        header_layout.addLayout(title_box)

        header_layout.addStretch()

        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self.refresh_tasks)
        header_layout.addWidget(self.refresh_btn)

        layout.addWidget(header_card)

        # Create Task Card
        create_card = LiquidGlassCard(self, corner_radius=18)
        create_layout = QVBoxLayout(create_card)
        create_layout.setContentsMargins(18, 14, 18, 14)
        create_layout.setSpacing(10)

        create_title = QLabel("<b style='color: #7FFFD4; font-size: 14px;'>Create New Task</b>")
        create_layout.addWidget(create_title)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Task title (required)...")
        self.title_input.setFixedHeight(36)
        row1.addWidget(self.title_input, stretch=3)

        self.priority_combo = QComboBox()
        self.priority_combo.addItems(["MEDIUM", "LOW", "HIGH", "CRITICAL"])
        self.priority_combo.setFixedHeight(36)
        row1.addWidget(self.priority_combo, stretch=1)

        self.due_date_input = QLineEdit()
        self.due_date_input.setPlaceholderText("Due Date (YYYY-MM-DD)")
        self.due_date_input.setFixedHeight(36)
        row1.addWidget(self.due_date_input, stretch=1)

        self.add_btn = QPushButton("➕ Add Task")
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.setFixedHeight(36)
        self.add_btn.clicked.connect(self._create_task)
        row1.addWidget(self.add_btn, stretch=1)

        create_layout.addLayout(row1)

        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("Optional description or details...")
        self.desc_input.setFixedHeight(34)
        create_layout.addWidget(self.desc_input)

        layout.addWidget(create_card)

        # Filter and Search Bar
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search tasks...")
        self.search_input.setFixedHeight(34)
        self.search_input.textChanged.connect(self.refresh_tasks)
        filter_bar.addWidget(self.search_input, stretch=2)

        self.status_filter = QComboBox()
        self.status_filter.addItems(["All Tasks", "Pending Only", "Completed Only"])
        self.status_filter.setFixedHeight(34)
        self.status_filter.currentIndexChanged.connect(self.refresh_tasks)
        filter_bar.addWidget(self.status_filter, stretch=1)

        self.priority_filter = QComboBox()
        self.priority_filter.addItems(["All Priorities", "CRITICAL", "HIGH", "MEDIUM", "LOW"])
        self.priority_filter.setFixedHeight(34)
        self.priority_filter.currentIndexChanged.connect(self.refresh_tasks)
        filter_bar.addWidget(self.priority_filter, stretch=1)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Newest First", "Oldest First", "By Priority", "By Due Date"])
        self.sort_combo.setFixedHeight(34)
        self.sort_combo.currentIndexChanged.connect(self.refresh_tasks)
        filter_bar.addWidget(self.sort_combo, stretch=1)

        layout.addLayout(filter_bar)

        # Scroll Area for Task Items
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.task_list_container = QWidget()
        self.task_list_layout = QVBoxLayout(self.task_list_container)
        self.task_list_layout.setContentsMargins(0, 0, 0, 0)
        self.task_list_layout.setSpacing(8)
        self.task_list_layout.addStretch()
        self.scroll_area.setWidget(self.task_list_container)

        layout.addWidget(self.scroll_area, stretch=1)

    def _create_task(self):
        title = self.title_input.text().strip()
        if not title:
            show_error_message("Validation Error", "Task title cannot be empty.")
            return

        priority = self.priority_combo.currentText()
        due_date = self.due_date_input.text().strip() or None
        desc = self.desc_input.text().strip()

        try:
            self.task_service.create_task(
                title=title, description=desc, priority=priority, due_date=due_date
            )
            self.title_input.clear()
            self.desc_input.clear()
            self.due_date_input.clear()
            self.refresh_tasks()
        except Exception as e:
            show_error_message("Task Error", str(e))

    def refresh_tasks(self):
        # Clear existing items in layout
        while self.task_list_layout.count() > 1:
            child = self.task_list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        status_text = self.status_filter.currentText()
        status_filter = None
        if status_text == "Pending Only":
            status_filter = "pending"
        elif status_text == "Completed Only":
            status_filter = "completed"

        pri_text = self.priority_filter.currentText()
        priority_filter = None if pri_text == "All Priorities" else pri_text

        search = self.search_input.text().strip() or None

        sort_map = {
            "Newest First": "created_desc",
            "Oldest First": "created_asc",
            "By Priority": "priority",
            "By Due Date": "due_date",
        }
        sort_by = sort_map.get(self.sort_combo.currentText(), "created_desc")

        tasks = self.task_service.get_all_tasks(
            status_filter=status_filter,
            priority_filter=priority_filter,
            search_query=search,
            sort_by=sort_by,
        )

        all_tasks = self.task_service.get_all_tasks()
        pending_count = sum(1 for t in all_tasks if t.status == "pending")
        completed_count = sum(1 for t in all_tasks if t.status == "completed")
        self.stats_label.setText(f"{pending_count} Pending | {completed_count} Completed | Total: {len(all_tasks)}")
        self.task_count_updated.emit(pending_count, completed_count)

        if not tasks:
            empty_lbl = QLabel("<p style='color: #718096; text-align: center; margin: 30px;'>No tasks found matching criteria.</p>")
            empty_lbl.setAlignment(Qt.AlignCenter)
            self.task_list_layout.insertWidget(0, empty_lbl)
            return

        for task in tasks:
            card = self._create_task_item_widget(task)
            self.task_list_layout.insertWidget(self.task_list_layout.count() - 1, card)

    def _create_task_item_widget(self, task: Task) -> QWidget:
        item = LiquidGlassCard(self.task_list_container, corner_radius=14)
        item_layout = QHBoxLayout(item)
        item_layout.setContentsMargins(14, 10, 14, 10)
        item_layout.setSpacing(12)

        # Checkbox toggle
        chk = QCheckBox()
        chk.setChecked(task.status == "completed")
        chk.toggled.connect(lambda checked, tid=task.id: self._toggle_status(tid))
        item_layout.addWidget(chk)

        # Priority Badge
        pri_colors = {
            "CRITICAL": "#FF4444",
            "HIGH": "#FFAA00",
            "MEDIUM": "#00C8FF",
            "LOW": "#888888",
        }
        color = pri_colors.get(task.priority, "#00C8FF")
        badge = QLabel(f" {task.priority} ")
        badge.setStyleSheet(f"""
            background-color: rgba(255, 255, 255, 10);
            color: {color};
            border: 1px solid {color};
            border-radius: 6px;
            font-size: 11px;
            font-weight: bold;
            padding: 3px 6px;
        """)
        item_layout.addWidget(badge)

        # Task Text Box
        content_box = QVBoxLayout()
        content_box.setSpacing(2)

        title_style = "color: #718096; text-decoration: line-through;" if task.status == "completed" else "color: #F0F4F8; font-weight: bold;"
        title_lbl = QLabel(f"<span style='{title_style} font-size: 13px;'>{task.title}</span>")
        content_box.addWidget(title_lbl)

        if task.description:
            desc_lbl = QLabel(f"<span style='color: #A0AEC0; font-size: 11px;'>{task.description}</span>")
            content_box.addWidget(desc_lbl)

        item_layout.addLayout(content_box, stretch=1)

        # Due Date Badge
        if task.due_date:
            due_lbl = QLabel(f"📅 {task.due_date}")
            due_lbl.setStyleSheet("color: #7FFFD4; font-size: 11px; background: rgba(0, 200, 255, 20); padding: 4px 8px; border-radius: 6px;")
            item_layout.addWidget(due_lbl)

        # Edit button
        edit_btn = QPushButton("✏️")
        edit_btn.setFixedSize(32, 32)
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.setToolTip("Edit Task")
        edit_btn.clicked.connect(lambda _, t=task: self._edit_task_dialog(t))
        item_layout.addWidget(edit_btn)

        # Delete button
        del_btn = QPushButton("🗑️")
        del_btn.setFixedSize(32, 32)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setToolTip("Delete Task")
        del_btn.setStyleSheet("color: #FF6B6B;")
        del_btn.clicked.connect(lambda _, tid=task.id: self._confirm_delete(tid))
        item_layout.addWidget(del_btn)

        return item

    def _toggle_status(self, task_id: int):
        self.task_service.toggle_task_status(task_id)
        self.refresh_tasks()

    def _confirm_delete(self, task_id: int):
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            "Are you sure you want to delete this task?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.task_service.delete_task(task_id)
            self.refresh_tasks()

    def _edit_task_dialog(self, task: Task):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Edit Task #{task.id}")
        dialog.setFixedWidth(400)
        d_layout = QVBoxLayout(dialog)
        d_layout.setSpacing(10)

        d_layout.addWidget(QLabel("Title:"))
        title_in = QLineEdit(task.title)
        d_layout.addWidget(title_in)

        d_layout.addWidget(QLabel("Description:"))
        desc_in = QLineEdit(task.description)
        d_layout.addWidget(desc_in)

        d_layout.addWidget(QLabel("Priority:"))
        pri_combo = QComboBox()
        pri_combo.addItems(["LOW", "MEDIUM", "HIGH", "CRITICAL"])
        pri_combo.setCurrentText(task.priority)
        d_layout.addWidget(pri_combo)

        d_layout.addWidget(QLabel("Due Date (YYYY-MM-DD):"))
        due_in = QLineEdit(task.due_date or "")
        d_layout.addWidget(due_in)

        btn_box = QHBoxLayout()
        save_btn = QPushButton("Save Changes")
        save_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        btn_box.addWidget(save_btn)
        btn_box.addWidget(cancel_btn)
        d_layout.addLayout(btn_box)

        if dialog.exec() == QDialog.Accepted:
            new_title = title_in.text().strip()
            if new_title:
                self.task_service.update_task(
                    task.id,
                    title=new_title,
                    description=desc_in.text().strip(),
                    priority=pri_combo.currentText(),
                    due_date=due_in.text().strip() or None,
                )
                self.refresh_tasks()


# ----------------------------------------------------------------------
# 2. MEMORY & PERSONALIZATION WIDGET
# ----------------------------------------------------------------------

class MemoryManagementWidget(QWidget):
    """
    Dedicated view for configuring long-term user preferences,
    inspecting remembered context, adding facts, and managing memories.
    """

    def __init__(self, memory_service: MemoryService, parent=None):
        super().__init__(parent)
        self.memory_service = memory_service
        self._setup_ui()
        self.refresh_memories()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # Header Card
        header_card = LiquidGlassCard(self, corner_radius=18)
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(18, 12, 18, 12)

        title_box = QVBoxLayout()
        title = QLabel("<h2 style='color: #00C8FF; margin: 0;'>Memory & Personalization</h2>")
        desc = QLabel("User preferences and contextual memories injected into AI responses")
        desc.setStyleSheet("color: #A0AEC0; font-size: 13px;")
        title_box.addWidget(title)
        title_box.addWidget(desc)
        header_layout.addLayout(title_box)

        header_layout.addStretch()

        self.memory_toggle = QCheckBox("Enable Long-Term Memory")
        self.memory_toggle.setChecked(self.memory_service.is_memory_enabled())
        self.memory_toggle.toggled.connect(self._toggle_memory)
        header_layout.addWidget(self.memory_toggle)

        layout.addWidget(header_card)

        # Preferences Card
        pref_card = LiquidGlassCard(self, corner_radius=18)
        pref_layout = QVBoxLayout(pref_card)
        pref_layout.setContentsMargins(18, 14, 18, 14)
        pref_layout.setSpacing(10)

        pref_title = QLabel("<b style='color: #7FFFD4; font-size: 14px;'>User Preferences</b>")
        pref_layout.addWidget(pref_title)

        prefs = self.memory_service.get_preferences()
        row = QHBoxLayout()
        row.setSpacing(10)

        self.user_name_input = QLineEdit(prefs.get("user_name", ""))
        self.user_name_input.setPlaceholderText("Your Name (e.g. Tony)")
        self.user_name_input.setFixedHeight(34)
        row.addWidget(self.user_name_input, stretch=1)

        self.tone_input = QLineEdit(prefs.get("preferred_tone", ""))
        self.tone_input.setPlaceholderText("Tone (e.g. Concise, technical, witty)")
        self.tone_input.setFixedHeight(34)
        row.addWidget(self.tone_input, stretch=2)

        self.lang_input = QLineEdit(prefs.get("code_language_preference", ""))
        self.lang_input.setPlaceholderText("Preferred Language (e.g. Python)")
        self.lang_input.setFixedHeight(34)
        row.addWidget(self.lang_input, stretch=1)

        save_pref_btn = QPushButton("Save Preferences")
        save_pref_btn.setFixedHeight(34)
        save_pref_btn.setCursor(Qt.PointingHandCursor)
        save_pref_btn.clicked.connect(self._save_preferences)
        row.addWidget(save_pref_btn, stretch=1)

        pref_layout.addLayout(row)
        layout.addWidget(pref_card)

        # Add Memory Card
        add_card = LiquidGlassCard(self, corner_radius=18)
        add_layout = QHBoxLayout(add_card)
        add_layout.setContentsMargins(18, 12, 18, 12)
        add_layout.setSpacing(10)

        self.mem_content_input = QLineEdit()
        self.mem_content_input.setPlaceholderText("Add a fact or context (e.g. 'Working on Windows AI desktop project')...")
        self.mem_content_input.setFixedHeight(36)
        add_layout.addWidget(self.mem_content_input, stretch=3)

        self.category_combo = QComboBox()
        self.category_combo.addItems(["fact", "preference", "project", "instruction"])
        self.category_combo.setFixedHeight(36)
        add_layout.addWidget(self.category_combo, stretch=1)

        add_mem_btn = QPushButton("➕ Add Memory")
        add_mem_btn.setFixedHeight(36)
        add_mem_btn.setCursor(Qt.PointingHandCursor)
        add_mem_btn.clicked.connect(self._add_memory)
        add_layout.addWidget(add_mem_btn, stretch=1)

        layout.addWidget(add_card)

        # Action Bar (Search & Clear All)
        bar = QHBoxLayout()
        self.search_mem_input = QLineEdit()
        self.search_mem_input.setPlaceholderText("🔍 Search stored memories...")
        self.search_mem_input.setFixedHeight(34)
        self.search_mem_input.textChanged.connect(self.refresh_memories)
        bar.addWidget(self.search_mem_input, stretch=3)

        self.clear_all_btn = QPushButton("🗑️ Clear All Memories")
        self.clear_all_btn.setFixedHeight(34)
        self.clear_all_btn.setCursor(Qt.PointingHandCursor)
        self.clear_all_btn.setStyleSheet("color: #FF6B6B;")
        self.clear_all_btn.clicked.connect(self._clear_all_memories)
        bar.addWidget(self.clear_all_btn, stretch=1)

        layout.addLayout(bar)

        # Scroll Area for Memory List
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.mem_list_container = QWidget()
        self.mem_list_layout = QVBoxLayout(self.mem_list_container)
        self.mem_list_layout.setContentsMargins(0, 0, 0, 0)
        self.mem_list_layout.setSpacing(8)
        self.mem_list_layout.addStretch()
        self.scroll_area.setWidget(self.mem_list_container)

        layout.addWidget(self.scroll_area, stretch=1)

    def _toggle_memory(self, checked: bool):
        self.memory_service.set_memory_enabled(checked)
        show_info_message("Memory Setting", f"Memory context injection is now {'enabled' if checked else 'disabled'}.")

    def _save_preferences(self):
        updates = {
            "user_name": self.user_name_input.text().strip(),
            "preferred_tone": self.tone_input.text().strip(),
            "code_language_preference": self.lang_input.text().strip(),
        }
        self.memory_service.save_preferences(updates)
        show_info_message("Preferences Saved", "Your AI personalization settings have been updated.")

    def _add_memory(self):
        content = self.mem_content_input.text().strip()
        category = self.category_combo.currentText()
        if not content:
            show_error_message("Validation Error", "Memory content cannot be blank.")
            return

        try:
            self.memory_service.add_memory(content, category=category)
            self.mem_content_input.clear()
            self.refresh_memories()
        except Exception as e:
            show_error_message("Security Rejection", str(e))

    def refresh_memories(self):
        while self.mem_list_layout.count() > 1:
            child = self.mem_list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        search = self.search_mem_input.text().strip() or None
        memories = self.memory_service.get_all_memories(search_query=search)

        if not memories:
            empty = QLabel("<p style='color: #718096; text-align: center; margin: 30px;'>No stored memories found.</p>")
            empty.setAlignment(Qt.AlignCenter)
            self.mem_list_layout.insertWidget(0, empty)
            return

        for mem in memories:
            item = LiquidGlassCard(self.mem_list_container, corner_radius=14)
            i_layout = QHBoxLayout(item)
            i_layout.setContentsMargins(14, 10, 14, 10)
            i_layout.setSpacing(10)

            cat_badge = QLabel(f"[{mem.category.upper()}]")
            cat_badge.setStyleSheet("color: #7FFFD4; font-weight: bold; font-size: 11px;")
            i_layout.addWidget(cat_badge)

            content_lbl = QLabel(mem.content)
            content_lbl.setStyleSheet("color: #E2E8F0; font-size: 13px;")
            content_lbl.setWordWrap(True)
            i_layout.addWidget(content_lbl, stretch=1)

            date_lbl = QLabel(mem.created_at[:10])
            date_lbl.setStyleSheet("color: #718096; font-size: 11px;")
            i_layout.addWidget(date_lbl)

            del_btn = QPushButton("🗑️")
            del_btn.setFixedSize(30, 30)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setStyleSheet("color: #FF6B6B;")
            del_btn.clicked.connect(lambda _, mid=mem.id: self._delete_memory(mid))
            i_layout.addWidget(del_btn)

            self.mem_list_layout.insertWidget(self.mem_list_layout.count() - 1, item)

    def _delete_memory(self, memory_id: int):
        self.memory_service.delete_memory(memory_id)
        self.refresh_memories()

    def _clear_all_memories(self):
        reply = QMessageBox.warning(
            self,
            "Clear All Memories",
            "Are you sure you want to delete ALL remembered context? This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.memory_service.clear_all_memories()
            self.refresh_memories()
            show_info_message("Cleared", "All stored memories have been cleared.")


# ----------------------------------------------------------------------
# 3. GMAIL INTEGRATION WIDGET
# ----------------------------------------------------------------------

class EmailManagementWidget(QWidget):
    """
    Dedicated view for Gmail integration:
    OAuth authorization, mailbox inbox, pagination, message viewing, draft composing,
    and user-confirmed message dispatching.
    """

    def __init__(self, gmail_service: GmailService, parent=None):
        super().__init__(parent)
        self.gmail_service = gmail_service
        self._current_page_token: Optional[str] = None
        self._next_page_token: Optional[str] = None
        self._page_tokens_history: List[Optional[str]] = []
        self._setup_ui()
        self.update_auth_status()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # Header Card with Status
        header_card = LiquidGlassCard(self, corner_radius=18)
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(18, 12, 18, 12)

        title_box = QVBoxLayout()
        title = QLabel("<h2 style='color: #00C8FF; margin: 0;'>Gmail Integration</h2>")
        self.status_label = QLabel("Status: Checking authentication...")
        self.status_label.setStyleSheet("color: #A0AEC0; font-size: 13px;")
        title_box.addWidget(title)
        title_box.addWidget(self.status_label)
        header_layout.addLayout(title_box)

        header_layout.addStretch()

        self.auth_btn = QPushButton("Connect Account")
        self.auth_btn.setCursor(Qt.PointingHandCursor)
        self.auth_btn.clicked.connect(self._toggle_auth)
        header_layout.addWidget(self.auth_btn)

        self.setup_help_btn = QPushButton("OAuth Setup Guide")
        self.setup_help_btn.setCursor(Qt.PointingHandCursor)
        self.setup_help_btn.clicked.connect(self._show_oauth_guide)
        header_layout.addWidget(self.setup_help_btn)

        self.refresh_mail_btn = QPushButton("🔄 Check Mail")
        self.refresh_mail_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_mail_btn.clicked.connect(self._load_mailbox)
        header_layout.addWidget(self.refresh_mail_btn)

        layout.addWidget(header_card)

        # Main Splitter: Left = Mailbox & Detail, Right = Compose Draft
        splitter = QSplitter(Qt.Horizontal, self)

        # Left Container: Messages
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 5, 0)
        left_layout.setSpacing(10)

        search_row = QHBoxLayout()
        self.email_search_input = QLineEdit()
        self.email_search_input.setPlaceholderText("🔍 Search emails (e.g. from:support, is:unread)...")
        self.email_search_input.setFixedHeight(34)
        self.email_search_input.returnPressed.connect(self._load_mailbox)
        search_row.addWidget(self.email_search_input)

        search_btn = QPushButton("Search")
        search_btn.setFixedHeight(34)
        search_btn.clicked.connect(self._load_mailbox)
        search_row.addWidget(search_btn)
        left_layout.addLayout(search_row)

        self.mail_scroll = QScrollArea()
        self.mail_scroll.setWidgetResizable(True)
        self.mail_list_container = QWidget()
        self.mail_list_layout = QVBoxLayout(self.mail_list_container)
        self.mail_list_layout.setContentsMargins(0, 0, 0, 0)
        self.mail_list_layout.setSpacing(6)
        self.mail_list_layout.addStretch()
        self.mail_scroll.setWidget(self.mail_list_container)
        left_layout.addWidget(self.mail_scroll)

        # Pagination controls bar
        page_bar = QHBoxLayout()
        self.prev_page_btn = QPushButton("◀ Previous Page")
        self.prev_page_btn.setFixedHeight(30)
        self.prev_page_btn.setEnabled(False)
        self.prev_page_btn.setCursor(Qt.PointingHandCursor)
        self.prev_page_btn.clicked.connect(self._load_prev_page)

        self.next_page_btn = QPushButton("Next Page ▶")
        self.next_page_btn.setFixedHeight(30)
        self.next_page_btn.setEnabled(False)
        self.next_page_btn.setCursor(Qt.PointingHandCursor)
        self.next_page_btn.clicked.connect(self._load_next_page)

        page_bar.addWidget(self.prev_page_btn)
        page_bar.addWidget(self.next_page_btn)
        left_layout.addLayout(page_bar)

        splitter.addWidget(left_container)

        # Right Container: Compose & Drafts
        right_container = LiquidGlassCard(self, corner_radius=18)
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(18, 14, 18, 14)
        right_layout.setSpacing(10)

        right_layout.addWidget(QLabel("<b style='color: #7FFFD4; font-size: 14px;'>Compose / Draft Email</b>"))

        self.to_input = QLineEdit()
        self.to_input.setPlaceholderText("Recipient (To: email@example.com)...")
        self.to_input.setFixedHeight(34)
        right_layout.addWidget(self.to_input)

        self.subject_input = QLineEdit()
        self.subject_input.setPlaceholderText("Subject...")
        self.subject_input.setFixedHeight(34)
        right_layout.addWidget(self.subject_input)

        self.body_input = QTextEdit()
        self.body_input.setPlaceholderText("Email content...")
        right_layout.addWidget(self.body_input, stretch=1)

        btn_row = QHBoxLayout()
        self.save_draft_btn = QPushButton("💾 Save as Draft")
        self.save_draft_btn.setFixedHeight(36)
        self.save_draft_btn.setCursor(Qt.PointingHandCursor)
        self.save_draft_btn.clicked.connect(self._save_draft)
        btn_row.addWidget(self.save_draft_btn)

        self.send_mail_btn = QPushButton("🚀 Send Email")
        self.send_mail_btn.setFixedHeight(36)
        self.send_mail_btn.setCursor(Qt.PointingHandCursor)
        self.send_mail_btn.setStyleSheet("background-color: rgba(0, 200, 255, 60); font-weight: bold;")
        self.send_mail_btn.clicked.connect(self._send_email_confirmed)
        btn_row.addWidget(self.send_mail_btn)

        right_layout.addLayout(btn_row)
        splitter.addWidget(right_container)

        splitter.setSizes([550, 450])
        layout.addWidget(splitter, stretch=1)

    def update_auth_status(self):
        if self.gmail_service.is_authenticated():
            email = self.gmail_service.get_user_email() or "Connected"
            self.status_label.setText(f"Connected: {email}")
            self.status_label.setStyleSheet("color: #7FFFD4; font-size: 13px;")
            self.auth_btn.setText("Disconnect")
            self.refresh_mail_btn.setEnabled(True)
            self.save_draft_btn.setEnabled(True)
            self.send_mail_btn.setEnabled(True)
        else:
            has_creds = self.gmail_service.has_client_credentials()
            if has_creds:
                self.status_label.setText("Not connected (credentials JSON found, ready for login)")
            else:
                self.status_label.setText("Not connected (place gmail_credentials.json in data/ folder)")
            self.status_label.setStyleSheet("color: #FFAA00; font-size: 13px;")
            self.auth_btn.setText("Connect Account")
            self.refresh_mail_btn.setEnabled(False)
            self.save_draft_btn.setEnabled(False)
            self.send_mail_btn.setEnabled(False)

    def _toggle_auth(self):
        if self.gmail_service.is_authenticated():
            self.gmail_service.disconnect()
            self.update_auth_status()
            show_info_message("Disconnected", "Gmail account disconnected.")
        else:
            if not self.gmail_service.has_client_credentials():
                show_error_message(
                    "Credentials Required",
                    f"Please place your OAuth client secrets file at:\n{self.gmail_service.get_credentials_path()}\n\n"
                    "Click 'OAuth Setup Guide' for step-by-step instructions."
                )
                return
            try:
                self.gmail_service.authenticate_oauth()
                self.update_auth_status()
                self._load_mailbox()
            except Exception as e:
                show_error_message("OAuth Authentication Failed", str(e))

    def _show_oauth_guide(self):
        guide = (
            "<h3>Google Gmail OAuth Setup Guide</h3>"
            "<ol>"
            "<li>Go to <a href='https://console.cloud.google.com/'>Google Cloud Console</a>.</li>"
            "<li>Create a project and enable the <b>Gmail API</b>.</li>"
            "<li>Configure the OAuth consent screen (Desktop App).</li>"
            "<li>Create credentials: <b>OAuth client ID</b> > <b>Desktop app</b>.</li>"
            "<li>Download JSON and save it as:<br><code>data/gmail_credentials.json</code> inside the project folder.</li>"
            "<li>Click <b>Connect Account</b> to complete browser authentication.</li>"
            "</ol>"
        )
        dlg = QMessageBox(self)
        dlg.setWindowTitle("OAuth Setup Guide")
        dlg.setTextFormat(Qt.RichText)
        dlg.setText(guide)
        dlg.exec()

    @asyncSlot()
    async def _load_mailbox(self, page_token: Optional[str] = None):
        if not self.gmail_service.is_authenticated():
            return

        while self.mail_list_layout.count() > 1:
            child = self.mail_list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        loading = QLabel("<p style='color: #00C8FF; text-align: center; margin: 20px;'>Loading emails from Gmail...</p>")
        self.mail_list_layout.insertWidget(0, loading)

        q = self.email_search_input.text().strip() or None
        try:
            summaries, next_token = await asyncio.to_thread(
                self.gmail_service.list_messages, query=q, page_token=page_token
            )
            loading.deleteLater()

            self._next_page_token = next_token
            self.next_page_btn.setEnabled(bool(next_token))
            self.prev_page_btn.setEnabled(len(self._page_tokens_history) > 0)

            if not summaries:
                empty = QLabel("<p style='color: #718096; text-align: center; margin: 30px;'>No messages found.</p>")
                empty.setAlignment(Qt.AlignCenter)
                self.mail_list_layout.insertWidget(0, empty)
                return

            for summary in summaries:
                card = self._create_email_summary_widget(summary)
                self.mail_list_layout.insertWidget(self.mail_list_layout.count() - 1, card)
        except Exception as e:
            loading.deleteLater()
            show_error_message("Mailbox Error", f"Failed to retrieve emails: {e}")

    @asyncSlot()
    async def _load_next_page(self):
        if self._next_page_token:
            self._page_tokens_history.append(self._current_page_token)
            self._current_page_token = self._next_page_token
            await self._load_mailbox(page_token=self._current_page_token)

    @asyncSlot()
    async def _load_prev_page(self):
        if self._page_tokens_history:
            prev_token = self._page_tokens_history.pop()
            self._current_page_token = prev_token
            await self._load_mailbox(page_token=self._current_page_token)

    def _create_email_summary_widget(self, s: EmailSummary) -> QWidget:
        card = LiquidGlassCard(self.mail_list_container, corner_radius=12)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(12, 10, 12, 10)
        c_layout.setSpacing(4)

        top = QHBoxLayout()
        sender_lbl = QLabel(f"<b style='color: #00C8FF;'>{s.sender}</b>")
        date_lbl = QLabel(s.date[:16] if len(s.date) > 16 else s.date)
        date_lbl.setStyleSheet("color: #718096; font-size: 11px;")
        top.addWidget(sender_lbl, stretch=1)
        top.addWidget(date_lbl)
        c_layout.addLayout(top)

        subj_lbl = QLabel(f"<b style='color: #F0F4F8;'>{s.subject}</b>")
        c_layout.addWidget(subj_lbl)

        snippet_lbl = QLabel(s.snippet)
        snippet_lbl.setStyleSheet("color: #A0AEC0; font-size: 11px;")
        snippet_lbl.setWordWrap(True)
        c_layout.addWidget(snippet_lbl)

        view_btn = QPushButton("View Full Message")
        view_btn.setFixedHeight(26)
        view_btn.setCursor(Qt.PointingHandCursor)
        view_btn.clicked.connect(lambda _, mid=s.id: self._open_message_detail(mid))
        c_layout.addWidget(view_btn, alignment=Qt.AlignRight)

        return card

    @asyncSlot()
    async def _open_message_detail(self, message_id: str):
        try:
            detail: EmailDetail = await asyncio.to_thread(
                self.gmail_service.get_message_detail, message_id
            )
            if not detail:
                return

            dlg = QDialog(self)
            dlg.setWindowTitle(detail.subject)
            dlg.resize(650, 500)
            d_layout = QVBoxLayout(dlg)

            header_box = QVBoxLayout()
            header_box.addWidget(QLabel(f"<b>From:</b> {detail.sender}"))
            header_box.addWidget(QLabel(f"<b>To:</b> {detail.recipient}"))
            header_box.addWidget(QLabel(f"<b>Date:</b> {detail.date}"))
            header_box.addWidget(QLabel(f"<b>Subject:</b> {detail.subject}"))
            d_layout.addLayout(header_box)

            body_view = QTextEdit()
            body_view.setReadOnly(True)
            if detail.body_html:
                body_view.setHtml(detail.body_html)
            else:
                body_view.setPlainText(detail.body_text)
            d_layout.addWidget(body_view)

            # AI Summary Display Box
            summary_display = QLabel()
            summary_display.setStyleSheet("background: rgba(0, 200, 255, 20); border: 1px solid rgba(0, 200, 255, 60); padding: 10px; border-radius: 8px; color: #E2E8F0; font-size: 12px;")
            summary_display.setWordWrap(True)
            summary_display.hide()
            d_layout.addWidget(summary_display)

            # AI Action Buttons Row
            ai_btn_row = QHBoxLayout()

            summarize_btn = QPushButton("✨ AI Summarize & Classify")
            summarize_btn.setFixedHeight(34)
            summarize_btn.setCursor(Qt.PointingHandCursor)

            reply_draft_btn = QPushButton("✍️ AI Generate Reply Draft")
            reply_draft_btn.setFixedHeight(34)
            reply_draft_btn.setCursor(Qt.PointingHandCursor)

            ai_btn_row.addWidget(summarize_btn)
            ai_btn_row.addWidget(reply_draft_btn)
            d_layout.addLayout(ai_btn_row)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dlg.accept)
            d_layout.addWidget(close_btn)

            async def _on_summarize():
                summarize_btn.setEnabled(False)
                summary_display.setText("AI is analyzing and summarizing email...")
                summary_display.show()
                try:
                    ai_prov = getattr(self.window(), "ai_provider", None)
                    res = await asyncio.to_thread(summarize_and_classify_email, detail, ai_prov)
                    urgency_colors = {
                        "critical": "#FF4444",
                        "high": "#FFAA00",
                        "medium": "#00C8FF",
                        "low": "#7FFFD4",
                    }
                    u_col = urgency_colors.get(res.get("urgency", "low"), "#7FFFD4")
                    text = (
                        f"<b>AI Urgency Rating:</b> <span style='color:{u_col}; font-weight:bold;'>{res['urgency'].upper()}</span><br>"
                        f"<b>AI Summary:</b> {res['summary']}"
                    )
                    summary_display.setText(text)
                except Exception as ex:
                    summary_display.setText(f"AI Summarization Error: {ex}")
                finally:
                    summarize_btn.setEnabled(True)

            async def _on_generate_reply():
                reply_draft_btn.setEnabled(False)
                try:
                    ai_prov = getattr(self.window(), "ai_provider", None)
                    res = await asyncio.to_thread(generate_reply_draft, detail, ai_prov)
                    self.to_input.setText(detail.sender)
                    self.subject_input.setText(res.get("subject", f"Re: {detail.subject}"))
                    self.body_input.setText(res.get("body", ""))
                    dlg.accept()
                    show_info_message("Reply Draft Generated", "Proposed reply draft populated in Compose tab for your review.")
                except Exception as ex:
                    show_error_message("Draft Error", str(ex))
                finally:
                    reply_draft_btn.setEnabled(True)

            summarize_btn.clicked.connect(lambda *_: asyncio.create_task(_on_summarize()))
            reply_draft_btn.clicked.connect(lambda *_: asyncio.create_task(_on_generate_reply()))

            dlg.exec()
        except Exception as e:
            show_error_message("Read Error", str(e))

    @asyncSlot()
    async def _save_draft(self):
        to = self.to_input.text().strip()
        subj = self.subject_input.text().strip()
        body = self.body_input.toPlainText()

        try:
            draft = await asyncio.to_thread(self.gmail_service.create_draft, to, subj, body)
            show_info_message("Draft Saved", f"Draft saved successfully in Gmail (ID: {draft.id})")
        except Exception as e:
            show_error_message("Draft Error", str(e))

    @asyncSlot()
    async def _send_email_confirmed(self):
        to = self.to_input.text().strip()
        subj = self.subject_input.text().strip()
        body = self.body_input.toPlainText()

        if not to:
            show_error_message("Validation Error", "Recipient 'To:' address cannot be empty.")
            return

        # Explicit user confirmation dialog
        reply = QMessageBox.question(
            self,
            "Confirm Send Email",
            f"Are you sure you want to send this email?\n\nTo: {to}\nSubject: {subj}\n\nThis action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            sent_id = await asyncio.to_thread(
                self.gmail_service.send_email, to, subj, body, user_confirmed=True
            )
            show_info_message("Email Sent", f"Email successfully dispatched! (ID: {sent_id})")
            self.to_input.clear()
            self.subject_input.clear()
            self.body_input.clear()
        except Exception as e:
            show_error_message("Send Error", str(e))


# ----------------------------------------------------------------------
# 4. WINDOWS AUTOMATION WIDGET
# ----------------------------------------------------------------------

class AutomationManagementWidget(QWidget):
    """
    Dedicated view for safe Windows automation:
    Approved applications registry, safe URL launcher, system telemetry,
    workflows, and execution audit log.
    """

    def __init__(self, automation_service: WindowsAutomationService, parent=None):
        super().__init__(parent)
        self.automation_service = automation_service
        self._setup_ui()
        self.refresh_system_status()
        self.refresh_audit_log()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # Header Card
        header_card = LiquidGlassCard(self, corner_radius=18)
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(18, 12, 18, 12)

        title_box = QVBoxLayout()
        title = QLabel("<h2 style='color: #00C8FF; margin: 0;'>Windows Automation</h2>")
        desc = QLabel("Controlled desktop operations, safe application launching, and telemetry")
        desc.setStyleSheet("color: #A0AEC0; font-size: 13px;")
        title_box.addWidget(title)
        title_box.addWidget(desc)
        header_layout.addLayout(title_box)

        header_layout.addStretch()

        refresh_telemetry_btn = QPushButton("🔄 Refresh Telemetry")
        refresh_telemetry_btn.setCursor(Qt.PointingHandCursor)
        refresh_telemetry_btn.clicked.connect(self.refresh_system_status)
        header_layout.addWidget(refresh_telemetry_btn)

        layout.addWidget(header_card)

        # Telemetry Card
        self.telemetry_card = LiquidGlassCard(self, corner_radius=16)
        tele_layout = QVBoxLayout(self.telemetry_card)
        tele_layout.setContentsMargins(18, 12, 18, 12)
        tele_title = QLabel("<b style='color: #7FFFD4;'>System Telemetry</b>")
        self.telemetry_content = QLabel("Collecting system telemetry...")
        self.telemetry_content.setStyleSheet("color: #E2E8F0; font-size: 12px;")
        tele_layout.addWidget(tele_title)
        tele_layout.addWidget(self.telemetry_content)
        layout.addWidget(self.telemetry_card)

        # Middle Section Splitter: Approved Apps & Safe Workflows
        mid_splitter = QSplitter(Qt.Horizontal, self)

        # Approved Apps Card
        apps_card = LiquidGlassCard(self, corner_radius=18)
        apps_layout = QVBoxLayout(apps_card)
        apps_layout.setContentsMargins(16, 12, 16, 12)
        apps_layout.setSpacing(8)

        apps_layout.addWidget(QLabel("<b style='color: #00C8FF; font-size: 14px;'>Approved Applications Allowlist</b>"))

        apps_scroll = QScrollArea()
        apps_scroll.setWidgetResizable(True)
        apps_content = QWidget()
        apps_grid = QVBoxLayout(apps_content)
        apps_grid.setContentsMargins(0, 0, 0, 0)
        apps_grid.setSpacing(6)

        for app in self.automation_service.get_allowed_apps():
            row = LiquidGlassCard(apps_content, corner_radius=10)
            r_layout = QHBoxLayout(row)
            r_layout.setContentsMargins(10, 8, 10, 8)

            txt = QVBoxLayout()
            name_lbl = QLabel(f"<b>{app.display_name}</b> ({app.executable})")
            name_lbl.setStyleSheet("color: #F0F4F8; font-size: 12px;")
            desc_lbl = QLabel(app.description)
            desc_lbl.setStyleSheet("color: #A0AEC0; font-size: 10px;")
            txt.addWidget(name_lbl)
            txt.addWidget(desc_lbl)
            r_layout.addLayout(txt, stretch=1)

            launch_btn = QPushButton("Launch")
            launch_btn.setFixedSize(70, 28)
            launch_btn.setCursor(Qt.PointingHandCursor)
            launch_btn.clicked.connect(lambda _, aid=app.id: self._launch_app_action(aid))
            r_layout.addWidget(launch_btn)

            apps_grid.addWidget(row)

        apps_grid.addStretch()
        apps_scroll.setWidget(apps_content)
        apps_layout.addWidget(apps_scroll)
        mid_splitter.addWidget(apps_card)

        # Right: URL Launcher & Workflows
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        # URL Launcher
        url_card = LiquidGlassCard(right_panel, corner_radius=16)
        url_layout = QVBoxLayout(url_card)
        url_layout.setContentsMargins(14, 12, 14, 12)
        url_layout.addWidget(QLabel("<b style='color: #7FFFD4;'>Safe Browser URL Launcher</b>"))

        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com...")
        self.url_input.setFixedHeight(34)
        url_row.addWidget(self.url_input, stretch=3)

        open_url_btn = QPushButton("Open URL")
        open_url_btn.setFixedHeight(34)
        open_url_btn.setCursor(Qt.PointingHandCursor)
        open_url_btn.clicked.connect(self._open_url_action)
        url_row.addWidget(open_url_btn, stretch=1)
        url_layout.addLayout(url_row)
        right_layout.addWidget(url_card)

        # Preset Workflows
        wf_card = LiquidGlassCard(right_panel, corner_radius=16)
        wf_layout = QVBoxLayout(wf_card)
        wf_layout.setContentsMargins(14, 12, 14, 12)
        wf_layout.addWidget(QLabel("<b style='color: #00C8FF;'>Preset Safe Workflows</b>"))

        for wf_id, wf_data in self.automation_service.get_registered_workflows().items():
            wf_row = QHBoxLayout()
            w_txt = QVBoxLayout()
            w_txt.addWidget(QLabel(f"<b>{wf_data['name']}</b>"))
            w_txt.addWidget(QLabel(f"<span style='color: #A0AEC0; font-size: 11px;'>{wf_data['description']}</span>"))
            wf_row.addLayout(w_txt, stretch=1)

            run_btn = QPushButton("Execute")
            run_btn.setFixedSize(70, 30)
            run_btn.setCursor(Qt.PointingHandCursor)
            run_btn.clicked.connect(lambda _, wid=wf_id: self._run_workflow_action(wid))
            wf_row.addWidget(run_btn)
            wf_layout.addLayout(wf_row)

        right_layout.addWidget(wf_card, stretch=1)
        mid_splitter.addWidget(right_panel)

        layout.addWidget(mid_splitter, stretch=2)

        # Audit Log Card
        audit_card = LiquidGlassCard(self, corner_radius=16)
        audit_layout = QVBoxLayout(audit_card)
        audit_layout.setContentsMargins(14, 10, 14, 10)
        audit_layout.addWidget(QLabel("<b style='color: #A0AEC0;'>Automation Security Audit Log</b>"))

        self.audit_display = QTextEdit()
        self.audit_display.setReadOnly(True)
        self.audit_display.setFixedHeight(110)
        self.audit_display.setStyleSheet("background-color: rgba(10, 15, 30, 200); font-family: Consolas; font-size: 11px;")
        audit_layout.addWidget(self.audit_display)

        layout.addWidget(audit_card, stretch=1)

    def refresh_system_status(self):
        res = self.automation_service.get_system_status()
        if res.success:
            self.telemetry_content.setText(res.message)

    def refresh_audit_log(self):
        logs = self.automation_service.get_audit_log()
        lines = []
        for log in reversed(logs):
            status = "SUCCESS" if log.success else "DENIED"
            lines.append(f"[{log.timestamp[:19]}] [{status}] {log.action}: {log.message}")
        self.audit_display.setText("\n".join(lines))

    def _launch_app_action(self, app_id: str):
        # First attempt without confirmation
        res = self.automation_service.launch_app(app_id, user_confirmed=False)
        if not res.success and res.data and res.data.get("needs_confirmation"):
            reply = QMessageBox.question(
                self,
                "Confirmation Required",
                f"Confirm launching '{app_id}'?\n\n{res.message}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                res = self.automation_service.launch_app(app_id, user_confirmed=True)

        if res.success:
            show_info_message("Automation", res.message)
        else:
            show_error_message("Automation", res.message)
        self.refresh_audit_log()

    def _open_url_action(self):
        url = self.url_input.text().strip()
        if not url:
            show_error_message("Validation Error", "URL cannot be blank.")
            return

        res = self.automation_service.open_url(url, user_confirmed=True)
        if res.success:
            self.url_input.clear()
            show_info_message("URL Launcher", res.message)
        else:
            show_error_message("Security Rejection", res.message)
        self.refresh_audit_log()

    def _run_workflow_action(self, wf_id: str):
        res = self.automation_service.execute_workflow(wf_id, user_confirmed=True)
        if res.success:
            show_info_message("Workflow Complete", res.message)
        else:
            show_error_message("Workflow Error", res.message)
        self.refresh_audit_log()
