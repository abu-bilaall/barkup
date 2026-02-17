"""
classes and functions for resolving configuration fields
of [local] and [[cloud_providers]] sections.
"""

from dataclasses import dataclass
from config_models import GeneralConfig, LocalConfig, CloudProvider


@dataclass
class ResolvedLocalConfig:
    """Fully resolved config for local backup."""

    # native to local
    destination: str

    # resolved (from local or fallen back to general)
    sources: list[str]
    compression: bool
    exclude: list[str]


@dataclass
class ResolvedCloudConfig:
    """Fully resolved config for cloud backup"""

    # fields native cloud
    provider: str
    enabled: bool
    large_file_warning: int

    # resolved (from cloud or fallen back to general)
    sources: list[str]
    compression: bool
    exclude: list[str]


@dataclass
class ResolvedGoogleDriveCloudConfig(ResolvedCloudConfig):
    """Fully resolved config for cloud backup w/ Google Drive."""

    credentials_file: str
    remote_folder: str


@dataclass
class ResolvedAmazonS3CloudConfig(ResolvedCloudConfig):
    """Fully resolved config for cloud backup w/ Amazon S3."""

    access_key: str
    secret_key: str
    bucket: str
    region: str


def resolve_local_config(
    general: GeneralConfig, local: LocalConfig
) -> ResolvedLocalConfig:
    """Resolve effective local backup config using general as fallback."""
    return ResolvedLocalConfig(
        destination=local.destination,
        sources=local.sources if local.sources is not None else general.sources,
        compression=(
            local.compression if local.compression is not None else general.compression
        ),
        exclude=list(set(general.exclude + local.exclude)),  # Merge + deduplicate
    )


def resolve_cloud_config(
    general: GeneralConfig, provider: CloudProvider
) -> ResolvedGoogleDriveCloudConfig | ResolvedAmazonS3CloudConfig:
    """Resolve effective cloud backup config based on provider."""
    resolved_sources = (
        provider.sources if provider.sources is not None else general.sources
    )
    resolved_compression = (
        provider.compression
        if provider.compression is not None
        else general.compression
    )
    resolved_exclude = list(
        set(general.exclude + provider.exclude)
    )  # merged and deduplicated

    if not provider.enabled:
        raise ValueError("Cloud backup is not enabled")

    match provider.provider:
        case "google_drive":
            return ResolvedGoogleDriveCloudConfig(
                sources=resolved_sources,
                compression=resolved_compression,
                exclude=resolved_exclude,
                provider=provider.provider,
                enabled=provider.enabled,
                large_file_warning=provider.large_file_warning,
                credentials_file=provider.credentials_file,
                remote_folder=provider.remote_folder,
            )
        case "amazon_s3":
            return ResolvedAmazonS3CloudConfig(
                sources=resolved_sources,
                compression=resolved_compression,
                exclude=resolved_exclude,
                provider=provider.provider,
                enabled=provider.enabled,
                large_file_warning=provider.large_file_warning,
                access_key=provider.access_key,
                secret_key=provider.secret_key,
                bucket=provider.bucket,
                region=provider.region,
            )
