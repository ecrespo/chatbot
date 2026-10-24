# Releasing and maintenance

Every release publishes the same version to two places:

| Where | What | Name |
| --- | --- | --- |
| [PyPI](https://pypi.org/project/reflex-chatbot/) | sdist + wheel with the `reflex-chatbot` command | `reflex-chatbot` |
| [Docker Hub](https://hub.docker.com/r/ecrespo/reflex-chatbot) | image for `linux/amd64` and `linux/arm64` | `ecrespo/reflex-chatbot:X.Y.Z`, `:X.Y`, `:latest` |

plus a GitHub release with the distribution files and generated notes.

## Workflows

| Workflow | Runs on | Does |
| --- | --- | --- |
| `quality.yml` | push / PR to `main`, `develop` | ruff, `uv lock --check`, pytest, builds the wheel and compiles the app from it, validates every compose profile, builds the image and checks `/ping` |
| `security.yml` | push / PR, weekly | gitleaks, bandit, pip-audit, hadolint, CodeQL, dependency review (PRs) |
| `release.yml` | tag `vX.Y.Z` | quality + security → build → **PyPI** and **Docker Hub** in parallel → GitHub release |
| Dependabot | weekly | PRs to `develop` for `uv.lock`, the Docker base images, compose images and GitHub Actions |

`release.yml` refuses to publish when the tag is not on `main` or when the tag,
`pyproject.toml` and `reflex_chatbot/__init__.py` disagree on the version.

## One-time setup

**PyPI — Trusted Publishing (no token stored).** At
<https://pypi.org/manage/account/publishing/> add a *pending publisher* (the first
release creates the project):

- PyPI project name: `reflex-chatbot`
- Owner / repository: `ecrespo` / `chatbot`
- Workflow: `release.yml`
- Environment: `pypi`

**Docker Hub.** Create a personal access token at
<https://app.docker.com/settings/personal-access-tokens> with *Read & Write*
scope (*Read, Write & Delete* also lets the workflow update the repository
description from `docs/DOCKER.md`).

**GitHub.** *Settings → Environments*: create `pypi` and `dockerhub` (optionally with
required reviewers or restricted to tags `v*`). In `dockerhub` add the secrets:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

To publish under another Docker Hub namespace, set the repository variable
`DOCKERHUB_NAMESPACE` (defaults to `ecrespo`).

## Cutting a release

Work happens on `develop`; releases are tagged on `main`.

```bash
# 1. on develop: bump the version (pyproject.toml, uv.lock, reflex_chatbot/__init__.py)
make bump VERSION=0.2.0
make check build                     # lint, tests, package
git commit -am "chore: release 0.2.0" && git push

# 2. merge develop into main (PR), then on main:
git switch main && git pull
make release                         # tags v0.2.0 and pushes the tag
```

Follow the run in *Actions → Release*. Pre-releases work the same way
(`make bump VERSION=0.2.0rc1`): they are marked as pre-release on GitHub, are
published to PyPI as pre-releases and do not move the `latest`/`X.Y` Docker tags.

If a release fails after PyPI accepted the files, do not reuse the version
(PyPI never allows it): fix, bump to the next patch and tag again.

## Updating dependencies

Dependabot opens weekly PRs against `develop`; CI must be green before merging.
To update everything by hand:

```bash
make update          # uv lock --upgrade, uv sync, lint + tests
docker compose build # check the image still builds
```

- Python requirement ranges live in `pyproject.toml`; exact versions in `uv.lock`
  (the Docker image installs from it with `uv sync --locked`).
- Frontend packages are pinned by Reflex in `reflex.lock/`; it is refreshed when
  Reflex or `reflex-assistant-ui` change. Commit it together with `uv.lock`.
- Base images: `PYTHON_VERSION` / `UV_VERSION` build args in the `Dockerfile`, and
  `OLLAMA_IMAGE_TAG` for compose.

After merging dependency updates, release a patch version so PyPI and Docker Hub
get them too.

## Manual publishing (fallback)

```bash
make build                                   # dist/*.whl and dist/*.tar.gz
uv publish                                   # PyPI token in UV_PUBLISH_TOKEN
make docker-buildx DOCKERHUB_USER=ecrespo    # after docker login
```
