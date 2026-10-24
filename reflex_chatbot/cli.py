"""`reflex-chatbot` command, for running the app installed from PyPI.

Reflex needs a working directory holding ``rxconfig.py`` (it also creates
``.web/`` and ``.states/`` there). The app code itself is imported from the
installed ``reflex_chatbot`` package, so ``init`` only copies ``rxconfig.py``,
``assets/`` and a ``.env`` template::

    reflex-chatbot init my-chat      # creates my-chat/{rxconfig.py,.env,assets/}
    cd my-chat && $EDITOR .env
    reflex-chatbot run               # production, one port → http://localhost:3000
    reflex-chatbot run --dev         # hot reload, frontend 3000 + backend 8000
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from . import __version__

_TEMPLATE = Path(__file__).resolve().parent / "_app"
# Running from a source checkout: the template files live in the project root.
_SOURCE_ROOT = Path(__file__).resolve().parent.parent

# destination in the app directory -> (installed path, source checkout path)
_FILES = {
    "rxconfig.py": (_TEMPLATE / "rxconfig.py", _SOURCE_ROOT / "rxconfig.py"),
    ".env": (_TEMPLATE / "env.example", _SOURCE_ROOT / ".env.example"),
    "assets/favicon.ico": (
        _TEMPLATE / "assets" / "favicon.ico",
        _SOURCE_ROOT / "assets" / "favicon.ico",
    ),
}


def init_app_dir(directory: Path, force: bool = False) -> list[Path]:
    """Copy the files Reflex needs into ``directory``; returns the ones written.

    Existing files are kept unless ``force`` is set (``.env`` is never
    overwritten, it holds your configuration and API keys).
    """
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, candidates in _FILES.items():
        target = directory / name
        if target.exists() and (not force or name == ".env"):
            continue
        source = next((p for p in candidates if p.is_file()), None)
        if source is None:
            raise FileNotFoundError(f"template for {name} not found in the installed package")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        written.append(target)
    return written


def _cmd_init(args: argparse.Namespace) -> int:
    directory = Path(args.directory).resolve()
    written = init_app_dir(directory, force=args.force)
    for path in written:
        print(f"created {path}")
    if not written:
        print(f"{directory} is already initialised")
    print(f"\nNext: edit {directory / '.env'} and run `reflex-chatbot run --dir {directory}`")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    directory = Path(args.dir).resolve()
    if not (directory / "rxconfig.py").is_file():
        for path in init_app_dir(directory):
            print(f"created {path}")

    env_file = directory / ".env"
    if env_file.is_file():
        os.environ.setdefault("CHATBOT_ENV_FILE", str(env_file))
    os.environ.setdefault("REFLEX_TELEMETRY_ENABLED", "false")

    port = str(args.port or os.environ.get("PORT") or 3000)
    command = [sys.executable, "-m", "reflex", "run", "--loglevel", args.loglevel]
    if args.dev:
        command += ["--frontend-port", port]
    else:
        command += ["--env", "prod", "--single-port", "--backend-port", port]

    os.chdir(directory)
    print(f"Reflex chatbot {__version__} · {directory} · http://localhost:{port}", flush=True)
    os.execv(sys.executable, command)
    return 0  # unreachable


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reflex-chatbot",
        description="Reflex chatbot for Ollama, LM Studio, llama.cpp, OpenRouter and OmniRoute.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="create an app directory (rxconfig.py, .env, assets/)")
    p_init.add_argument("directory", nargs="?", default=".", help="default: current directory")
    p_init.add_argument("--force", action="store_true", help="overwrite rxconfig.py and assets")
    p_init.set_defaults(func=_cmd_init)

    p_run = sub.add_parser("run", help="run the chatbot (initialises --dir if needed)")
    p_run.add_argument("--dir", default=".", help="app directory (default: current directory)")
    p_run.add_argument("--port", type=int, help="port (default: $PORT or 3000)")
    p_run.add_argument("--dev", action="store_true", help="development mode with hot reload")
    p_run.add_argument("--loglevel", default="info", help="Reflex log level (default: info)")
    p_run.set_defaults(func=_cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
