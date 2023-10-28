from contextlib import contextmanager
from pathlib import Path

import appdirs
import keyring
import keyring.backend
import tomlkit
import tomlkit.items
import os

from .api import ApiFactory
from .errors import MissingTokenError


class ConfigManager:
    """Manages reading and writing configuration"""

    def __init__(self):
        self.profile = "default"

    @property
    def config_path(self) -> Path:
        """Reference path for the configuration file"""

        if override := os.getenv("FXF_CONFIG_FILE"):
            return Path(override)

        return Path(appdirs.user_config_dir("fxf", "flux-capacitor")) / "config.toml"

    def get_config(self) -> tomlkit.TOMLDocument:
        """Reads the configuration file and returns a TOML document, even if
        the configuration file does not exist yet"""

        if self.config_path.exists():
            with self.config_path.open() as f:
                return tomlkit.parse(f.read())
        else:
            return tomlkit.document()

    def write_config(self, config: tomlkit.TOMLDocument):
        """Writes back the TOML document to the configuration file's
        location"""

        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        with self.config_path.open("w") as f:
            f.write(config.as_string())

    def get_api(self, base_url: str, token: str = "") -> ApiFactory:
        """Returns an API client for the given base URL and token. If no token
        is provided then we'll get it from the keyring."""

        if not token:
            token = self._get_token(base_url)

        if not token:
            raise MissingTokenError(
                f"No token found for {base_url} (profile: {self.profile})"
            )

        return ApiFactory(base_url, token)

    @contextmanager
    def edit_profile(self) -> tomlkit.TOMLDocument:
        """Helper context manager to allow modifying a profile by getting its
        document. When the context manager exits, the modified document will
        be written into the configuration."""

        config = self.get_config()

        if "profiles" not in config:
            config.add("profiles", tomlkit.table())

        if self.profile not in config["profiles"]:
            config["profiles"].add(self.profile, tomlkit.table())

        yield config["profiles"][self.profile]

        self.write_config(config)

    def get_profile(self) -> tomlkit.items.Table:
        """Finds a specific profile for reading purposes into the
        configuration. If the profile doesn't exist you'll get an empty TOML
        document."""

        config = self.get_config()

        if "profiles" not in config:
            return tomlkit.table()

        if self.profile not in config["profiles"]:
            return tomlkit.table()

        return config["profiles"][self.profile]

    def get_keyring(self) -> keyring.backend.KeyringBackend:
        """Wrapper to get the keyring. For now there is no configuration
        happening but in the future there might be, so we're creating a central
        call point here."""

        return keyring.get_keyring()

    def _save_token(self, base_url: str, token: str):
        """Saves a token into the keyring"""

        kr = self.get_keyring()
        kr.set_password("fxf", base_url, token)

    def _get_token(self, base_url: str) -> str:
        """Gets a token from the keyring"""

        kr = self.get_keyring()
        return kr.get_password("fxf", base_url)

    def save_credentials(self, base_url: str, token: str):
        """Saves a given token for a base URL into both configuration and
        keyring."""

        with self.edit_profile() as profile:
            domains = profile.get("domains", [])

            if base_url not in domains:
                domains.append(base_url)

            profile["domains"] = domains
            self._save_token(base_url, token)
