import pytest
from pydantic import ValidationError

from tracefix.common.config import Settings, load_settings


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch):
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    monkeypatch.delenv("TRACEFIX_ENV_FILE", raising=False)
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    monkeypatch.delenv("langfuse_base_url", raising=False)


def test_env_file_and_environment_precedence(tmp_path, monkeypatch):
    path = tmp_path / "server.env"
    path.write_text("DB_USER=example\nDB_PASSWORD=secret@%:/\nDB_NAME=Example_DB\nDB_PORT=3307\n")
    monkeypatch.setenv("DB_PORT", "3308")
    settings = load_settings(path)
    assert settings.db_user == "example"
    assert settings.db_port == 3308
    assert settings.database_url().password == "secret@%:/"
    assert "secret@%:/" not in repr(settings)
    assert "secret@%:/" not in str(settings.database_url())


def test_empty_password_and_server_url(tmp_path):
    path = tmp_path / "server.env"
    path.write_text("DB_PASSWORD=\n")
    settings = load_settings(path)
    assert settings.database_url().password == ""
    assert settings.database_url(include_database=False).database is None


def test_alternate_env_file_is_explicitly_selected(tmp_path, monkeypatch):
    path = tmp_path / "alternate.env"
    path.write_text("DB_NAME=Alternate_DB\n")
    monkeypatch.setenv("TRACEFIX_ENV_FILE", str(path))
    assert load_settings().db_name == "Alternate_DB"


@pytest.mark.parametrize("key", ["LANGFUSE_BASE_URL", "LANGFUSE_HOST"])
def test_langfuse_url_aliases_and_source_precedence(tmp_path, monkeypatch, key):
    path = tmp_path / "server.env"
    path.write_text(f"{key}=https://cloud.langfuse.com\nLANGFUSE_ENABLED=true\n")
    assert load_settings(path).langfuse_enabled
    other = "LANGFUSE_HOST" if key == "LANGFUSE_BASE_URL" else "LANGFUSE_BASE_URL"
    monkeypatch.setenv(other, "https://us.cloud.langfuse.com/")
    assert load_settings(path).langfuse_host == "https://us.cloud.langfuse.com"


def test_conflicting_langfuse_urls_are_rejected(tmp_path):
    path = tmp_path / "server.env"
    path.write_text(
        "LANGFUSE_BASE_URL=https://us.cloud.langfuse.com\n"
        "LANGFUSE_HOST=https://cloud.langfuse.com\n"
    )
    with pytest.raises(ValueError, match="Conflicting LANGFUSE"):
        load_settings(path)


@pytest.mark.parametrize("name", ["db`;DROP DATABASE other;--", "a-b", "", "x" * 65])
def test_invalid_database_identifier_is_rejected(name):
    with pytest.raises(ValidationError):
        Settings(db_name=name, _env_file=None)
