"""Helpers to verify and install external tools on Windows."""

from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass


SVN_WINGET_ID = "Slik.Subversion"


@dataclass(slots=True)
class ToolStatus:
    """Status for external command availability."""

    command: str
    available: bool
    path: str | None
    version: str | None
    message: str


def get_command_status(command: str, version_args: list[str] | None = None) -> ToolStatus:
    """Return availability and version for one command."""
    executable = shutil.which(command)
    if executable is None:
        return ToolStatus(
            command=command,
            available=False,
            path=None,
            version=None,
            message=f"`{command}` no está en PATH.",
        )

    args = version_args or ["--version", "--quiet"]
    completed = subprocess.run(
        [command, *args],
        check=False,
        capture_output=True,
        text=True,
    )
    output = (completed.stdout or completed.stderr).strip()
    version = output.splitlines()[0] if output else None
    return ToolStatus(
        command=command,
        available=completed.returncode == 0,
        path=executable,
        version=version,
        message=f"`{command}` detectado en {executable}" if completed.returncode == 0 else output or "No se pudo obtener versión.",
    )


def install_svn_with_winget() -> ToolStatus:
    """Install SVN CLI on Windows using winget."""
    if platform.system().lower() != "windows":
        raise RuntimeError("Instalación automática de SVN implementada solo para Windows.")
    if shutil.which("winget") is None:
        raise RuntimeError("`winget` no está disponible en PATH.")

    completed = subprocess.run(
        [
            "winget",
            "install",
            "--id",
            SVN_WINGET_ID,
            "--exact",
            "--source",
            "winget",
            "--accept-source-agreements",
            "--accept-package-agreements",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip() or f"exit code {completed.returncode}"
        raise RuntimeError(f"No se pudo instalar SVN con winget: {detail}")
    status = get_command_status("svn")
    if status.available:
        return status
    return ToolStatus(
        command="svn",
        available=False,
        path=None,
        version=None,
        message="Instalación finalizada, pero `svn` todavía no aparece en PATH. Abrí nueva terminal o reiniciá sesión.",
    )
