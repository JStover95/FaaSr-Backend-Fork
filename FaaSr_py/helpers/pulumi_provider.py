import pulumi_esc_sdk as esc
from pulumi_esc_sdk.exceptions import NotFoundException
import time

import requests


def generate_temporary_access_token(access_token: str, expires_in: int = 1200) -> str:
    """
    Generate a temporary access token for the Pulumi environment.

    Args
    ----
    access_token: str - The access token to use for authentication.
    expires_in: int - The number of seconds from now until when the token will expire. Defaults to
        1200 seconds (20 minutes).

    Returns
    -------
    str - The temporary access token.
    """
    expires = int(time.time()) + expires_in
    response = requests.post(
        "https://api.pulumi.com/api/user/tokens",
        headers={
            "Accept": "application/vnd.pulumi+8",
            "Content-Type": "application/json",
            "Authorization": f"token {access_token}",
        },
        json={"description": "Temporary FaaSr access token", "expires": expires},
    )
    return response.json()["tokenValue"]


class PulumiProvider():
    """
    Pulumi provider for FaaSr.

    Args
    ----
    org_name: str - The name of the user's Pulumi organization for secret storage.

    Example usage:
    ```python
    # Set a new secret
    with PulumiProvider("my-org") as provider:
        provider.set_secret("my-secret", "my-value")

    # Previously set secrets can be retrieved later with get_secret
    with PulumiProvider("my-org") as provider:
        print(provider.get_secret("my-secret"))
    ```
    """

    project_name = "faasr"
    environment_name = "faasr"

    def __init__(self, org_name: str):
        self.org_name = org_name
        self.client: esc.EscClient = esc.esc_client.default_client()
        self.environment: esc.EnvironmentDefinition | None = None
        self._values: dict[str, str] | None = None
        self._has_new_values: bool = False

    def __enter__(self):
        """Initialize the Pulumi environment."""
        self.environment = self._get_or_create_environment()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Commit any new secrets to the Pulumi environment and clean up."""
        if self._has_new_values:
            self._commit_new_values()
        self.environment = None
        self._values = None
        self._has_new_values = False

    def _get_or_create_environment(self) -> esc.EnvironmentDefinition:
        """
        Try to get the Pulumi environment, and create it if it doesn't exist.

        Returns
        -------
        esc.EnvironmentDefinition - The Pulumi environment definition.
        """
        try:
            return self.client.get_environment(
                self.org_name,
                self.project_name,
                self.environment_name
            )
        except NotFoundException:
            return self._create_environment()

    def _create_environment(self):
        """Create a new Pulumi environment with an empty environment definition."""
        self.client.create_environment(
            self.org_name,
            self.project_name,
            self.environment_name,
        )
        env_def = esc.EnvironmentDefinition(imports=[], values=esc.EnvironmentDefinitionValues())
        self.client.update_environment(
            self.org_name,
            self.project_name,
            self.environment_name,
            env_def
        )

    def _get_values(self) -> dict[str, str]:
        """
        Get the Pulumi environment's secrets.

        Returns
        -------
        dict[str, str] - The Pulumi environment's secrets.
        """
        _, values, _ = self.client.open_and_read_environment(
            self.org_name,
            self.project_name,
            self.environment_name,
        )
        return values

    def _commit_new_values(self):
        """Commit any new secrets to the Pulumi environment."""
        # No-op if there are no new values ot commit
        if not self._has_new_values:
            return

        env_def = esc.EnvironmentDefinition(
            imports=[],
            values=esc.EnvironmentDefinitionValues(
                additional_properties=self._values
            ),
        )
        self.client.update_environment(
            self.org_name,
            self.project_name,
            self.environment_name,
            env_def,
        )

    def get_secret(self, key: str) -> str | None:
        """
        Get a secret from the Pulumi environment.

        Args
        ----
        key: str - The name of the secret to get.

        Returns
        -------
        str | None - The value of the secret, or None if the secret does not exist.
        """
        if self._values is None:
            self._values = self._get_values()
        return self._values.get(key)

    def set_secret(self, key: str, value: str):
        """
        Set a secret in the Pulumi environment.

        Args
        ----
        key: str - The name of the secret to set.
        value: str - The value of the secret to set.
        """
        self._has_new_values = True
        if self._values is None:
            self._values = self._get_values()
        self._values[key] = value

    def get_secrets(self, keys: list[str]) -> dict[str, str]:
        """
        Get multiple secrets from the Pulumi environment.

        Missing keys are omitted from the returned dict.

        Args
        ----
        keys: list[str] - The names of the secrets to get.

        Returns
        -------
        dict[str, str] - Mapping of keys that exist to their secret values.
        """
        if self._values is None:
            self._values = self._get_values()

        return {key: self._values[key] for key in keys if key in self._values}
