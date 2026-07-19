"""
CLI entry point for barkup.

Defines the command group and the shared profile-resolution
helper that all subcommands reuse.
"""

import sys
from pathlib import Path

import click

from barkup import run_barkup
from config import get_user_config_path, init_config, load_config


def resolve_profile_name(cli_name: str | None, config) -> str:
    """Resolve which profile to use based on three-tier precedence.

    1. CLI --name flag (highest priority)
    2. Config [general] profile_name field
    3. Hardcoded "default" fallback
    """
    if cli_name:
        return cli_name
    if hasattr(config, "general") and hasattr(config.general, "profile_name"):
        return config.general.profile_name
    return "default"


@click.group()
@click.option("--config", type=click.Path(exists=True), help="Custom config file path")
@click.pass_context
def cli(ctx, config):
    """Barkup - CLI backup tool for local and cloud storage."""
    # Store config path in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = Path(config) if config else None


@cli.command()
@click.option(
    "--force", is_flag=True, help="Overwrite an existing config without prompting"
)
def init(force):
    """Create default config file."""
    config_path = get_user_config_path()

    if config_path.exists():
        if not force and not click.confirm(
            f"Config already exists at '{config_path}'. Overwrite?"
        ):
            click.echo("Aborted. Existing config was left unchanged.")
            return
        force = True

    init_config(force=force)

    click.echo(f"Config created at '{config_path}'.")
    click.echo(f"See '{config_path.parent / 'config.example.toml'}' for all options.")


@cli.command()
@click.option("--name", help="Backup profile name")
@click.option("--yes", is_flag=True, help="Skip confirmation prompts")
@click.pass_context
def run(ctx, name, yes):
    """Run backup using config."""
    config_path = ctx.obj.get("config_path")

    try:
        config = load_config(config_path)

        # Resolve profile name using three-tier fallback.
        profile = resolve_profile_name(name, config)

        click.echo(f"Running backup for profile: {profile}")
        stats = run_barkup(
            cli_path=config_path,
            profile_name=profile,
            skip_confirm=yes,
        )

        click.echo("\n✓ Backup completed successfully")
        click.echo(f"  New files: {stats['new_files']}")
        click.echo(f"  Modified files: {stats['modified_files']}")
        click.echo(f"  Skipped (unchanged): {stats['skipped_files']}")
        sys.exit(0)

    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nBackup cancelled by user")
        sys.exit(2)


@cli.command("list")  # Renamed to avoid Python keyword
@click.option("--name", help="Filter by profile name")
def list_cmd(name):
    """List all backed up files."""
    from database import open_connection, close_connection, list_backups

    conn = open_connection()
    try:
        rows = list_backups(conn, name)
    finally:
        close_connection(conn)

    if not rows:
        click.echo("No backups found.")
        return

    for row in rows:
        click.echo(f"{row['original_path']} -> {row['backup_path']}")
        click.echo(f"  {row['size']} bytes, backed up {row['last_backup']}")


@cli.command()
@click.option("--name", help="Show stats for specific profile")
def status(name):
    """Show backup statistics."""
    from database import (
        open_connection,
        close_connection,
        get_backup_stats,
        format_size,
    )

    conn = open_connection()
    try:
        stats = get_backup_stats(conn, name)
    finally:
        close_connection(conn)

    if not stats:
        click.echo("No backups found.")
        return

    for profile, s in stats.items():
        click.echo(f"Profile: {profile}")
        click.echo(f"  Files: {s['file_count']}")
        click.echo(f"  Total size: {format_size(s['total_size'])}")
        click.echo(f"  Last backup: {s['last_backup']}")


@cli.command()
@click.option("--name", help="Verify specific profile")
def verify(name):
    from database import (
        open_connection,
        close_connection,
        get_all_backups,
        verify_backup,
    )

    conn = open_connection()
    try:
        entries = get_all_backups(conn, name)
    finally:
        close_connection(conn)

    if not entries:
        click.echo("No backups found.")
        sys.exit(0)

    # Aggregate results per profile
    summary: dict[str, dict[str, int]] = {}
    for e in entries:
        profile = e["profile"]
        status = verify_backup(e)
        if profile not in summary:
            summary[profile] = {"ok": 0, "missing": 0, "mismatch": 0}
        summary[profile][status] += 1

    for profile, counts in summary.items():
        click.echo(f"Profile: {profile}")
        click.echo(f"  OK: {counts['ok']}")
        click.echo(f"  Missing: {counts['missing']}")
        click.echo(f"  Mismatched: {counts['mismatch']}")

    # Exit non-zero if any problem detected
    any_issues = any(
        v for prof in summary.values() for k, v in prof.items() if k != "ok" and v > 0
    )
    sys.exit(1 if any_issues else 0)


@cli.command()
@click.argument("path", required=False)
@click.option("--to", "destination", help="Restore to custom location")
@click.option("--all", "restore_all", is_flag=True, help="Restore entire backup set")
@click.option("--name", help="Profile name")
def restore(path, destination, restore_all, name):
    """Restore files from backup."""
    from restore import restore_all_files, restore_file

    if restore_all:
        if not name:
            click.echo("Error: --name required with --all", err=True)
            sys.exit(1)
        try:
            results = restore_all_files(name, destination)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        click.echo(f"✓ Restored {results['restored']} files from profile '{name}'")
        if destination:
            click.echo(f"  → {destination}")
        if results["failed"]:
            click.echo(f"\n⚠ Failed to restore {len(results['failed'])} files:")
            for item in results["failed"]:
                click.echo(f"  - {item['path']}: {item['error']}")
            sys.exit(1)
        sys.exit(0)

    if not path:
        click.echo("Error: PATH argument required (or use --all)", err=True)
        sys.exit(1)

    try:
        restored_path = restore_file(path, destination, name)
        click.echo(f"✓ Restored {path}")
        click.echo(f"  → {restored_path}")
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
