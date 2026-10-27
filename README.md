# JARVIS AI — Personal Windows Desktop AI Assistant

JARVIS AI is a cloud-powered personal desktop AI assistant built natively with **Python**, **PySide6**, and the modern official **Google Gen AI SDK** (`google-genai`). Featuring a dark glassmorphic ("Liquid Glass") user interface and animated AI core visualization, JARVIS provides intelligent chat, persistent task management, long-term memory personalization, safe Windows automation, and Gmail integration.

---

## ✨ Key Capabilities

- **Liquid Glass Interface**: High-tech translucent visual aesthetic with custom gradients and responsive layouts built natively on Qt/PySide6.
- **Animated AI Core**: Dynamic Arc Reactor core visualization reflecting real-time AI states (*Idle*, *Thinking*, *Speaking*, *Error*).
- **Google Gen AI SDK (`google-genai`)**: Centralized Gemini AI integration with model support (`gemini-2.0-flash`, `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-1.5-flash`, `gemini-1.5-pro`) and memory context injection.
- **Persistent Task Management**: Full SQLite-backed task tracking with CRUD operations, priority levels (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), due dates, status toggles, filtering, and real-time search.
- **Memory & Personalization Service**: Persistent context store and user preferences (name, communication tone, programming preferences). Injects relevant memories into Gemini prompts; automatically rejects sensitive credentials or secrets.
- **Safe Windows Automation**: Controlled action allowlist for approved apps (Notepad, Calculator, File Explorer, Paint, Task Manager, Command Prompt), validated HTTP/HTTPS URL opening, system resource telemetry, and multi-step workflows. Consequential actions require explicit user confirmation.
- **Google Gmail Integration**: Official Google Gmail API integration using OAuth 2.0 InstalledAppFlow, mailbox search, message detail viewing, draft saving, and strictly user-confirmed email dispatching.
- **Provider-Independent Voice Architecture**: Non-blocking text-to-speech abstraction supporting Windows SAPI and designed for future Edge TTS / Kokoro TTS integrations.
- **Secure Key Storage**: API keys and tokens stored securely via the OS Keyring / Credential Manager with encrypted local fallbacks.

---

## 🛠️ Project Architecture

```
G-AI_ASSISTANT/
├── main.py                  # Application entry point with qasync event loop integration
├── Jarvis_UI.py             # Main window controller, navigation, and chat handling
├── ui_views.py              # Dedicated Liquid Glass widgets for Tasks, Memory, Email, Automation
├── gemini_api.py            # Centralized Google Gen AI provider with memory context injection
├── task_service.py          # SQLite-backed persistent task manager (CRUD, filtering, search)
├── memory_service.py        # Persistent context & personalization service with secret filtering
├── gmail_service.py         # Official Gmail API service (OAuth 2.0, mailbox, drafts, safe send)
├── automation_service.py    # Windows automation engine (allowlist, safe URLs, system telemetry)
├── voice_service.py         # Provider-independent text-to-speech engine (Windows SAPI / mock)
├── ai_core_visualization.py # Animated Arc Reactor AI Core widget
├── gui_components.py        # Liquid Glass UI card and background widgets
├── config.py                # Configuration and secure credential manager (Keyring + fallback)
├── utils.py                 # Application-wide logging and message dialogs
├── requirements.txt         # Project dependencies
├── tests/                   # Comprehensive automated test suite (35 unit tests)
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_gemini_api.py
│   ├── test_task_service.py
│   ├── test_memory_service.py
│   ├── test_gmail_service.py
│   ├── test_automation_service.py
│   └── test_voice_service.py
└── data/                    # Local persistent storage (.gitignore protected)
```

---

## 🚀 Getting Started

### Prerequisites

- **Windows 10 / 11**
- **Python 3.11+**
- **Google Gemini API Key**: Obtain a key from [Google AI Studio](https://aistudio.google.com/).

### Installation

1. **Clone or Open the Repository**:
   ```bash
   cd C:\Users\welcome\.gemini\antigravity\scratch\G-AI_ASSISTANT
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Launch Application**:
   ```bash
   python main.py
   ```

---

## ⚙️ Configuration & Setup

1. **Gemini API Key**:
   - Open JARVIS AI and click **Settings** (⚙️) on the sidebar.
   - Enter your Gemini API key and select your preferred model (`gemini-2.0-flash`).
   - Click **Save & Validate Credentials**. Your key will be securely saved into the Windows Credential Manager.

2. **Gmail OAuth Integration** (Optional):
   - In Google Cloud Console, enable the **Gmail API** and create **OAuth 2.0 Client ID (Desktop app)** credentials.
   - Download the client secrets file and place it at:
     ```
     data/gmail_credentials.json
     ```
   - Navigate to the **Email** tab (📧) and click **Connect Account** to authorize via browser.

3. **Windows Automation**:
   - Applications are executed from the strictly controlled allowlist without shell interpreters.
   - You can toggle confirmation requirements under **Settings** > **Automation Security**.

4. **Running Tests**:
   ```bash
   python -m pytest tests --rootdir=. -o cache_dir=.pytest_cache -v
   ```

---

## 📄 License

Distributed under the MIT License.
