# DeepTutor Installation & Setup Guide (Clean Install)

This guide provides complete, step-by-step instructions to perform a **clean installation** of DeepTutor with the new **Document & Chat Export** features (PDF, Responsive EPUB, Word DOCX, and Markdown).

---

## 📑 Table of Contents
1. [Key Features of this Build](#key-features-of-this-build)
2. [System Prerequisites](#system-prerequisites)
3. [Quick Start (Clean Installation)](#quick-start-clean-installation)
   - [Windows (PowerShell)](#windows-powershell)
   - [macOS & Linux (Terminal)](#macos--linux-terminal)
4. [Configuring LLM Providers / API Keys](#configuring-llm-providers--api-keys)
5. [Running DeepTutor](#running-deeptutor)
6. [Running Side-by-Side with an Existing DeepTutor Install](#running-side-by-side-with-an-existing-deeptutor-install)
7. [Using Document & Chat Export](#using-document--chat-export)
8. [Troubleshooting & FAQs](#troubleshooting--faqs)

---

## 🌟 Key Features of this Build

In addition to DeepTutor's core capabilities (agentic chat, deep solve, deep research, knowledge bases, and multi-agent workflows), this build includes:

- **Vector PDF Export**:
  - Automatically converts Mermaid diagrams into crisp vector `<svg>` drawings.
  - Pre-renders KaTeX / LaTeX mathematical formulas with complete font metrics.
  - Preserves Chart.js visualizations, responsive tables, code blocks, and callout alerts.
- **Screen-Responsive EPUB 3 Export**:
  - Fluid typography and layout tailored for mobile phones, tablets, and e-readers.
  - Diagrams and charts are packaged directly into the EPUB container for 100% offline viewing.
- **Zero-Dependency Architecture**:
  - Leverages DeepTutor's built-in `markdown-it-py` parser.
  - Automatic detection of Google Chrome, Chromium, or Microsoft Edge installed on your PC.
  - Built-in pure-Python EPUB 3 packager (uses standard library `zipfile` fallback).

---

## 💻 System Prerequisites

Before starting, ensure your system has the following installed:

| Requirement | Supported Versions | Notes |
| :--- | :--- | :--- |
| **Operating System** | Windows 10/11, macOS 12+, Ubuntu 20.04+ (or any modern Linux) | 64-bit architecture |
| **Python** | 3.11, 3.12, 3.13, 3.14 | Recommended: Python 3.11 or 3.12 |
| **Node.js & npm** | Node.js 20 LTS or 22 LTS | Required for the Web interface (`npm` bundled) |
| **Web Browser** | Google Chrome, Chromium, or Microsoft Edge | Used automatically in headless mode for vector PDF/EPUB rendering |
| **Git** | Latest stable | To clone and pull updates |

> [!TIP]
> On Windows, Microsoft Edge comes pre-installed and is recognized automatically. On macOS and Linux, ensure Google Chrome or Chromium is installed.

---

## 🚀 Quick Start (Clean Installation)

### Windows (PowerShell)

Open PowerShell as your regular user (or in Windows Terminal):

```powershell
# 1. Clone the repository
git clone https://github.com/gunjanj20000/DT.git
cd DT

# 2. Create and activate a Python virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# (If PowerShell blocks script execution, run: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass)

# 3. Upgrade pip and install Python dependencies
python -m pip install --upgrade pip
pip install -r requirements/full.txt
pip install -e . --no-deps

# 4. Install frontend dependencies
cd web
npm ci --legacy-peer-deps
cd ..

# 5. Launch DeepTutor
deeptutor start
```

---

### macOS & Linux (Terminal)

Open your terminal:

```bash
# 1. Clone the repository
git clone https://github.com/gunjanj20000/DT.git
cd DT

# 2. Create and activate a Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Upgrade pip and install Python dependencies
python -m pip install --upgrade pip
pip install -r requirements/full.txt
pip install -e . --no-deps

# 4. Install frontend dependencies
cd web
npm ci --legacy-peer-deps
cd ..

# 5. Launch DeepTutor
deeptutor start
```

---

## 🔑 Configuring LLM Providers / API Keys

DeepTutor connects to OpenAI, Google Gemini, Anthropic Claude, Groq, DeepSeek, Ollama, and other providers.

### Option 1: Via the Web UI (Easiest)
1. Open DeepTutor in your browser (`http://localhost:3782`).
2. Navigate to **Settings** (gear icon in the sidebar) -> **Models** or **Providers**.
3. Enter your API key (e.g., Google Gemini, OpenAI, or Anthropic) and select your active model.

### Option 2: Via Environment Variables
You can also set your keys in your shell before launching:

```bash
# Examples:
export GEMINI_API_KEY="your-gemini-key"
export OPENAI_API_KEY="your-openai-key"
export ANTHROPIC_API_KEY="your-anthropic-key"
```

On Windows PowerShell:
```powershell
$env:GEMINI_API_KEY="your-gemini-key"
$env:OPENAI_API_KEY="your-openai-key"
```

---

## 🖥️ Running DeepTutor

Start the complete application (backend API + frontend Web UI):

```bash
deeptutor start
```

- **Web UI URL**: `http://localhost:3782`
- **Backend API URL**: `http://localhost:8001`

### Running Backend or Frontend Separately (Optional for Developers)
If you prefer running them in separate terminal tabs:
```bash
# Terminal 1 (API Server):
deeptutor serve --host 127.0.0.1 --port 8001 --reload

# Terminal 2 (Web UI):
cd web
npm run dev
```

---

## 🔀 Running Side-by-Side with an Existing DeepTutor Install

If you already have another DeepTutor version installed on your PC, you can run this build completely independently without conflicts by setting a custom `DEEPTUTOR_HOME` and using an alternate port:

### On Windows (PowerShell):
```powershell
$env:DEEPTUTOR_HOME="$HOME\.deeptutor_export"
deeptutor start --port 8002
```

### On macOS / Linux:
```bash
DEEPTUTOR_HOME=~/.deeptutor_export deeptutor start --port 8002
```

This ensures:
- Chat logs, notes, and vector databases stay in their own isolated directory (`.deeptutor_export`).
- The web server runs on port `8002` (frontend on `3783`), avoiding port collisions with your existing install.

---

## 📤 Using Document & Chat Export

### 1. Exporting from the Notebook / Co-Writer
1. Open any document or note in **Notebook**.
2. Click the **`...` (Actions)** dropdown in the top-right toolbar.
3. Select **Export PDF** or **Export EPUB** (in addition to Markdown and Word).
4. The file downloads directly to your device with diagrams, charts, and formulas intact.

### 2. Exporting an Entire Chat Session
1. In the chat view, click the **`...` menu** at the top right of the session header.
2. Choose **Export as PDF** or **Export as EPUB**.

### 3. Exporting a Single Message / Answer
1. Hover over any assistant response bubble.
2. Click the **Export icon** in the message action bar.
3. Choose **Export as PDF** or **Export as EPUB** (or DOCX / Markdown) to download only that specific answer.

---

## 🛠️ Troubleshooting & FAQs

### Q1: `command not found: deeptutor`
**Cause**: The virtual environment is not activated, or the package was not linked.  
**Solution**:
1. Activate your virtual environment:
   - Windows: `.\.venv\Scripts\Activate.ps1`
   - Linux/Mac: `source .venv/bin/activate`
2. Run `pip install -e . --no-deps`.

### Q2: `Port 3782 or 8001 is already in use`
**Cause**: Another instance of DeepTutor or another service is running on that port.  
**Solution**:
Specify a different port:
```bash
deeptutor start --port 8002
```

### Q3: `npm ci fails with peer dependency conflict`
**Cause**: Strict npm dependency resolution.  
**Solution**:
Always run npm with the legacy peer deps flag:
```bash
cd web
npm ci --legacy-peer-deps
```

### Q4: Browser rendering not detecting Chrome
**Cause**: Chrome or Edge is installed in a non-standard location.  
**Solution**:
Set the `CHROME_BIN` environment variable pointing directly to your browser binary:
- Windows: `$env:CHROME_BIN="C:\Path\To\chrome.exe"`
- Linux/Mac: `export CHROME_BIN="/path/to/google-chrome"`

---

## 📚 Helpful Commands Quick Reference

| Command | Description |
| :--- | :--- |
| `deeptutor start` | Start both backend and frontend together |
| `deeptutor chat` | Interactive terminal REPL |
| `deeptutor module list` | Inspect installed and enabled modules |
| `deeptutor kb list` | List knowledge bases |
| `deeptutor serve --port 8001` | Start API server only |
| `git pull` | Update your installation with the latest improvements |
