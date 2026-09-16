import pytest
from pydantic import ValidationError

from tracefix.common.config import Settings, load_settings


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch):
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    monkeypatch.delenv("TRACEFIX_ENV_FILE", raising=False)


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


@pytest.mark.parametrize("name", ["db`;DROP DATABASE other;--", "a-b", "", "x" * 65])
def test_invalid_database_identifier_is_rejected(name):
    with pytest.raises(ValidationError):
        Settings(db_name=name, _env_file=None)
