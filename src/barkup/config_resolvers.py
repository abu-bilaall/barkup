"""
Resolves raw config models into fully merged, provider-specific configs
ready for use by the backup pipeline.

Takes GeneralConfig and provider-specific config models (LocalConfig,
CloudProvider) and produces resolved dataclasses where fallback logic
has already been applied — local/provider values take precedence over
general, and exclude lists are merged and deduplicated.

Resolved types:
    ResolvedLocalConfig             -- local filesystem backup
    ResolvedCloudConfig             -- base class for cloud backups
    ResolvedGoogleDriveCloudConfig  -- Google Drive-specific config

Resolvers:
    resolve_local_config(general, local)      -> ResolvedLocalConfig
    resolve_cloud_config(general, provider)   -> ResolvedGoogleDriveCloudConfig
"""

from dataclasses import dataclass
from barkup.config_models import GeneralConfig, LocalConfig, CloudProvider


@dataclass
class ResolvedLocalConfig:
    """Fully resolved config for local backup."""

    # general fields
    profile_name: str
    dry_run: bool

    # native to local
    destination: str

    # resolved (from local or fallen back to general)
    sources: list[str]
    compression: bool
    exclude: list[str]


@dataclass
class ResolvedCloudConfig:
    """Fully resolved config for cloud backup"""

    # general fields
    profile_name: str
    dry_run: bool

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

    credentials_file: str | None
    remote_folder: str | None


def resolve_local_config(
    general: GeneralConfig, local: LocalConfig
) -> ResolvedLocalConfig:
    """Resolve effective local backup config using general as fallback."""
    return ResolvedLocalConfig(
        profile_name=general.profile_name,
        dry_run=general.dry_run,
        destination=local.destination if local.destination is not None else "",
        sources=local.sources if local.sources is not None else general.sources,
        compression=(
            local.compression if local.compression is not None else general.compression
        ),
        exclude=list(set(general.exclude + local.exclude)),  # Merge + deduplicate
    )


def resolve_cloud_config(
    general: GeneralConfig, provider: CloudProvider
) -> ResolvedGoogleDriveCloudConfig:
    """Resolve effective cloud backup config based on provider."""
    profile_name = general.profile_name
    dry_run = general.dry_run
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
                profile_name=profile_name,
                dry_run=dry_run,
                sources=resolved_sources,
                compression=resolved_compression,
                exclude=resolved_exclude,
                provider=provider.provider,
                enabled=provider.enabled,
                large_file_warning=provider.large_file_warning,
                credentials_file=provider.credentials_file,
                remote_folder=provider.remote_folder,
            )
