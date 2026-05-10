"""
models for validating config file of barkup.

supports section customization for 'source', 'compression'
and 'exclude'fields.
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Literal


class GeneralConfig(BaseModel):
    """
    General settings and global defaults.
    'sources', 'compression', and 'exclude' defined here
    serve as fallbacks for [local] and [[cloud_providers]]
    if they don't define their own.
    """

    # fields specific to this section
    profile_name: str
    dry_run: bool = False

    # These are mandatory at the general level.
    # local and cloud_providers sections inherit these
    # if they don't define their own.
    sources: list[str]
    compression: bool = False
    exclude: list[str] = Field(default_factory=list)

    @field_validator("sources")
    @classmethod
    def sources_not_empty(cls, v):
        if not v:
            raise ValueError("At least one source path is required in [general]")
        return v


class LocalConfig(BaseModel):
    """
    Local backup settings.
    'sources', 'compression', and 'exclude' are optional
    and fallback to [general] values, if not defined.
    'exclude' merges with [general] 'exclude' list.
    """

    # field specific to this section
    destination: str | None

    # optional fields, fall back to general defaults if not defined
    sources: list[str] | None = Field(default=None)
    compression: bool | None = Field(default=None)
    exclude: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def destination_required_when_sources_defined(self):
        """Only require destination when sources are explicitly defined under [local]."""
        if self.sources is not None:
            if not self.destination or not self.destination.strip():
                raise ValueError(
                    "Local destination path cannot be empty when sources are defined under [local]."
                )
        return self


class CloudProvider(BaseModel):
    """
    Cloud backup settings.
    'sources', 'compression', and 'exclude' are optional
    and fallback to [general] values, if not defined.
    'exclude' merges with [general] 'exclude' list.
    """

    # fields specific to this section
    provider: Literal["google_drive"]
    enabled: bool = False
    large_file_warning: int = 100  # MB threhold

    # optional fields, fall back to general defaults if not defined
    sources: list[str] | None = Field(default=None)
    compression: bool | None = Field(default=None)
    exclude: list[str] = Field(default_factory=list)

    # Google Drive specific fields
    credentials_file: str | None = Field(default=None)
    remote_folder: str | None = Field(default=None)

    @model_validator(mode="after")
    def validate_provider_credentials(self):
        """Only validate credentials if the provider is enabled."""
        if not self.enabled:
            return self

        if self.provider == "google_drive":
            missing = [
                field
                for field, val in [
                    ("credentials_file", self.credentials_file),
                    ("remote_folder", self.remote_folder),
                ]
                if not val
            ]

            if missing:
                raise ValueError(
                    f"Google Drive requires these fields when enabled: {', '.join(missing)}"
                )

        return self


class AdvancedConfig(BaseModel):
    """Advanced / optional settings."""

    temp_dir: str = "/tmp/barkup"


class BarkupConfig(BaseModel):
    """
    Root config model. Represents the entire config file.
    All other models are nested under this one.
    """

    general: GeneralConfig
    local: LocalConfig
    cloud_providers: list[CloudProvider] = Field(default_factory=list)
    advanced: AdvancedConfig = Field(default_factory=AdvancedConfig)