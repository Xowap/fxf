import subprocess
from pathlib import Path
from typing import Optional


class ProjectManager:
    """Wrapper around Git to manage things related to a physical project"""

    def __init__(self, anchor: Path):
        self.anchor = anchor
        self.git_root = self.find_git_root()

    @property
    def is_valid(self) -> bool:
        return self.git_root is not None

    def _check_output(self, *args, **kwargs):
        return (
            subprocess.check_output(
                args,
                cwd=self.anchor,
                stderr=subprocess.DEVNULL,
                **kwargs,
            )
            .decode()
            .rstrip("\n")
        )

    def find_git_root(self) -> Optional[Path]:
        try:
            return Path(self._check_output("git", "rev-parse", "--show-toplevel"))
        except subprocess.CalledProcessError:
            return None

    def get_origin(self) -> Optional[str]:
        try:
            return self._check_output("git", "config", "--get", "remote.origin.url")
        except subprocess.CalledProcessError:
            return None
