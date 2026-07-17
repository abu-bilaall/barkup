import pytest
from pydantic import ValidationError

import main


def _raise_validation_error():
    # Produce a genuine Pydantic ValidationError as config loading would.
    try:
        from config_models import GeneralConfig

        # `sources` is mandatory on GeneralConfig, so this fails validation.
        GeneralConfig(profile_name="broken", sources=[])
    except ValidationError as e:
        raise e


class TestMainEntryPoint:
    def test_catches_validation_error_and_exits_with_code_1(self, monkeypatch, capsys):
        monkeypatch.setattr(main, "run_barkup", _raise_validation_error)

        with pytest.raises(SystemExit) as exc:
            main.main()

        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "Configuration error" in out

    def test_runs_successfully_with_valid_config(self, monkeypatch, capsys):
        def ok():
            return None

        monkeypatch.setattr(main, "run_barkup", ok)

        # Should complete without raising.
        main.main()

        # No output, no error path taken.
        assert capsys.readouterr().out == ""
