#!/usr/bin/env python3
from pathlib import Path
from signal import SIGTERM, signal
from sys import stderr
from typing import Tuple

import httpx
import rich.table
import rich_click as click
from rich import print
from rich.prompt import Prompt

from .config import ConfigManager
from .errors import FxfError, MissingTokenError
from .project import ProjectManager


def sigterm_handler(_, __):
    raise SystemExit(1)


@click.group()
@click.option(
    "-p",
    "--profile",
    help=("Scope all operations to this profile"),
    default="default",
)
@click.pass_context
def main(ctx: click.Context, profile: str):
    """The local counterpart of Flux Capacitor that will help you manage
    projects on your local machine."""

    ctx.ensure_object(ConfigManager)
    ctx.obj.profile = profile


@main.group()
def auth():
    """Manage authentication and Flux Capacitor instances."""


def _get_token(cm: ConfigManager, instance_url: str) -> Tuple[dict, str]:
    is_valid = False
    next_message = "[cyan]What is your [bold]token[/bold]?[/cyan]"
    token = ""

    while not is_valid:
        token = Prompt.ask(next_message, password=True)
        next_message = "[red][bold]Invalid[/bold] token, please try again[/red]"

        with cm.get_api(instance_url, token) as api:
            try:
                user = api.me().get_current_user()

                if user["type"] == "authenticated":
                    is_valid = True
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 403:
                    raise FxfError(f"Unexpected error: {e}")
            except httpx.UnsupportedProtocol:
                raise FxfError(f"Invalid URL: {instance_url}")

    return user, token


@auth.command()
@click.option(
    "-u",
    "--instance-url",
    help="Base URL of the instance to login to.",
    required=True,
)
@click.pass_context
def login(ctx: click.Context, instance_url: str):
    """Login to a Flux Capacitor instance, based on the provided instance
    url."""

    cm: ConfigManager = ctx.obj

    user, token = _get_token(cm, instance_url)

    print(
        f"[green]Welcome [bold]{user['first_name']} {user['last_name']}[/bold][/green]"
    )
    cm.save_credentials(instance_url, token)


@auth.command()
@click.pass_context
def test(ctx: click.Context):
    """Tests all registered authentication tokens."""

    cm: ConfigManager = ctx.obj

    domains = cm.get_profile().get("domains", [])

    if not domains:
        print("[red]No domains found[/]")
        print("[cyan]Run [bold]fxf auth login[/bold] to login to an instance[/]")
        return

    table = rich.table.Table()

    table.add_column("Instance URL", style="cyan")
    table.add_column("Status")

    for domain in domains:
        try:
            with cm.get_api(domain) as api:
                user = api.me().get_current_user()

                if user["type"] == "authenticated":
                    status = "[green]OK[/]"
                else:
                    status = "[red]Not Authenticated[/]"
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                status = "[red]Invalid Token[/]"
            else:
                status = f"[red]HTTP {e.response.status_code}[/]"
        except MissingTokenError:
            status = "[red]No Token[/]"

        table.add_row(domain, status)

    console = rich.console.Console()
    console.print(table)


@main.group()
def project():
    """Manage projects and local code repositories."""


def _connect(ctx: click.Context, directory: Path):
    """Associates a Git repo to a connected instance."""

    cm: ConfigManager = ctx.obj

    if not cm.has_credentials():
        raise click.ClickException(
            "No credentials found, please use 'fxf auth login' first"
        )

    origin, _ = _find_project_origin(directory)

    print(f"[green]Found Git origin: [white]{origin}[/]")
    success = False

    for domain in cm.get_profile().get("domains", []):
        with cm.get_api(domain) as api:
            resolved = api.project().resolve(origin)

            if resolved["project"]:
                success = True
                print(
                    f"[green]Found project: [white]{resolved['project']['name']}[green] on [white]{domain}[/]"
                )
                cm.save_project(origin, domain, resolved["project"])
                print("[green]Connected![/green]")

    if not success:
        raise click.ClickException(
            "None of your Flux Capacitor instances have this project, please "
            "create it first"
        )


@project.command()
@click.option(
    "-d",
    "--directory",
    help="Directory where the project is.",
    type=click.Path(exists=True, dir_okay=True, file_okay=False, path_type=Path),
    default=Path("."),
)
@click.pass_context
def connect(ctx: click.Context, directory: Path):
    """Associates a Git repo to a connected instance."""

    return _connect(ctx, directory)


def _find_project_origin(directory):
    pm = ProjectManager(directory)

    if not pm.is_valid:
        raise click.ClickException("This directory is not a valid Git repository")

    origin = pm.get_origin()

    if not origin:
        raise click.ClickException("This repository has no origin")

    return origin, pm


@project.command()
@click.option(
    "-d",
    "--directory",
    help="Directory where the project is.",
    type=click.Path(exists=True, dir_okay=True, file_okay=False, path_type=Path),
    default=Path("."),
)
@click.pass_context
def gha(ctx: click.Context, directory: Path):
    """Generates the GitHub Action files for this project."""

    cm: ConfigManager = ctx.obj
    origin, pm = _find_project_origin(directory)
    proj = cm.get_project(origin)

    if not proj:
        print("[yellow]This project is not connected. Attempting to connect.[/yellow]")
        _connect(ctx, directory)

    proj = cm.get_project(origin)
    ff = pm.git_root / "Fluxfile"

    if not ff.exists():
        raise click.ClickException(
            "This project has no Fluxfile. Please write it before proceeding."
        )

    with cm.get_api(proj["domain"]) as api:
        try:
            resp = api.project().gha(proj["project"], ff.read_text())

            for file in resp["files"]:
                path = pm.git_root / file["name"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(file["content"])
                print(f"[green]Generated [white]{file['name']}[/]")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                errors = e.response.json().get("fluxfile")

                if not errors:
                    raise click.ClickException("Unknown error from API")

                table = rich.table.Table()

                table.add_column("Path", style="cyan")
                table.add_column("Error", style="white")

                for err in errors:
                    table.add_row(".".join(err["path"]), err["message"])

                print("[red]Invalid Fluxfile[/]")

                console = rich.console.Console()
                console.print(table)
            else:
                raise click.ClickException(f"API error: HTTP {e.response.status_code}")


def __main__():
    signal(SIGTERM, sigterm_handler)

    try:
        main()
    except KeyboardInterrupt:
        stderr.write("ok, bye\n")
        exit(1)
    except FxfError as e:
        stderr.write(f"Error: {e}\n")
        exit(1)


if __name__ == "__main__":
    __main__()
