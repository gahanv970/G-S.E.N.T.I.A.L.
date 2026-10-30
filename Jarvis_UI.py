import asyncio
import html
import logging
from pathlib import Path
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from qasync import asyncSlot

from ai_core_visualization import AICoreVisualization
from automation_service import WindowsAutomationService
from config import APP_DIR, get_config_value, get_secret, load_config, save_config, set_secret
from gemini_api import DEFAULT_MODEL, SUPPORTED_MODELS, GeminiAIProvider
from gmail_service import GmailService
from gui_components import LiquidGlassBackground, LiquidGlassCard
from memory_service import MemoryService
from microphone_service import MicrophoneService, transcribe_audio_bytes
from task_service import TaskService
from ui_views import (
    AutomationManagementWidget,
    EmailManagementWidget,
    MemoryManagementWidget,
    TaskManagementWidget,
    WhatsAppCompanionWidget,
)
from whatsapp_service import WhatsAppService
from utils import show_error_message, show_info_message
from voice_service import VoiceManager

logger = logging.getLogger(__name__)

MASKED_KEY = "********"


class JarvisMainWindow(QMainWindow):
    """
    The main window for the JARVIS AI desktop assistant, featuring a Liquid Glass UI.
    Houses Chat, Email, Automation, Tasks, Memory, and Settings views.
    """

    ai_state_changed = Signal(str)  # Updates the AI core visualization state

    def __init__(self):
        super().__init__()
        self.setWindowTitle("JARVIS AI Assistant - Personal Desktop Intelligence")
        self.resize(1200, 800)
        self.setMinimumSize(1024, 768)

        # Initialize Services
        self.ai_provider = GeminiAIProvider()
        self.task_service = TaskService()
        self.memory_service = MemoryService()
        self.gmail_service = GmailService()
        self.whatsapp_service = WhatsAppService()
        self.automation_service = WindowsAutomationService()
        self.voice_manager = VoiceManager()
        self.mic_service = MicrophoneService(self)

        self.conversation_history = []  # list of (role, text) tuples, role in {"User", "JARVIS"}
        self._busy = False
        self._sidebar_buttons = []

        # Timer to reset core visualization state back to idle
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(lambda: self.ai_state_changed.emit("idle"))

        self._setup_ui()
        self._load_settings()

        self.ai_state_changed.emit("idle")
        logger.info("JARVIS AI application initialized successfully.")

    # ------------------------------------------------------------------ UI Setup

    def _setup_ui(self):
        """Initializes the Liquid Glass GUI components and layout."""
        self.background_widget = LiquidGlassBackground(self)
        self.setCentralWidget(self.background_widget)

        self.root_layout = QHBoxLayout(self.background_widget)
        self.root_layout.setContentsMargins(15, 15, 15, 15)
        self.root_layout.setSpacing(15)

        # --- Left sidebar (navigation) ---
        self.sidebar = LiquidGlassCard(self.background_widget, corner_radius=24)
        self.sidebar.setFixedWidth(210)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(12, 24, 12, 18)
        sidebar_layout.setSpacing(10)

        # App Title in Sidebar
        app_title = QLabel("JARVIS AI")
        app_title.setAlignment(Qt.AlignCenter)
        app_title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        app_title.setStyleSheet("color: #00C8FF; margin-bottom: 15px;")
        sidebar_layout.addWidget(app_title)

        nav_items = [
            ("💬 Chat", 0),
            ("📧 Email", 1),
            ("📱 WhatsApp", 2),
            ("⚡ Automation", 3),
            ("📋 Tasks", 4),
            ("🧠 Memory", 5),
            ("⚙️ Settings", 6),
        ]

        for text, index in nav_items:
            btn = self._add_sidebar_button(text, index)
            self._sidebar_buttons.append(btn)

        sidebar_layout.addStretch()

        # Version stamp
        ver_lbl = QLabel("v2.0 Liquid Glass")
        ver_lbl.setAlignment(Qt.AlignCenter)
        ver_lbl.setStyleSheet("color: #4A5568; font-size: 11px;")
        sidebar_layout.addWidget(ver_lbl)

        self.root_layout.addWidget(self.sidebar)

        # --- Main content area ---
        self.content_area = QWidget(self.background_widget)
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)

        self.stacked_widget = QStackedWidget(self.content_area)
        self.content_layout.addWidget(self.stacked_widget)

        # 0: Chat View
        self._setup_chat_view()
        self.stacked_widget.addWidget(self.chat_view)

        # 1: Email View
        self.email_view = EmailManagementWidget(self.gmail_service, self.content_area)
        self.stacked_widget.addWidget(self.email_view)

        # 2: WhatsApp Personal Companion View
        self.whatsapp_view = WhatsAppCompanionWidget(self.whatsapp_service, self.content_area)
        self.stacked_widget.addWidget(self.whatsapp_view)

        # 3: Windows Automation View
        self.automation_view = AutomationManagementWidget(self.automation_service, self.content_area)
        self.stacked_widget.addWidget(self.automation_view)

        # 4: Task Management View
        self.task_view = TaskManagementWidget(self.task_service, self.content_area)
        self.stacked_widget.addWidget(self.task_view)

        # 5: Memory & Personalization View
        self.memory_view = MemoryManagementWidget(self.memory_service, self.content_area)
        self.stacked_widget.addWidget(self.memory_view)

        # 6: Settings View
        self._setup_settings_view()
        self.stacked_widget.addWidget(self.settings_view)

        self.stacked_widget.currentChanged.connect(self._on_page_changed)
        self.root_layout.addWidget(self.content_area, stretch=1)

        # Set initial active tab
        self._update_sidebar_styles(0)

        self.setStyleSheet("""
            QMainWindow {
                background: transparent;
            }
            QLabel, QPushButton, QLineEdit, QTextEdit, QComboBox, QCheckBox {
                font-family: 'Segoe UI', 'Roboto', sans-serif;
                color: #E0E0E0;
            }
            QPushButton {
                background-color: rgba(255, 255, 255, 20);
                border: 1px solid rgba(255, 255, 255, 40);
                border-radius: 10px;
                padding: 8px 15px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: rgba(0, 200, 255, 40);
                border: 1px solid rgba(0, 200, 255, 120);
            }
            QPushButton:pressed {
                background-color: rgba(0, 150, 200, 70);
            }
            QPushButton:disabled {
                background-color: rgba(255, 255, 255, 10);
                color: rgba(224, 224, 224, 80);
                border: 1px solid rgba(255, 255, 255, 15);
            }
            QLineEdit, QTextEdit, QComboBox {
                background-color: rgba(15, 23, 42, 180);
                border: 1px solid rgba(0, 200, 255, 60);
                border-radius: 10px;
                padding: 8px 12px;
                selection-background-color: #00C8FF;
                selection-color: #000000;
            }
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
                border: 1px solid rgba(0, 200, 255, 180);
            }
            QComboBox QAbstractItemView {
                background-color: #0F172A;
                color: #FFFFFF;
                selection-background-color: #00C8FF;
                selection-color: #000000;
                border: 1px solid #00C8FF;
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                border: none;
                background: rgba(255, 255, 255, 10);
                width: 8px;
                margin: 0px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgba(0, 200, 255, 120);
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                background: none;
            }
        """)

    def _add_sidebar_button(self, text, page_index):
        """Creates a styled sidebar navigation button."""
        button = QPushButton(text)
        button.setFixedHeight(42)
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(page_index))
        self.sidebar.layout().addWidget(button)
        return button

    def _on_page_changed(self, index):
        """Updates active sidebar button styling and refreshes view data."""
        self._update_sidebar_styles(index)
        if index == 1:
            self.email_view.update_auth_status()
        elif index == 2:
            self.whatsapp_view.refresh_all()
        elif index == 3:
            self.automation_view.refresh_system_status()
            self.automation_view.refresh_audit_log()
        elif index == 4:
            self.task_view.refresh_tasks()
        elif index == 5:
            self.memory_view.refresh_memories()

    def _update_sidebar_styles(self, active_index):
        """Highlights the active sidebar navigation tab."""
        for i, btn in enumerate(self._sidebar_buttons):
            if i == active_index:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(0, 200, 255, 70);
                        border: 1px solid rgba(0, 200, 255, 180);
                        color: #FFFFFF;
                        font-weight: bold;
                    }
                """)
            else:
                btn.setStyleSheet("")

    def _setup_chat_view(self):
        """Sets up the main interactive chat interface."""
        self.chat_view = QWidget(self.content_area)
        chat_layout = QVBoxLayout(self.chat_view)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(15)

        # Top section: Core animation & status card
        top_panel = QWidget(self.chat_view)
        top_panel_layout = QHBoxLayout(top_panel)
        top_panel_layout.setContentsMargins(0, 0, 0, 0)
        top_panel_layout.setSpacing(15)

        self.ai_core_viz = AICoreVisualization(self.chat_view)
        self.ai_core_viz.setFixedSize(220, 220)
        top_panel_layout.addWidget(self.ai_core_viz, alignment=Qt.AlignCenter)
        self.ai_state_changed.connect(self.ai_core_viz.set_state)

        status_card = LiquidGlassCard(self.chat_view, corner_radius=24)
        status_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(20, 15, 20, 15)

        status_header = QLabel("<h3 style='color: #00C8FF; margin: 0;'>System Overview</h3>")
        status_layout.addWidget(status_header)

        self.ai_status_label = QLabel("AI Engine: Initializing...")
        self.ai_status_label.setFont(QFont("Segoe UI", 10))
        self.model_status_label = QLabel(f"Active Model: {DEFAULT_MODEL}")
        self.model_status_label.setFont(QFont("Segoe UI", 10))

        status_layout.addWidget(self.ai_status_label)
        status_layout.addWidget(self.model_status_label)

        # Clear chat history button in status card (does NOT touch tasks or persistent memories)
        self.clear_chat_button = QPushButton("Clear Chat History")
        self.clear_chat_button.setFixedHeight(32)
        self.clear_chat_button.setCursor(Qt.PointingHandCursor)
        self.clear_chat_button.clicked.connect(self._clear_chat_history)
        status_layout.addWidget(self.clear_chat_button)

        status_layout.addStretch()

        top_panel_layout.addWidget(status_card)
        chat_layout.addWidget(top_panel)

        # Conversation display widget
        self.conversation_display = QTextEdit(self.chat_view)
        self.conversation_display.setReadOnly(True)
        self.conversation_display.setFont(QFont("Segoe UI", 10))
        self.conversation_display.setPlaceholderText("JARVIS is ready. Ask me anything!")
        chat_layout.addWidget(self.conversation_display, stretch=1)

        # Command input row
        input_panel = QWidget(self.chat_view)
        input_layout = QHBoxLayout(input_panel)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(10)

        self.mic_button = QPushButton("🎤")
        self.mic_button.setFixedSize(42, 42)
        self.mic_button.setCursor(Qt.PointingHandCursor)
        self.mic_button.setToolTip("Click to start/stop voice recording")
        self.mic_button.clicked.connect(self._toggle_microphone_recording)
        input_layout.addWidget(self.mic_button)

        self.command_input = QLineEdit(self.chat_view)
        self.command_input.setPlaceholderText("Ask JARVIS or type a command...")
        self.command_input.setFont(QFont("Segoe UI", 10))
        self.command_input.setFixedHeight(42)
        self.command_input.returnPressed.connect(self._send_command)
        input_layout.addWidget(self.command_input)

        self.send_button = QPushButton("Send")
        self.send_button.setFixedSize(90, 42)
        self.send_button.setCursor(Qt.PointingHandCursor)
        self.send_button.clicked.connect(self._send_command)
        input_layout.addWidget(self.send_button)

        chat_layout.addWidget(input_panel)

    def _setup_settings_view(self):
        """Sets up comprehensive configuration settings for API keys, models, memory, automation, and voice."""
        self.settings_view = QWidget(self.content_area)
        settings_layout = QVBoxLayout(self.settings_view)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(15)

        scroll_area = QScrollArea(self.settings_view)
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(15)
        scroll_area.setWidget(scroll_content)
        settings_layout.addWidget(scroll_area)

        # 1. Gemini API Config Card
        gemini_card = LiquidGlassCard(scroll_content, corner_radius=20)
        gemini_layout = QVBoxLayout(gemini_card)
        gemini_layout.setContentsMargins(20, 16, 20, 16)
        scroll_layout.addWidget(gemini_card)

        gemini_layout.addWidget(QLabel("<h3 style='color: #00C8FF; margin: 0;'>Google Gemini AI Configuration</h3>"))

        gemini_layout.addWidget(QLabel("Gemini API Key (stored securely in OS Keyring / Credential Manager):"))
        self.gemini_api_key_input = QLineEdit()
        self.gemini_api_key_input.setEchoMode(QLineEdit.Password)
        self.gemini_api_key_input.setPlaceholderText("Enter AI Studio API Key (AIzaSy...)")
        gemini_layout.addWidget(self.gemini_api_key_input)

        gemini_layout.addWidget(QLabel("Active Gemini Model:"))
        self.gemini_model_selector = QComboBox()
        self.gemini_model_selector.setEditable(True)
        self.gemini_model_selector.addItems(SUPPORTED_MODELS)
        gemini_layout.addWidget(self.gemini_model_selector)

        self.save_key_button = QPushButton("Save & Validate Credentials")
        self.save_key_button.setFixedHeight(40)
        self.save_key_button.setCursor(Qt.PointingHandCursor)
        self.save_key_button.clicked.connect(self._save_and_test_gemini_key)
        gemini_layout.addWidget(self.save_key_button)

        # 2. Personalization & Memory Card
        mem_card = LiquidGlassCard(scroll_content, corner_radius=20)
        mem_layout = QVBoxLayout(mem_card)
        mem_layout.setContentsMargins(20, 16, 20, 16)
        scroll_layout.addWidget(mem_card)

        mem_layout.addWidget(QLabel("<h3 style='color: #7FFFD4; margin: 0;'>Memory & Context Injection</h3>"))
        self.mem_enabled_checkbox = QCheckBox("Enable long-term memory and user preferences injection into AI prompts")
        self.mem_enabled_checkbox.setChecked(self.memory_service.is_memory_enabled())
        self.mem_enabled_checkbox.toggled.connect(self._on_memory_checkbox_toggled)
        mem_layout.addWidget(self.mem_enabled_checkbox)

        # 3. Windows Automation Security Card
        auto_card = LiquidGlassCard(scroll_content, corner_radius=20)
        auto_layout = QVBoxLayout(auto_card)
        auto_layout.setContentsMargins(20, 16, 20, 16)
        scroll_layout.addWidget(auto_card)

        auto_layout.addWidget(QLabel("<h3 style='color: #FFAA00; margin: 0;'>Automation Security</h3>"))
        self.confirm_auto_checkbox = QCheckBox("Require explicit confirmation before launching applications or workflows")
        self.confirm_auto_checkbox.setChecked(bool(get_config_value("automation_require_confirmation", True)))
        self.confirm_auto_checkbox.toggled.connect(self._on_automation_confirm_toggled)
        auto_layout.addWidget(self.confirm_auto_checkbox)

        # 4. Voice Controls Card
        voice_card = LiquidGlassCard(scroll_content, corner_radius=20)
        voice_layout = QVBoxLayout(voice_card)
        voice_layout.setContentsMargins(20, 16, 20, 16)
        scroll_layout.addWidget(voice_card)

        voice_layout.addWidget(QLabel("<h3 style='color: #00C8FF; margin: 0;'>Voice Engine Configuration</h3>"))
        voice_row = QHBoxLayout()
        self.voice_combo = QComboBox()
        self.voice_combo.addItems(["Disabled", "ElevenLabs TTS (Voice Clone)", "Windows SAPI (Native TTS)"])
        current_voice = get_config_value("voice_provider", "disabled")
        if current_voice == "elevenlabs":
            self.voice_combo.setCurrentText("ElevenLabs TTS (Voice Clone)")
        elif current_voice == "windows_sapi":
            self.voice_combo.setCurrentText("Windows SAPI (Native TTS)")
        else:
            self.voice_combo.setCurrentText("Disabled")
        self.voice_combo.currentIndexChanged.connect(self._on_voice_provider_changed)
        voice_row.addWidget(self.voice_combo, stretch=2)

        test_voice_btn = QPushButton("🔊 Test Voice")
        test_voice_btn.setFixedHeight(36)
        test_voice_btn.setCursor(Qt.PointingHandCursor)
        test_voice_btn.clicked.connect(self._test_voice)
        voice_row.addWidget(test_voice_btn, stretch=1)

        stop_voice_btn = QPushButton("⏹ Stop Audio")
        stop_voice_btn.setFixedHeight(36)
        stop_voice_btn.setCursor(Qt.PointingHandCursor)
        stop_voice_btn.clicked.connect(self.voice_manager.stop)
        voice_row.addWidget(stop_voice_btn, stretch=1)
        voice_layout.addLayout(voice_row)

        voice_layout.addWidget(QLabel("ElevenLabs API Key:"))
        self.elevenlabs_key_input = QLineEdit()
        self.elevenlabs_key_input.setEchoMode(QLineEdit.Password)
        self.elevenlabs_key_input.setPlaceholderText("Enter ElevenLabs API Key...")
        existing_el_key = get_secret("elevenlabs_api_key")
        if existing_el_key:
            self.elevenlabs_key_input.setText(MASKED_KEY)
        voice_layout.addWidget(self.elevenlabs_key_input)

        voice_layout.addWidget(QLabel("ElevenLabs Voice ID:"))
        self.elevenlabs_voice_id_input = QLineEdit()
        self.elevenlabs_voice_id_input.setPlaceholderText("Enter ElevenLabs Voice ID (e.g. 21m00Tcm4TlvDq8ikWAM)...")
        existing_voice_id = get_secret("elevenlabs_voice_id") or get_config_value("elevenlabs_voice_id", "")
        self.elevenlabs_voice_id_input.setText(existing_voice_id)
        voice_layout.addWidget(self.elevenlabs_voice_id_input)

        save_voice_settings_btn = QPushButton("Save Voice Configuration")
        save_voice_settings_btn.setFixedHeight(36)
        save_voice_settings_btn.setCursor(Qt.PointingHandCursor)
        save_voice_settings_btn.clicked.connect(self._save_elevenlabs_credentials)
        voice_layout.addWidget(save_voice_settings_btn)

        self.voice_status_lbl = QLabel(f"Voice Status: {self.voice_manager.get_status()}")
        self.voice_status_lbl.setStyleSheet("color: #A0AEC0; font-size: 11px;")
        voice_layout.addWidget(self.voice_status_lbl)

        # 5. Environment & Storage Card
        storage_card = LiquidGlassCard(scroll_content, corner_radius=20)
        storage_layout = QVBoxLayout(storage_card)
        storage_layout.setContentsMargins(20, 16, 20, 16)
        scroll_layout.addWidget(storage_card)

        storage_layout.addWidget(QLabel("<h3 style='color: #A0AEC0; margin: 0;'>Storage & Data Locations</h3>"))
        storage_info = QLabel(
            f"<b>Application Data:</b> <code>{APP_DIR}</code><br>"
            f"<b>Tasks Database:</b> <code>{APP_DIR / 'tasks.db'}</code><br>"
            f"<b>Memory Database:</b> <code>{APP_DIR / 'memory.db'}</code><br>"
            f"<b>Gmail Credentials:</b> <code>{self.gmail_service.get_credentials_path()}</code>"
        )
        storage_info.setTextFormat(Qt.RichText)
        storage_info.setStyleSheet("color: #718096; font-size: 11px; line-height: 1.5;")
        storage_layout.addWidget(storage_info)

        scroll_layout.addStretch()

    # ------------------------------------------------------------------ Logic & Settings Handlers

    def _on_memory_checkbox_toggled(self, checked: bool):
        self.memory_service.set_memory_enabled(checked)
        self.memory_view.memory_toggle.setChecked(checked)

    def _on_automation_confirm_toggled(self, checked: bool):
        save_config({"automation_require_confirmation": checked})

    def _on_voice_provider_changed(self):
        text = self.voice_combo.currentText()
        if "ElevenLabs" in text:
            provider_type = "elevenlabs"
        elif "Windows SAPI" in text:
            provider_type = "windows_sapi"
        else:
            provider_type = "disabled"
        self.voice_manager.set_provider_type(provider_type)
        self.voice_status_lbl.setText(f"Voice Status: {self.voice_manager.get_status()}")

    def _save_elevenlabs_credentials(self):
        key = self.elevenlabs_key_input.text().strip()
        voice_id = self.elevenlabs_voice_id_input.text().strip()

        if key and key != MASKED_KEY:
            set_secret("elevenlabs_api_key", key)
            self.elevenlabs_key_input.setText(MASKED_KEY)

        if voice_id:
            set_secret("elevenlabs_voice_id", voice_id)
            save_config({"elevenlabs_voice_id": voice_id})

        self.voice_manager.reload_provider()
        self.voice_status_lbl.setText(f"Voice Status: {self.voice_manager.get_status()}")
        show_info_message("Voice Settings Saved", "ElevenLabs TTS credentials and Voice ID updated successfully.")

    def _test_voice(self):
        if not self.voice_manager.is_available():
            show_error_message("Voice Unavailable", f"Voice engine is not available: {self.voice_manager.get_status()}")
            return
        self.voice_manager.speak("Greetings! I am JARVIS, your personal desktop assistant.")

    def _clear_chat_history(self):
        """Clears the chat history without touching persistent tasks or memories."""
        self.conversation_history.clear()
        self.conversation_display.clear()
        show_info_message("Chat Cleared", "Conversation history cleared. Tasks and persistent memories remain intact.")

    def _load_settings(self):
        """Loads non-sensitive config and secure secrets."""
        app_config = load_config()
        model_name = app_config.get("gemini_model", DEFAULT_MODEL)
        self.gemini_model_selector.setCurrentText(model_name)
        self.ai_provider.set_model(model_name)
        self.model_status_label.setText(f"Active Model: {model_name}")

        try:
            stored_key = self.ai_provider.get_api_key_securely()
            if stored_key:
                self.gemini_api_key_input.setText(MASKED_KEY)
                self.ai_provider.set_api_key(stored_key)
                logger.info("Gemini API key restored securely.")
                self.ai_status_label.setText("AI Engine: Ready (API Key Loaded)")
            else:
                logger.warning("No stored API key found.")
                self.ai_status_label.setText("AI Engine: Key Not Configured")
        except Exception as e:
            logger.error(f"Failed to load secure key: {e}")
            self.ai_status_label.setText("AI Engine: Security Error")

    def _current_model_name(self):
        return self.gemini_model_selector.currentText().strip() or DEFAULT_MODEL

    @asyncSlot()
    async def _save_and_test_gemini_key(self):
        """Saves and tests Gemini API Key."""
        api_key = self.gemini_api_key_input.text().strip()
        model_name = self._current_model_name()

        if api_key != MASKED_KEY:
            if not api_key:
                show_error_message("Validation Error", "API Key cannot be blank.")
                return
            try:
                self.ai_provider.save_api_key_securely(api_key)
                self.ai_provider.set_api_key(api_key)
            except Exception as e:
                show_error_message("Storage Error", f"Could not save API key: {e}")
                return

        # Save model preference to config JSON
        save_config({"gemini_model": model_name})
        self.ai_provider.set_model(model_name)
        self.model_status_label.setText(f"Active Model: {model_name}")

        self.save_key_button.setEnabled(False)
        self.ai_status_label.setText("AI Engine: Testing Connection...")
        self.ai_state_changed.emit("thinking")

        try:
            ok = await asyncio.to_thread(self.ai_provider.test_connection, model_name)
            if ok:
                show_info_message("Success", f"Successfully connected to Gemini API with {model_name}!")
                self.ai_status_label.setText("AI Engine: Online & Ready")
                self.gemini_api_key_input.setText(MASKED_KEY)
            else:
                show_error_message("Connection Failed", "Unable to connect with provided credentials/model.")
                self.ai_status_label.setText("AI Engine: Connection Failed")
        except Exception as e:
            show_error_message("Test Error", str(e))
            self.ai_status_label.setText("AI Engine: Test Error")
        finally:
            self.save_key_button.setEnabled(True)
            self.ai_state_changed.emit("idle")

    # ------------------------------------------------------------------ Voice Recording Slot

    @asyncSlot()
    async def _toggle_microphone_recording(self):
        """Starts or stops push-to-talk voice recording and routes transcription to intent pipeline."""
        if self._busy:
            return

        if self.mic_service.is_recording():
            # Stop recording and transcribe
            self.mic_button.setText("🎤")
            self.mic_button.setStyleSheet("")
            self.ai_status_label.setText("AI Engine: Transcribing Audio...")
            self.ai_state_changed.emit("thinking")

            wav_bytes = self.mic_service.stop_recording()
            if not wav_bytes or len(wav_bytes) < 200:
                self.ai_status_label.setText("AI Engine: No Audio Captured")
                self.ai_state_changed.emit("idle")
                return

            try:
                transcript = await asyncio.to_thread(
                    transcribe_audio_bytes, wav_bytes, self.ai_provider
                )
                if transcript:
                    logger.info(f"Speech Recognized: {transcript}")
                    self.command_input.setText(transcript)
                    await self._send_command()
                else:
                    show_info_message("Voice Input", "No speech detected in audio recording.")
                    self.ai_status_label.setText("AI Engine: Online & Ready")
                    self.ai_state_changed.emit("idle")
            except Exception as e:
                show_error_message("Speech Recognition Error", str(e))
                self.ai_status_label.setText("AI Engine: Error")
                self.ai_state_changed.emit("error")
        else:
            if not self.mic_service.has_microphone():
                show_error_message("Microphone Missing", "No microphone input device detected on your system.")
                return

            started = self.mic_service.start_recording()
            if started:
                self.mic_button.setText("🔴")
                self.mic_button.setStyleSheet("background-color: rgba(255, 68, 68, 120); border: 1px solid #FF4444;")
                self.ai_status_label.setText("AI Engine: Recording Voice... Click 🔴 to Stop")
                self.ai_state_changed.emit("speaking")

    # ------------------------------------------------------------------ Chat Slot

    @asyncSlot()
    async def _send_command(self):
        """Handles sending a command to JARVIS AI with intent understanding, safe action confirmation, and voice playback."""
        if self._busy:
            return

        user_text = self.command_input.text().strip()
        if not user_text:
            return

        if not self.ai_provider.is_configured():
            show_error_message(
                "Configuration Needed",
                "Gemini API key is not configured. Please set your key in Settings (⚙️)."
            )
            return

        model_name = self._current_model_name()
        self.command_input.clear()
        self._append_message("User", user_text)

        # Build prompt context from memory service
        system_context = self.memory_service.build_context_for_prompt(user_text)

        self._set_busy(True)
        self._idle_timer.stop()
        self.ai_state_changed.emit("thinking")
        self.ai_status_label.setText("AI Engine: Analyzing Intent...")

        try:
            intent_data = await asyncio.to_thread(
                self.ai_provider.understand_intent, user_text, model_name, system_context
            )

            response_text = intent_data.get("response_text", "")
            intent_type = intent_data.get("intent_type", "general_chat")
            params = intent_data.get("parameters", {})
            requires_confirm = intent_data.get("requires_confirmation", False)

            # Handle intent execution with confirmation and clean spoken feedback
            if intent_type == "launch_app" and "app_id" in params:
                app_id = params["app_id"]
                if requires_confirm:
                    reply = QMessageBox.question(
                        self,
                        "Confirm Application Launch",
                        f"S.E.N.T.I.A.L. wants to launch '{app_id}'. Do you approve?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No,
                    )
                    if reply == QMessageBox.Yes:
                        act_res = self.automation_service.launch_app(app_id, user_confirmed=True)
                        response_text += f"\n[{act_res.message}]"
                    else:
                        response_text = f"Action cancelled. Launching {app_id} was declined."
                else:
                    act_res = self.automation_service.launch_app(app_id, user_confirmed=True)
                    response_text += f"\n[{act_res.message}]"

            elif intent_type == "create_task" and "title" in params:
                task_title = params["title"]
                if requires_confirm:
                    reply = QMessageBox.question(
                        self,
                        "Confirm Task Creation",
                        f"Create task '{task_title}'?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No,
                    )
                    if reply == QMessageBox.Yes:
                        task = self.task_service.create_task(
                            title=task_title,
                            description=params.get("description", ""),
                            priority=params.get("priority", "MEDIUM").upper(),
                            due_date=params.get("due_date"),
                        )
                        response_text += f"\n[Task #{task.id} created successfully]"
                    else:
                        response_text = f"Task creation cancelled for '{task_title}'."

            self._handle_gemini_response(response_text)

            # Speak response via voice manager if enabled
            if self.voice_manager.is_available():
                self.voice_manager.speak(response_text)

        except Exception as e:
            logger.exception("Error processing AI request.")
            self._handle_gemini_error(str(e))
        finally:
            self._set_busy(False)

    def _build_gemini_history(self):
        """Converts conversation history to Gemini list format."""
        return [
            {"role": "user" if role == "User" else "model", "parts": [text]}
            for role, text in self.conversation_history
        ]

    def _set_busy(self, busy):
        self._busy = busy
        self.send_button.setEnabled(not busy)
        self.command_input.setEnabled(not busy)
        self.mic_button.setEnabled(not busy)
        if not busy:
            self.command_input.setFocus()

    def _handle_gemini_response(self, response_text):
        self._append_message("JARVIS", response_text)
        self.ai_state_changed.emit("speaking")
        self.ai_status_label.setText("AI Engine: Online & Ready")
        self._idle_timer.start(2500)

    def _handle_gemini_error(self, error_msg):
        if self.conversation_history and self.conversation_history[-1][0] == "User":
            self.conversation_history.pop()

        self._append_message("JARVIS (System)", f"Error: {error_msg}", store=False)
        self.ai_state_changed.emit("error")
        self.ai_status_label.setText("AI Engine: Error")
        self._idle_timer.start(4000)

    def _append_message(self, sender, text, store=True):
        if store:
            self.conversation_history.append((sender, text))

        color_map = {
            "User": "#00C8FF",
            "JARVIS": "#7FFFD4",
            "JARVIS (System)": "#FF6B6B"
        }
        color = color_map.get(sender, "#E0E0E0")
        safe_text = html.escape(str(text)).replace("\n", "<br>")

        formatted_msg = (
            f'<div style="margin-bottom: 12px;">'
            f'<b style="color: {color}; font-size: 11pt;">{html.escape(sender)}:</b><br>'
            f'<span style="color: #F0F4F8; font-size: 10pt; line-height: 1.4;">{safe_text}</span>'
            f'</div>'
        )

        self.conversation_display.append(formatted_msg)
        bar = self.conversation_display.verticalScrollBar()
        bar.setValue(bar.maximum())
