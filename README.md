# shared-services

> Shared infrastructure layer for homelab AI projects — GPU-accelerated local LLM and Telegram command dispatcher, shared across multiple applications via Docker network.

---

## What it does

`shared-services` is the backbone of a self-hosted AI stack. Instead of each application running its own LLM instance (expensive in VRAM and memory), this project provides a single shared Ollama instance running on an RTX 3080 — accessible to all applications on the `shared_net` Docker network.

It also runs a Telegram bot dispatcher that routes commands to the appropriate backend agents.

---

## Architecture

```
shared_net (Docker bridge network)
      │
      ├──► shared-ollama (Ollama 0.23.0)
      │       ├── RTX 3080 — GPU inference, 33/33 layers
      │       ├── llama3:latest (8B, 4.7 GB)
      │       └── nomic-embed-text (274 MB — RAG embeddings)
      │
      └──► telegram-dispatcher
              ├── /ask  → queries shared-ollama
              └── routes commands to connected agents
```

### Connected Services

| Service | How it connects |
|---------|----------------|
| `eletrica-pro` | `OLLAMA_HOST=http://shared-ollama:11434` via `shared_net` |
| `agente-ligacao` | joins `shared_net` for dispatcher communication |
| `open-webui` | uses `shared-ollama` as its LLM backend |

---

## Key Design Decisions

**Single GPU, multiple consumers:** Rather than duplicating model weights across containers, all LLM workloads share one Ollama instance. `OLLAMA_KEEP_ALIVE=-1` keeps the model loaded in VRAM at all times.

**External Docker network:** `shared_net` is declared as `external: true` — other projects join it in their own `docker-compose.yml` without coupling to this repo.

**Dispatcher pattern:** The Telegram bot acts as a hub — it doesn't implement business logic itself, it routes commands to whichever agent owns that responsibility.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| LLM runtime | Ollama 0.23.0 |
| GPU | NVIDIA RTX 3080 (NVIDIA Container Toolkit) |
| Models | llama3:latest, nomic-embed-text |
| Bot framework | python-telegram-bot |
| Infra | Docker Compose + `shared_net` external network |

---

## Project Structure

```
dispatcher/
├── main.py          # Telegram bot entrypoint + command registration
├── handlers.py      # Command handlers (/ask, /help, ...)
└── requirements.txt
docker-compose.yml   # shared-ollama + telegram-dispatcher
.env.example         # Required environment variables
```

---

## Setup

```bash
# Create the shared network first (one-time)
docker network create shared_net

cp .env.example .env
# Fill in your Telegram credentials

docker compose up -d
```

**Environment variables:**

```env
TELEGRAM_BOT_TOKEN=your-telegram-bot-token-here
TELEGRAM_CHAT_ID=your-telegram-chat-id-here
```

**GPU requirement:** NVIDIA GPU with [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) installed.

To run without GPU, remove the `deploy.resources` block from `docker-compose.yml` and switch to a CPU-compatible Ollama model.

---

## Adding a new consumer

Any Docker Compose project can consume `shared-ollama` by joining `shared_net`:

```yaml
# In your project's docker-compose.yml
services:
  my-service:
    environment:
      OLLAMA_HOST: http://shared-ollama:11434
    networks:
      - shared_net

networks:
  shared_net:
    external: true
```

---

## Status

Running 24/7 on a self-hosted Debian 12 server. RTX 3080 dedicated to LLM inference (separate GTX 660 handles display output).

---

## Author

Luis Rocha · [github.com/rochaOps](https://github.com/rochaOps)
