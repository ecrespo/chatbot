# Docker and Docker Hub

The image runs Reflex in production mode with frontend and backend on **a single
port** (`3000` by default). `docker build` installs the Python dependencies (uv,
from `uv.lock`), bun and the frontend packages, and runs a first build. At start-up
Reflex recompiles in a few seconds, so `PORT` or `REFLEX_API_URL` can change
without rebuilding the image.

Files:

| File | Purpose |
| --- | --- |
| `Dockerfile` | Production image (non-root user, healthcheck on `/ping`) |
| `docker-entrypoint.sh` | `reflex run --env prod --single-port --backend-port $PORT` |
| `.dockerignore` | Excludes `.env`, `.venv`, `.web`… (**secrets never go into the image**) |
| `docker-compose.yml` | The chatbot, pointing at LLMs on the host or OpenRouter |
| `docker-compose.ollama.yml` | Override: adds Ollama and pulls the models |
| `Makefile` | Shortcuts: `docker-build`, `docker-push`, `docker-buildx`, `up`, `up-ollama`… |
| `.github/workflows/docker-publish.yml` | Automatic publishing to Docker Hub when a tag is pushed |

---

## 1. Build and run the image

```bash
docker build -t ecrespo/reflex-chatbot:latest .

docker run --rm -p 3000:3000 --env-file .env \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434/v1 \
  --add-host host.docker.internal:host-gateway \
  ecrespo/reflex-chatbot:latest
```

Open <http://localhost:3000>. With make: `make docker-build` and `make docker-run`.

With OpenRouter only, no special networking is needed:

```bash
docker run --rm -p 3000:3000 \
  -e LLM_PROVIDER=openrouter -e OPENROUTER_API_KEY=sk-or-v1-... \
  ecrespo/reflex-chatbot:latest
```

## 2. docker compose — LLM on your machine

```bash
cp .env.example .env        # set LLM_PROVIDER, models, keys
docker compose up -d --build
docker compose logs -f chatbot
```

`docker-compose.yml` loads `.env` and overrides the local server URLs, because
inside the container `localhost` is the container itself:

| Variable in `.env` | Default |
| --- | --- |
| `DOCKER_OLLAMA_BASE_URL` | `http://host.docker.internal:11434/v1` |
| `DOCKER_LMSTUDIO_BASE_URL` | `http://host.docker.internal:1234/v1` |
| `DOCKER_LLAMACPP_BASE_URL` | `http://host.docker.internal:8080/v1` |
| `DOCKER_OMNIROUTE_BASE_URL` | `http://host.docker.internal:20128/v1` |

`host.docker.internal` is mapped to the host with `extra_hosts: host-gateway` (Linux)
and exists out of the box in Docker Desktop (macOS/Windows).

**On Linux the host server must listen on all interfaces**, not only on 127.0.0.1:

| Server | How |
| --- | --- |
| Ollama (systemd) | `sudo systemctl edit ollama` → `[Service]` `Environment="OLLAMA_HOST=0.0.0.0:11434"` → `sudo systemctl restart ollama` |
| Ollama (manual) | `OLLAMA_HOST=0.0.0.0:11434 ollama serve` |
| LM Studio | Server settings → **Serve on Local Network** |
| llama.cpp | `llama-server … --host 0.0.0.0` |
| OmniRoute | configure its listen host, or run it on the same compose network |

Alternative on Linux: add `network_mode: host` to the `chatbot` service (and remove
`ports`); then `localhost` really is the host and the `DOCKER_*` variables are not needed.

## 3. docker compose — with Ollama included

```bash
# in .env: LLM_PROVIDER=ollama, OLLAMA_MODEL=llama3.2, OLLAMA_PULL_MODELS="llama3.2 qwen3:8b"
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up -d --build
# or: make up-ollama
```

