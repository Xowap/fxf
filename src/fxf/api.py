import httpx


def auto_raise(response: httpx.Response):
    """Hook for HTTPX to auto-raise for status"""

    response.read()
    response.raise_for_status()
    return response


class MeApi:
    """Wrapper around the self user API"""

    def __init__(self, client: httpx.Client):
        self.client = client

    def get_current_user(self) -> dict:
        """Retrieves information about the current user (either authenticated
        or not)."""

        return self.client.get("me/").json()


class ProjectApi:
    def __init__(self, client: httpx.Client):
        self.client = client

    def resolve(self, remote: str) -> dict:
        """Resolves a remote to a project"""

        return self.client.get("project/resolve/", params={"remote": remote}).json()

    def gha(self, project: dict, fluxfile: str) -> dict:
        """Generates the GHA files for a project"""

        return self.client.post(
            f"project/{project['id']}/gha/",
            json={
                "fluxfile": fluxfile,
            },
        ).json()


class ApiFactory:
    """Factory for API clients"""

    def __init__(self, base_url: str, token: str):
        self.token = token
        self.base_url = base_url
        self.client = None
        self._depth = 0

    def __enter__(self) -> "ApiFactory":
        """Creates the client"""

        if not self._depth:
            self.client = httpx.Client(
                base_url=httpx.URL(self.base_url).join("/back/api/"),
                headers={
                    "Authorization": f"Token {self.token}",
                },
                event_hooks=dict(
                    response=[auto_raise],
                ),
            )
            self.client.__enter__()

        self._depth += 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Releases the client"""

        if self._depth:
            self._depth -= 1

            if not self._depth:
                self.client.__exit__(exc_type, exc_val, exc_tb)

    def me(self) -> "MeApi":
        """Returns the "Me" namespace of the API"""

        return MeApi(self.client)

    def project(self) -> "ProjectApi":
        """Returns the "Project" namespace of the API"""

        return ProjectApi(self.client)
