# LLM provider guide

The chatbot talks to every provider through the **OpenAI-compatible API**
(`POST /v1/chat/completions` and `GET /v1/models`). For each one you only need to
(1) have the server running, (2) fill in its block in `.env` and (3) select it with
`LLM_PROVIDER` or from the picker in the UI.

Common variables per prefix (`OLLAMA_`, `LMSTUDIO_`, `LLAMACPP_`, `OPENROUTER_`,
`OMNIROUTE_`, `CUSTOM_`): `_BASE_URL`, `_API_KEY`, `_MODEL`, `_MODELS`,
`_HEADERS`, `_EXTRA_BODY`, `_LABEL` (see the README).

Quick check of any provider from a terminal:

```bash
curl -s $BASE_URL/models -H "Authorization: Bearer $API_KEY" | head
```

- [Ollama](#ollama)
- [LM Studio](#lm-studio)
- [llama.cpp](#llamacpp-llama-server)
- [OpenRouter](#openrouter)
- [OmniRoute](#omniroute)
- [Other servers (custom)](#other-openai-compatible-servers-custom)
- [Tools and reasoning per provider](#tools-and-reasoning)

---

## Ollama

A local model server. It exposes its native API plus an OpenAI-compatible one
under `/v1`, which is what the chatbot uses.

```bash
# install: https://ollama.com/download
ollama pull llama3.2          # small model with tool support
ollama pull qwen3:8b          # "thinking" model with tools
ollama serve                  # unless it already runs as a service
curl http://localhost:11434/v1/models
```

`.env`:

```dotenv
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_API_KEY=ollama          # required by the SDK, ignored by Ollama
OLLAMA_MODEL=llama3.2
```

Notes:

- Model names carry a tag (`llama3.2:latest`, `qwen3:8b`); `OLLAMA_MODEL=llama3.2`
  matches `llama3.2:latest`.
- **Context window**: the `/v1` API cannot set `num_ctx`. Start the server with
  `OLLAMA_CONTEXT_LENGTH=8192 ollama serve` or create a model from a Modelfile
  (`PARAMETER num_ctx 8192`).
- **Reasoning**: thinking models (qwen3, deepseek-r1, gpt-oss…) return their reasoning,
  which is shown collapsed. `LLM_REASONING_EFFORT=low|medium|high|none` controls it.
- **Ollama on another machine**: `OLLAMA_BASE_URL=http://192.168.1.50:11434/v1`, and on that
  machine `OLLAMA_HOST=0.0.0.0:11434`.
- **Ollama in Docker next to the chatbot**: `docker-compose.ollama.yml` (see [DOCKER.md](DOCKER.md)).

---

## LM Studio

A desktop app with an OpenAI-compatible server on port 1234.

1. Download a model from the *Discover* tab.
2. *Developer* → **Start Server** (or from a terminal: `lms server start`).
3. Load the model (`lms load <model>`) or enable *Just-in-time model loading*
   so it loads on request.

```bash
curl http://localhost:1234/v1/models
```

`.env`:

```dotenv
LLM_PROVIDER=lmstudio
LMSTUDIO_BASE_URL=http://localhost:1234/v1
LMSTUDIO_API_KEY=lm-studio     # any value
LMSTUDIO_MODEL=                # empty = first model the server lists
```

Notes:

- The model id is the one LM Studio shows (e.g. `qwen/qwen3-8b`).
- Tools: supported by models with a tool-use template (Qwen, Llama 3.1+, Mistral…).
- Reasoning: LM Studio returns it in `reasoning_content` or as `<think>…</think>`; both are shown collapsed.
- To reach it from Docker or another machine, enable **Serve on Local Network** in the server settings.

---

## llama.cpp (`llama-server`)

The llama.cpp HTTP server serves a GGUF model through an OpenAI-compatible API.

```bash
# from Hugging Face (downloaded and cached)
llama-server -hf ggml-org/gemma-3-4b-it-GGUF --jinja --port 8080

# or a local file, reachable from the network/Docker, with a key
llama-server -m ./models/Qwen3-8B-Q4_K_M.gguf --jinja \
  --host 0.0.0.0 --port 8080 --ctx-size 8192 --api-key my-key

curl http://localhost:8080/v1/models
```

`.env`:

```dotenv
LLM_PROVIDER=llamacpp
LLAMACPP_BASE_URL=http://localhost:8080/v1
LLAMACPP_API_KEY=              # only if you started it with --api-key
LLAMACPP_MODEL=                # empty = the loaded model
```

Notes:

- **`--jinja` is required for tool calling.** Without it, switch off the *tools* toggle
  or set `LLM_ENABLE_TOOLS=false`.
- One process serves one model; for several, use `llama-swap` or several ports (via `CUSTOM_*`).
- Reasoning: with `--reasoning-format deepseek` (the default in recent builds) it arrives
  in `reasoning_content`; with `--reasoning-format none` it arrives as `<think>` in the text.
  Both are handled.

---

## OpenRouter

A cloud gateway to hundreds of models (OpenAI, Anthropic, Google, Meta, Mistral…).

1. Create an account and a key at <https://openrouter.ai/keys>.
2. Pick models at <https://openrouter.ai/models> (the id is `provider/model`).

`.env`:

```dotenv
LLM_PROVIDER=openrouter
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxx
OPENROUTER_MODEL=openai/gpt-4o-mini
# Short list for the picker (OpenRouter returns hundreds when left empty)
OPENROUTER_MODELS=openrouter/auto,openai/gpt-4o-mini,google/gemini-2.5-flash,meta-llama/llama-3.3-70b-instruct
# Optional attribution
OPENROUTER_HTTP_REFERER=https://my-site.com
OPENROUTER_APP_TITLE=Reflex Chatbot
```

Notes:

- Without `OPENROUTER_API_KEY` the provider shows up as "not configured".
- `openrouter/auto` lets OpenRouter choose the model.
- Free models: ids ending in `:free` (rate-limited).
- Reasoning: arrives in the `reasoning` field. To request it explicitly:
  `OPENROUTER_EXTRA_BODY={"reasoning": {"effort": "medium"}}`.
- Provider routing: `OPENROUTER_EXTRA_BODY={"provider": {"sort": "throughput"}}`.
- The key lives only on the server; it is never sent to the browser.

---

## OmniRoute

[OmniRoute](https://github.com/diegosouzapw/OmniRoute) is a local AI gateway with an
OpenAI-compatible endpoint that routes to many providers (free ones included), with
automatic fallback.

```bash
npx omniroute                                        # or: npm i -g omniroute && omniroute
# or with Docker
docker run -d -p 20128:20128 diegosouzapw/omniroute:latest

curl http://localhost:20128/v1/models
```

Dashboard: <http://localhost:20128/dashboard> (providers, quotas and client keys).

`.env`:

```dotenv
LLM_PROVIDER=omniroute
OMNIROUTE_BASE_URL=http://localhost:20128/v1
OMNIROUTE_API_KEY=             # if you created a client key in the dashboard
OMNIROUTE_MODEL=auto           # auto, auto/coding, auto/fast, auto/cheap or a specific model
```

Notes:

- `auto*` are virtual models: OmniRoute picks the real provider.
- If OmniRoute runs in Docker on the same compose network as the chatbot, use
  `DOCKER_OMNIROUTE_BASE_URL=http://<service-name>:20128/v1`.

---

## Other OpenAI-compatible servers (custom)

The `CUSTOM_*` block works with any OpenAI-compatible endpoint:
vLLM, SGLang, LocalAI, Jan, text-generation-webui, LiteLLM, the OpenAI API,
Groq, Together, Mistral, DeepSeek…

```dotenv
LLM_PROVIDER=custom
CUSTOM_LABEL=vLLM
CUSTOM_BASE_URL=http://gpu-server:8000/v1
CUSTOM_API_KEY=token-abc
CUSTOM_MODEL=Qwen/Qwen3-8B
```

Example base URLs:

| Server | `CUSTOM_BASE_URL` |
| --- | --- |
| vLLM (`vllm serve …`) | `http://localhost:8000/v1` |
| LiteLLM proxy | `http://localhost:4000/v1` |
| LocalAI | `http://localhost:8080/v1` |
| Jan | `http://localhost:1337/v1` |
| OpenAI | `https://api.openai.com/v1` |
| Groq | `https://api.groq.com/openai/v1` |
| DeepSeek | `https://api.deepseek.com/v1` |

If you need several of them at once under their own names, add entries to
`PROVIDER_PRESETS` in `chatbot/settings.py` (see README → *Extending*).

---

## Tools and reasoning

| Provider | Tool calling | Reasoning arrives as |
| --- | --- | --- |
| Ollama | Yes (models tagged *tools*: llama3.1+, qwen2.5+, qwen3, mistral…) | `reasoning` |
| LM Studio | Yes (models with a tool template) | `reasoning_content` or `<think>` |
| llama.cpp | Yes, with `--jinja` | `reasoning_content` or `<think>` |
| OpenRouter | Depends on the model (*tools* filter on their site) | `reasoning` |
| OmniRoute | Depends on the upstream provider | depends on the upstream provider |

Chatbot behaviour:

- If the server rejects a request because of the tools (HTTP 400 "does not support
  tools"…), it retries without them and remembers that for the provider + model until restart.
- The same applies to `reasoning_effort` when the server does not accept it.
- The *reasoning* toggle only hides the block; to make the model think less use
  `LLM_REASONING_EFFORT` or the provider's own `*_EXTRA_BODY`.
