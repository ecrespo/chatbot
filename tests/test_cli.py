from pathlib import Path

import pytest

from reflex_chatbot import __version__
from reflex_chatbot.cli import build_parser, init_app_dir


def test_init_creates_app_dir(tmp_path: Path):
    written = init_app_dir(tmp_path / "app")
    names = sorted(p.relative_to(tmp_path / "app").as_posix() for p in written)
    assert names == [".env", "assets/favicon.ico", "rxconfig.py"]
    assert 'app_name="reflex_chatbot"' in (tmp_path / "app" / "rxconfig.py").read_text()


def test_init_never_overwrites_env(tmp_path: Path):
    init_app_dir(tmp_path)
    (tmp_path / ".env").write_text("LLM_PROVIDER=openrouter\n")
    (tmp_path / "rxconfig.py").write_text("# edited\n")

    assert init_app_dir(tmp_path) == []
    written = init_app_dir(tmp_path, force=True)

    assert tmp_path / ".env" not in written
    assert (tmp_path / ".env").read_text() == "LLM_PROVIDER=openrouter\n"
    assert "# edited" not in (tmp_path / "rxconfig.py").read_text()


def test_version_flag(capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--version"])
    assert __version__ in capsys.readouterr().out
