# miniagent

A lightweight coding agent with OpenAI-compatible APIs (Ollama by default).

## Features

- **Auto/Manual Mode**: Switch between automatic tool execution and confirmation-based mode
- **Session Memory**: Maintains conversation context during runtime
- **Rich UI**: Beautiful terminal output with Markdown rendering
- **Tool Support**: Pluggable tool system with bash execution capability
- **Ollama/Cloud Support**: Works with any OpenAI-compatible API

## Installation

```bash
uv sync
```

## Usage

Run with Ollama (default):

```bash
uv run miniagent
```

Run with OpenAI:

```bash
uv run miniagent -m gpt-4o -u https://api.openai.com/v1 -k your_api_key
```

### Commands

- `/auto` - Switch to auto mode (tools run without confirmation)
- `/manual` - Switch to manual mode (confirm before running tools)
- `/quit` - Exit the agent

### Options

- `-m, --model`: Model to use (default: glm-4.7:cloud)
- `-u, --base-url`: API base URL (default: http://localhost:11434/v1)
- `-k, --api-key`: API key (default: ollama)
- `-t, --temperature`: Temperature for response generation (default: 0.7)

## Examples

```bash
# Ollama with custom model
uv run miniagent -m llama3:8b

# OpenAI
uv run miniagent -m gpt-4o -u https://api.openai.com/v1 -k sk-xxx

# OpenRouter
uv run miniagent -m anthropic/claude-3-opus -u https://openrouter.ai/api/v1 -k sk-or-xxx
```