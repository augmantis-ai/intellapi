# Intellapi

**AI-powered API documentation generator.** Analyze a backend project and generate professional API documentation using the LLM of your choice.

## Features

- **Safe project analysis**: Scans code without importing or running the app
- **Backend detection + picker**: Finds candidate backend folders and lets you choose interactively
- **OpenAPI-assisted generation**: Accepts local or remote OpenAPI specs to supplement source analysis
- **Multi-provider**: OpenAI-compatible endpoints, Anthropic, and AWS Bedrock
- **Privacy-first**: Never sends secrets, credentials, or unnecessary files to the LLM
- **Flexible output**: Markdown, plain text, or both

## Installation

```bash
pip install intellapi
```

Or with [pipx](https://pipx.pypa.io/):

```bash
pipx install intellapi
```

## Quick Start

```bash
intellapi init
cd my-backend-project
intellapi generate
```

Milestones M1-M3 are now in place: the CLI, provider setup, privacy guardrails, backend detection, OpenAPI merge, Python extractors, and Node/TypeScript extractors are implemented. Static analysis is strongest on common routing patterns; when a project uses heavily custom abstractions, OpenAPI input is still the safest fallback.

## Supported Frameworks

| Language | Framework | Current support |
|----------|-----------|-----------------|
| Python | FastAPI | Source extraction for routers, handlers, params, models, and auth hints |
| Python | Flask | Source extraction for routes, blueprints, payloads, and auth hints |
| Python | Django REST | Source extraction for views, routers, serializers, and custom actions |
| JavaScript/TypeScript | Express | Source extraction for app/router routes, mounted prefixes, payloads, and auth hints |
| JavaScript/TypeScript | Next.js | Source extraction for App Router and Pages Router API handlers |
| JavaScript/TypeScript | SvelteKit | Source extraction for `+server` endpoints, params, and JSON handlers |

## LLM Providers

| Provider | Config key | Notes |
|----------|------------|-------|
| AWS Bedrock | `bedrock` | Uses the standard AWS credential chain |
| Anthropic | `anthropic` | API key stored in OS keyring or provided via env |
| OpenAI-compatible | `openai_compatible` | Covers OpenAI, OpenRouter, Ollama, and compatible gateways |

## Configuration

Global config lives in `~/.intellapi/config.yml`. Project config lives in `.intellapi.yml`. Secrets are never stored in config files; use `intellapi init` or environment variables.

Example user config:

```yaml
provider: bedrock
model: anthropic.claude-3-haiku-20240307-v1:0
aws_region: us-east-1
```

Example project config:

```yaml
output_format: md
output_filename: API_DOCUMENTATION.md
exclude:
  - "tests/"
  - "migrations/"
```

## CLI Reference

```bash
intellapi init
intellapi generate
intellapi generate --path ./backend
intellapi generate --dry-run
intellapi generate --openapi-file ./openapi.json
intellapi doctor
intellapi config show
intellapi config set model gpt-4o-mini
```

## License

MIT
