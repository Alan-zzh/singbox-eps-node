import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "scripts" / "config.py"


def load_config_module(monkeypatch):
    monkeypatch.setenv("SERVER_IP", "127.0.0.1")
    monkeypatch.setenv("CF_DOMAIN", "example.com")
    spec = importlib.util.spec_from_file_location("project_config", CONFIG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_load_env_file_compat_inline_comments(monkeypatch, tmp_path):
    config = load_config_module(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AI_SOCKS5_PORT=               # SOCKS5端口\n"
        "CF_DOMAIN=jp.example.com   # 订阅域名\n"
        "REALITY_PUBLIC_KEY=abc123 # Reality公钥\n"
        "EMPTY=\n",
        encoding="utf-8",
    )

    values = config.load_env_file(env_file)

    assert values["AI_SOCKS5_PORT"] == ""
    assert values["CF_DOMAIN"] == "jp.example.com"
    assert values["REALITY_PUBLIC_KEY"] == "abc123"
    assert values["EMPTY"] == ""
