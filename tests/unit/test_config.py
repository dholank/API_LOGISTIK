import os
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from api_logistik.config import Settings, load_settings
from api_logistik.errors import ConfigurationError


@pytest.fixture(autouse=True)
def isolated_settings_environment(monkeypatch):
    for name in tuple(os.environ):
        if name.lower() in Settings.model_fields:
            monkeypatch.delenv(name)
    monkeypatch.delenv("API_LOGISTIK_ENV_FILE", raising=False)


def test_synthetic_dotenv_password_is_literal_and_environment_has_priority(tmp_path, monkeypatch):
    file = tmp_path / "synthetic-settings.env"
    file.write_text(
        "ORACLE_DSN=tcps://synthetic.invalid:2484/test\n"
        "ORACLE_USER=synthetic_user\n"
        "ORACLE_PASSWORD='literal-${DO_NOT_EXPAND}-password'\n"
        "PORT=8123\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DO_NOT_EXPAND", "must-not-appear")
    monkeypatch.setenv("PORT", "8124")
    settings = load_settings(file)
    assert settings.oracle_password.get_secret_value() == "literal-${DO_NOT_EXPAND}-password"
    assert settings.port == 8124
    assert "literal-" not in repr(settings)
    assert "synthetic_user" not in repr(settings)
    assert "synthetic.invalid" not in repr(settings)


@pytest.mark.parametrize(
    "values",
    [
        {"oracle_password": "synthetic-private-password"},
        {"oracle_writer_password": "synthetic-private-password"},
        {"oracle_pool_min": 6, "oracle_pool_max": 5},
        {"oracle_mode": "thick"},
        {"environment": "production"},
        {"oracle_call_timeout_ms": 0},
        {"port": "synthetic-private-password"},
    ],
)
def test_invalid_partial_settings_raise_safe_validation_error(values):
    with pytest.raises(ValidationError) as caught:
        Settings(
            _env_file=None,
            environment=values.get("environment", "test"),
            **{k: v for k, v in values.items() if k != "environment"},
        )
    assert "synthetic-private-password" not in str(caught.value)


def test_load_settings_hides_invalid_file_values(tmp_path):
    file = tmp_path / "invalid-synthetic.env"
    file.write_text("ORACLE_PASSWORD=synthetic-private-password\n", encoding="utf-8")
    with pytest.raises(ConfigurationError) as caught:
        load_settings(file)
    assert "synthetic-private-password" not in str(caught.value)


def test_factory_and_openapi_do_not_read_dotenv_or_create_driver_pool(monkeypatch):
    import api_logistik.config as config
    import api_logistik.db.pool as pool_module
    from api_logistik.main import create_app

    dotenv = Mock(side_effect=AssertionError("No dotenv access permitted"))
    factory = Mock(side_effect=AssertionError("No driver pool permitted"))
    monkeypatch.setattr(config, "dotenv_values", dotenv)
    monkeypatch.setattr(pool_module.oracledb, "create_pool", factory)
    settings = Settings(_env_file=None, environment="test")
    app = create_app(settings)
    assert app.openapi()["paths"]["/api/v1/karyawan"]["post"]
    assert app.state.pool._pool is None
    dotenv.assert_not_called()
    factory.assert_not_called()


@pytest.mark.parametrize(
    "environment,enabled,expected",
    [("test", None, True), ("development", False, False), ("test", True, True)],
)
def test_docs_configuration(environment, enabled, expected):
    settings = Settings(_env_file=None, environment=environment, docs_enabled=enabled)
    assert settings.expose_docs is expected