- `ollama` stores models in the `ollama-models` volume and publishes `11434`.
- `ollama-pull` waits until Ollama is healthy, pulls `OLLAMA_PULL_MODELS` and exits.
  After a new pull, press **Modelos** in the UI.
- The chatbot uses `http://ollama:11434/v1` (the internal compose network).
- **NVIDIA GPU**: uncomment the `deploy` block in `docker-compose.ollama.yml`
  (requires `nvidia-container-toolkit`). **AMD ROCm**: `OLLAMA_IMAGE_TAG=rocm` and
  uncomment `devices` (`/dev/kfd`, `/dev/dri`).

Stop everything: `make down` (models are kept in the volume).

## 4. Ports, domain and reverse proxy

The browser connects to the backend over a WebSocket on the **same host and port**
as the page. Therefore:

- Change the port with `PORT` (same number inside and outside): `PORT=8080 docker compose up -d`.
- If you publish on a different external port (`-p 80:3000`) or behind a proxy/domain,
  set `REFLEX_API_URL` to the public URL, e.g. `REFLEX_API_URL=https://chat.mydomain.com`.
- The proxy must forward WebSockets on `/_event`. Caddy example:

```caddyfile
chat.mydomain.com {
    reverse_proxy localhost:3000
}
```

Nginx:

```nginx
location / {
    proxy_pass http://127.0.0.1:3000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 300s;
}
```

## 5. Publishing to Docker Hub

1. Create the `reflex-chatbot` repository at <https://hub.docker.com> (or let the first push create it).
2. Generate a *Personal access token* (Account settings → Personal access tokens).
3. Log in and publish:

```bash
docker login -u <your_user>

# local architecture, tags :latest and :<version from pyproject.toml>
make docker-push DOCKERHUB_USER=<your_user>

# multi-architecture (amd64 + arm64) with buildx
docker buildx create --use --name multi 2>/dev/null || docker buildx use multi
make docker-buildx DOCKERHUB_USER=<your_user>
```

Without make:

```bash
docker build -t <your_user>/reflex-chatbot:latest -t <your_user>/reflex-chatbot:0.1.0 .
docker push <your_user>/reflex-chatbot:latest
docker push <your_user>/reflex-chatbot:0.1.0
```

With compose (it uses `image:` = `${DOCKERHUB_USER}/reflex-chatbot:${IMAGE_TAG}`):

```bash
DOCKERHUB_USER=<your_user> IMAGE_TAG=0.1.0 docker compose build
DOCKERHUB_USER=<your_user> IMAGE_TAG=0.1.0 docker compose push
```

### Automatically with GitHub Actions

`.github/workflows/docker-publish.yml` builds amd64 + arm64 and publishes when a `v*`
tag is pushed (or manually from *Actions*). Configure in the repository
(*Settings → Secrets and variables → Actions*):

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

```bash
git tag v0.1.0 && git push origin v0.1.0
# → <user>/reflex-chatbot:0.1.0, :0.1 and :latest
```

### Using the published image

On any machine with Docker you only need `docker-compose.yml` (optionally
`docker-compose.ollama.yml`) plus a `.env`:

```bash
docker compose pull
docker compose up -d
```

## 6. Diagnostics

```bash
docker compose ps                                   # status + healthcheck
docker compose logs -f chatbot
docker compose exec chatbot curl -s http://127.0.0.1:3000/ping
# can the container see the LLM?
docker compose exec chatbot curl -s http://host.docker.internal:11434/v1/models
```

| Symptom | Fix |
| --- | --- |
| `connection refused` to `host.docker.internal` | The host server listens only on 127.0.0.1 (see the table in section 2) |
| The page loads but stays "connecting" | External port ≠ internal port, or a proxy without WebSocket → `REFLEX_API_URL` / `Upgrade` headers |
| The first start takes a while | Expected: the frontend is recompiled (a few seconds); the healthcheck allows 120 s |
| `ollama-pull` fails | Non-existent model name in `OLLAMA_PULL_MODELS` |
