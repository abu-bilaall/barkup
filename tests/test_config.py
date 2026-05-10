import pytest
from pathlib import Path

from config import (
    get_user_config_path,
    deep_merge,
)


class TestGetUserConfigPath:
    def test_returns_path_under_home(self):
        user_path = get_user_config_path()
        assert str(Path.home()) in str(user_path)

    def test_ends_with_config_toml(self):
        user_path = get_user_config_path()
        assert user_path.name == "config.toml"
        assert user_path.parent.name == "barkup"


class TestDeepMerge:
    def test_override_replaces_simple_values(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": 3}

    def test_merges_nested_dicts(self):
        base = {"general": {"name": "default", "dry_run": False}}
        override = {"general": {"dry_run": True}}
        result = deep_merge(base, override)
        assert result == {"general": {"name": "default", "dry_run": True}}

    def test_override_adds_new_keys(self):
        base = {"a": 1}
        override = {"b": 2}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": 2}

    def test_does_not_mutate_base(self):
        base = {"a": 1}
        override = {"a": 2}
        deep_merge(base, override)
        assert base == {"a": 1}

    def test_empty_override_returns_base_copy(self):
        base = {"a": 1}
        result = deep_merge(base, {})
        assert result == {"a": 1}

    def test_empty_base_returns_override(self):
        result = deep_merge({}, {"a": 1})
        assert result == {"a": 1}