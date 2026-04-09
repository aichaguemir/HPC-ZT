import httpx
from app.core.config import KEYCLOAK_URL, KEYCLOAK_REALM
from app.core.logging import logger
import os

KEYCLOAK_ADMIN_USER     = os.getenv("KEYCLOAK_ADMIN_USER", "admin")
KEYCLOAK_ADMIN_PASSWORD = os.getenv("KEYCLOAK_ADMIN_PASSWORD", "admin")


async def get_admin_token() -> str:
    """Get Keycloak master admin token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token",
            data={
                "client_id":  "admin-cli",
                "username":   KEYCLOAK_ADMIN_USER,
                "password":   KEYCLOAK_ADMIN_PASSWORD,
                "grant_type": "password",
            }
        )
        response.raise_for_status()
        return response.json()["access_token"]

async def create_keycloak_user(
    username:   str,
    email:      str,
    password:   str,
    first_name: str = "",
    last_name:  str = "",
    enabled:    bool = True
) -> str:
    token = await get_admin_token()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "username":      username,
                "email":         email,
                "enabled":       enabled,
                "emailVerified": True,
                "firstName":     first_name,
                "lastName":      last_name,
                "credentials":   [{"type": "password", "value": password, "temporary": False}],
            }
        )
        if response.status_code == 409:
            raise ValueError("Username or email already exists in Keycloak")
        response.raise_for_status()

        location    = response.headers.get("Location", "")
        keycloak_id = location.split("/")[-1]

        logger.info(f"Keycloak user created: {username} ({keycloak_id})")
        return keycloak_id

async def assign_keycloak_role(keycloak_id: str, role_name: str) -> None:
    """Assign a realm role to a Keycloak user."""
    token = await get_admin_token()

    async with httpx.AsyncClient() as client:
        # Get role details
        role_response = await client.get(
            f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/roles/{role_name}",
            headers={"Authorization": f"Bearer {token}"}
        )
        role_response.raise_for_status()
        role = role_response.json()

        # Assign role to user
        assign_response = await client.post(
            f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users/{keycloak_id}/role-mappings/realm",
            headers={"Authorization": f"Bearer {token}"},
            json=[{"id": role["id"], "name": role["name"]}]
        )
        assign_response.raise_for_status()
        logger.info(f"Role '{role_name}' assigned to {keycloak_id}")


async def remove_keycloak_role(keycloak_id: str, role_name: str) -> None:
    """Remove a realm role from a Keycloak user."""
    token = await get_admin_token()

    async with httpx.AsyncClient() as client:
        role_response = await client.get(
            f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/roles/{role_name}",
            headers={"Authorization": f"Bearer {token}"}
        )
        role_response.raise_for_status()
        role = role_response.json()

        delete_response = await client.delete(
            f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users/{keycloak_id}/role-mappings/realm",
            headers={"Authorization": f"Bearer {token}"},
            json=[{"id": role["id"], "name": role["name"]}]
        )
        delete_response.raise_for_status()
        logger.info(f"Role '{role_name}' removed from {keycloak_id}")


async def delete_keycloak_user(keycloak_id: str) -> None:
    """Delete a user from Keycloak."""
    token = await get_admin_token()

    async with httpx.AsyncClient() as client:
        response = await client.delete(
            f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users/{keycloak_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        response.raise_for_status()
        logger.info(f"Keycloak user deleted: {keycloak_id}")


async def disable_keycloak_user(keycloak_id: str) -> None:
    """Disable a user in Keycloak."""
    token = await get_admin_token()

    async with httpx.AsyncClient() as client:
        response = await client.put(
            f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users/{keycloak_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": False}
        )
        response.raise_for_status()
        logger.info(f"Keycloak user disabled: {keycloak_id}")
