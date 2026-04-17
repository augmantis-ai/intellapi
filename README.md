# 🚀 Intellapi

**An intelligent, AI-powered system that reads your code and automatically writes your API documentation.**

**Stop writing API docs. Let your code do it for you.**

---

## 📖 What is Intellapi?

In modern software, an **API** (Application Programming Interface) is how different computer systems talk to each other. For example, when your phone's weather app wants the latest forecast, it asks a weather API.

However, **documenting** these APIs so that other programmers know exactly how to use them is historically tedious, confusing, and constantly out-of-date.

**Intellapi is the solution.** It acts like an incredibly smart robot that reads through your entire backend codebase, understands exactly how your software works without breaking anything, and then uses advanced AI to automatically write crystal-clear, professional documentation for you. 

## ✨ Key Features
- **Zero Risk:** It reads your code safely like a book. It never actually runs or executes your software.
- **Privacy First:** We don't send your secret keys, passwords, or irrelevant files to the AI. Only the structural shape of your code is analyzed.
- **Smart Detection:** Point it at a folder, and it will automatically detect what programming language and framework your engineering team used.
- **Brings Its Own Brain:** Works with the AI provider you trust—including AWS Bedrock, Anthropic (Claude), and OpenAI systems.

---

## 💻 Getting Started (Installation & Setup)

Getting Intellapi running on your computer takes just a few minutes.

### 1. Install the Tool
You can install Intellapi directly using Python's package manager.
Open your terminal (Command Prompt/PowerShell/Terminal) and run:
```bash
pip install intellapi
```

### 2. Initial Setup
Once installed, initialize the setup wizard:
```bash
intellapi init
```
This will interactively help you configure which AI model you want to use (like Claude or OpenAI) and where your API keys are securely stored.

### 3. Generate Your Documentation!
Navigate to the folder containing your backend project and tell Intellapi to get to work:
```bash
cd your-backend-project
intellapi generate
```
That's it! Intellapi will scan the folder and generate a professional `API_DOCUMENTATION.md` file inside your project.

---

## 🌐 Supported Frameworks

Intellapi is incredibly smart and currently understands the following backend technologies automatically:

| Language | Framework | What we extract automatically |
|----------|-----------|------------------------------|
| Python | **FastAPI** | Routes, Handlers, Parameters, Models, and Authentication |
| Python | **Flask** | Routes, Blueprints, Payloads, and Auth Hints |
| Python | **Django REST** | Views, Routers, Serializers, and Custom Actions |
| JavaScript/TypeScript | **Express.js** | Routes, App prefixes, Payloads, and Auth Hints |
| JavaScript/TypeScript | **Next.js** | App Router and Pages Router API handlers |
| JavaScript/TypeScript | **SvelteKit** | Server endpoints, Parameters, and JSON handlers |

---

## 🤖 Supported AI Providers

You have full control over which AI engine powers your documentation generation:

| Provider | Setup Note |
|----------|------------|
| **AWS Bedrock** | Uses your standard secure AWS credentials. Perfect for highly sensitive enterprise environments. |
| **Anthropic (Claude)** | Highly recommended. Fast and intelligent. Provide your API key during setup. Your key is kept secure inside your OS. |
| **OpenAI-Compatible** | Works with standard OpenAI, completely private local models (like Ollama/vLLM), and all major AI Gateways and Inference platforms (OpenRouter, Groq, Together AI, LiteLLM, Portkey, etc.). |

---

## ⚙️ Advanced Configuration (For Developers)

Global configurations are stored safely in `~/.intellapi/config.yml`. Project-specific settings live in a `.intellapi.yml` file located at the root of your project folder. 

**Example custom project `.intellapi.yml` configuration:**
```yaml
output_format: md
output_filename: API_DOCUMENTATION.md
exclude:
  - "tests/"
  - "migrations/"
```

**Helpful CLI Commands:**
- `intellapi generate --path ./backend` (Run generation on a specific folder)
- `intellapi generate --dry-run` (Test the scanner without calling the AI)
- `intellapi generate --openapi-file ./openapi.json` (Merge your scan with an existing OpenAPI spec file)
- `intellapi doctor` (Check if your system is configured correctly)
- `intellapi config set model gpt-4o-mini` (Change your default AI engine via terminal)

---

## 🔬 Technical Architecture

For the deeply technical folks, here is what powers Intellapi under the hood:

* **AST Extraction Engine:** We utilize industry-standard `tree-sitter` (and its JavaScript/TypeScript bindings) to convert source code into an Abstract Syntax Tree (AST). This allows flawless, incremental parsing of the backend structure statically, bypassing the massive security risks associated with importing or executing untrusted Python/JS files directly.
* **Intelligent Routing Synthesis:** Our Python/Node Extractors systematically trace dynamic route parameters, nested router architectures, and controller mounts to build a custom abstract Intermediate Representation (IR) tree.
* **Pydantic Validation:** Strict response enforcement and settings management are driven by `Pydantic`, ensuring the LLM's outputs conform instantly to standardized documentation schemas before rendering.
* **Templating Layer:** Outputs are rendered programmatically via `Jinja2`, separating logic synthesis from final Markdown styling.

## 📄 License
MIT License
