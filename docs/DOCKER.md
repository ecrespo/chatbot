# Docker and Docker Hub

Image: [`ecrespo/reflex-chatbot`](https://hub.docker.com/r/ecrespo/reflex-chatbot)
(`linux/amd64` and `linux/arm64`). Source: <https://github.com/ecrespo/chatbot>.

The image runs Reflex in production mode with frontend and backend on **a single
port** (`3000` by default). `docker build` installs the Python dependencies (uv,
from `uv.lock`), bun and the frontend packages, and runs a first build. At start-up
Reflex recompiles in a few seconds, so `PORT` or `REFLEX_API_URL` can change
without rebuilding the image.

Files:

| File | Purpose |
| --- | --- |
| `Dockerfile` | Production image (non-root user, healthcheck on `/ping`) |
| `docker-entrypoint.sh` | Resolves the Ollama URL, then `reflex run --env prod --single-port --backend-port $PORT` |
| `.dockerignore` | Excludes `.env`, `.venv`, `.web`… (**secrets never go into the image**) |
| `docker-compose.yml` | The chatbot plus optional Ollama services, selected with **profiles** |
| `Makefile` | Shortcuts: `up`, `up-ollama`, `up-gpu`, `down`, `docker-build`, `docker-push`, `docker-buildx`… |
| `.github/workflows/release.yml` | Publishes to Docker Hub (and PyPI) when a `vX.Y.Z` tag is pushed |
| `.github/workflows/dockerhub-description.yml` | Syncs this page to the Docker Hub description when it changes on `main` |

---

## 1. Run the published image

```bash
docker run --rm -p 3000:3000 --env-file .env \
  --add-host host.docker.internal:host-gateway \
  ecrespo/reflex-chatbot:latest
```

Open <http://localhost:3000>. When `OLLAMA_BASE_URL` is empty or unset, the
container uses Ollama on the host (`http://host.docker.internal:11434/v1`).

With OpenRouter only, no special networking is needed:

```bash
docker run --rm -p 3000:3000 \
  -e LLM_PROVIDER=openrouter -e OPENROUTER_API_KEY=sk-or-v1-... \
  ecrespo/reflex-chatbot:latest
```

Tags: `latest` (last stable release), `X.Y.Z` and `X.Y`. Pre-releases
(`X.Y.ZrcN`) only get their own tag.

## 2. docker compose and profiles

A single `docker-compose.yml` covers every setup. The chatbot always runs; the
Ollama services only start when their profile is enabled:

| Command | Profile | Services |
| --- | --- | --- |
| `docker compose up -d` / `make up` | — | `chatbot` (LLM on the host or OpenRouter) |
| `docker compose --profile ollama up -d` / `make up-ollama` | `ollama` | `chatbot` + `ollama` (CPU) + `ollama-pull` |
| `docker compose --profile ollama-gpu up -d` / `make up-gpu` | `ollama-gpu` | `chatbot` + `ollama-gpu` (NVIDIA) + `ollama-pull` |

Use one Ollama profile at a time. Instead of `--profile` you can set
`COMPOSE_PROFILES=ollama` in `.env`, and then `docker compose up -d` is enough.

`docker compose up` uses the published image
`${DOCKERHUB_USER:-ecrespo}/reflex-chatbot:${IMAGE_TAG:-latest}`; add `--build`
to build it from your checkout instead.

Stop everything, whatever profile started it: `make down`
(`docker compose --profile '*' down`). Models are kept in the `ollama-models` volume.

### 2a. LLM on your machine (no profile)

```bash
cp .env.example .env        # set LLM_PROVIDER, models, keys
docker compose up -d
docker compose logs -f chatbot
```

`docker-compose.yml` loads `.env` and overrides the local server URLs, because
inside the container `localhost` is the container itself:

| Variable in `.env` | Default |
| --- | --- |
| `DOCKER_OLLAMA_BASE_URL` | empty = auto (`http://ollama:11434/v1` with an Ollama profile, `http://host.docker.internal:11434/v1` otherwise) |
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

### 2b. Ollama inside compose (profiles `ollama` / `ollama-gpu`)

```bash
# in .env: LLM_PROVIDER=ollama, OLLAMA_MODEL=llama3.2, OLLAMA_PULL_MODELS="llama3.2 qwen3:8b"
docker compose --profile ollama up -d        # CPU
docker compose --profile ollama-gpu up -d    # NVIDIA GPU (nvidia-container-toolkit)
```

- `ollama` / `ollama-gpu` store models in the `ollama-models` volume and publish `11434`
  **on 127.0.0.1 only**, since Ollama has no authentication (`OLLAMA_PORT` changes the
  port, `OLLAMA_BIND=0.0.0.0` exposes it to the network). Both answer to the DNS name `ollama`.
- `ollama-pull` waits until Ollama is healthy, pulls `OLLAMA_PULL_MODELS` and exits.
  After a new pull, press **Modelos** in the UI.
- The chatbot waits for Ollama's healthcheck and uses `http://ollama:11434/v1`
  automatically (keep `DOCKER_OLLAMA_BASE_URL` empty).
- **AMD ROCm**: profile `ollama` with `OLLAMA_IMAGE_TAG=rocm`, and add
  `devices: ["/dev/kfd", "/dev/dri"]` to the `ollama` service.

## 3. Ports, domain and reverse proxy

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

## 4. Updating a running deployment

```bash
docker compose pull                 # new chatbot (and Ollama) images
docker compose up -d                # recreates only what changed
docker image prune -f               # optional: drop the old layers
```

Pin a version with `IMAGE_TAG=0.2.0` in `.env` and change it when you want to upgrade.
With an Ollama profile, pass the same `--profile` (or keep `COMPOSE_PROFILES` in `.env`).

## 5. Publishing to Docker Hub

Releases are published automatically by `.github/workflows/release.yml` when a
`vX.Y.Z` tag is pushed, together with the PyPI package — see
**[RELEASING.md](RELEASING.md)**. The workflow logs in with the `DOCKERHUB_TOKEN`
secret (a personal access token with *Read, Write & Delete* scope), pushes the
`X.Y.Z`, `X.Y` and `latest` tags and updates the repository description from this
file. Edits to this page merged into `main` are synced to Docker Hub by
`.github/workflows/dockerhub-description.yml`.

Manual publishing (e.g. from a fork):

```bash
docker login -u <your_user>                          # Personal access token as password

make docker-push DOCKERHUB_USER=<your_user>          # local arch, :latest and :<version>

docker buildx create --use --name multi 2>/dev/null || docker buildx use multi
make docker-buildx DOCKERHUB_USER=<your_user>        # amd64 + arm64
```

On an amd64 machine the arm64 half runs under QEMU and the frontend prerender may
time out; the release workflow avoids this by building each architecture on a
native runner and joining them with `docker buildx imagetools create`.

With compose: `DOCKERHUB_USER=<your_user> IMAGE_TAG=0.1.1 docker compose build && docker compose push chatbot`.

## 6. Diagnostics

```bash
docker compose ps                                   # status + healthcheck
docker compose logs -f chatbot                      # first line shows the Ollama URL in use
docker compose exec chatbot curl -s http://127.0.0.1:3000/ping
# can the container see the LLM?
docker compose exec chatbot curl -s http://host.docker.internal:11434/v1/models
docker compose exec chatbot curl -s http://ollama:11434/v1/models    # with an Ollama profile
```

| Symptom | Fix |
| --- | --- |
| `connection refused` to `host.docker.internal` | The host server listens only on 127.0.0.1 (see the table in section 2a) |
| The chatbot ignores the compose Ollama | `DOCKER_OLLAMA_BASE_URL` (or `OLLAMA_BASE_URL` in the environment) is set: leave it empty |
| `container name "reflex-chatbot-ollama" is already in use` | Two Ollama profiles at once: use only `ollama` or `ollama-gpu` |
| `could not select device driver "nvidia"` | `ollama-gpu` needs `nvidia-container-toolkit`; use the `ollama` profile otherwise |
| The page loads but stays "connecting" | External port ≠ internal port, or a proxy without WebSocket → `REFLEX_API_URL` / `Upgrade` headers |
| The first start takes a while | Expected: the frontend is recompiled (a few seconds); the healthcheck allows 120 s |
| `ollama-pull` fails | Non-existent model name in `OLLAMA_PULL_MODELS` |
