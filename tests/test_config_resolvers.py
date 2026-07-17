import pytest
from typing import Any

from config_models import GeneralConfig, LocalConfig, CloudProvider
from config_resolvers import (
    resolve_local_config,
    resolve_cloud_config,
    ResolvedLocalConfig,
    ResolvedGoogleDriveCloudConfig,
)


def _general(sources=None, exclude=None, compression=False, profile_name="default"):
    return GeneralConfig(
        profile_name=profile_name,
        sources=sources if sources is not None else ["/default/src"],
        compression=compression,
        exclude=exclude if exclude is not None else ["*.tmp"],
    )


class TestResolveLocalConfig:
    def test_uses_general_defaults_when_local_fields_none(self):
        general = _general(sources=["/gen"], exclude=["*.tmp"], compression=True)
        local = LocalConfig(destination="/backup")

        result = resolve_local_config(general, local)

        assert isinstance(result, ResolvedLocalConfig)
        assert result.sources == ["/gen"]
        assert result.compression is True
        assert result.exclude == ["*.tmp"]
        assert result.destination == "/backup"
        assert result.profile_name == "default"

    def test_overrides_with_local_values(self):
        general = _general(sources=["/gen"], exclude=["*.tmp"], compression=False)
        local = LocalConfig(
            destination="/backup",
            sources=["/local"],
            compression=True,
            exclude=["*.log"],
        )

        result = resolve_local_config(general, local)

        assert result.sources == ["/local"]
        assert result.compression is True
        # Exclude lists merge with general, not replace.
        assert set(result.exclude) == {"*.tmp", "*.log"}

    def test_merges_and_dedupes_exclude_lists(self):
        general = _general(exclude=["*.tmp", "*.log"])
        local = LocalConfig(destination="/backup", exclude=["*.log", "*.cache"])

        result = resolve_local_config(general, local)

        # Union, deduped.
        assert set(result.exclude) == {"*.tmp", "*.log", "*.cache"}

    def test_compression_flag_inheritance_from_general(self):
        general = _general(compression=True)
        local = LocalConfig(destination="/backup")

        result = resolve_local_config(general, local)

        assert result.compression is True

    def test_empty_destination_falls_back_to_empty_string(self):
        general = _general()
        local = LocalConfig(destination=None)

        result = resolve_local_config(general, local)

        assert result.destination == ""

    def test_passes_profile_name_through(self):
        general = _general(profile_name="work")
        local = LocalConfig(destination="/backup")

        result = resolve_local_config(general, local)

        assert result.profile_name == "work"


class TestResolveCloudConfig:
    def _provider(self, enabled: bool = True, **kwargs: Any) -> CloudProvider:
        return CloudProvider(
            provider="google_drive",
            enabled=enabled,
            credentials_file="/creds.json",
            remote_folder="backups",
            sources=kwargs.get("sources", ["/cloud/src"]),
            exclude=kwargs.get("exclude", ["*.tmp"]),
            compression=kwargs.get("compression", False),
        )

    def test_resolves_google_drive_provider(self):
        general = _general(sources=["/gen"], exclude=["*.tmp"], compression=False)
        provider = self._provider()

        result = resolve_cloud_config(general, provider)

        assert isinstance(result, ResolvedGoogleDriveCloudConfig)
        assert result.provider == "google_drive"
        assert result.enabled is True
        assert result.credentials_file == "/creds.json"
        assert result.remote_folder == "backups"

    def test_source_exclude_inheritance_from_general(self):
        general = _general(
            sources=["/gen"], exclude=["*.tmp", "*.log"], compression=True
        )
        provider = self._provider(sources=None, exclude=["*.log"], compression=None)

        result = resolve_cloud_config(general, provider)

        # sources fall back to general
        assert result.sources == ["/gen"]
        # compression falls back to general
        assert result.compression is True
        # exclude merged + deduped
        assert set(result.exclude) == {"*.tmp", "*.log"}

    def test_overrides_with_provider_values(self):
        general = _general(sources=["/gen"], exclude=["*.tmp"], compression=False)
        provider = self._provider(
            sources=["/prov"], compression=True, exclude=["*.log"]
        )

        result = resolve_cloud_config(general, provider)

        assert result.sources == ["/prov"]
        assert result.compression is True
        # Exclude lists merge with general, not replace.
        assert set(result.exclude) == {"*.tmp", "*.log"}

    def test_raises_when_provider_disabled(self):
        general = _general()
        provider = self._provider(enabled=False)

        with pytest.raises(ValueError, match="not enabled"):
            resolve_cloud_config(general, provider)

    def test_validates_provider_type_unknown_raises(self):
        # provider must be a Literal["google_drive"]; an invalid value is a
        # Pydantic validation error at construction.
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CloudProvider.model_validate(
                {
                    "provider": "dropbox",
                    "enabled": True,
                    "credentials_file": "/creds.json",
                    "remote_folder": "backups",
                }
            )
