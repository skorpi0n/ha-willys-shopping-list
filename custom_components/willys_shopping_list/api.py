"""Async client for the private Willys shopping list API."""

from __future__ import annotations

import base64
import secrets
from typing import Any
from urllib.parse import quote

import aiohttp
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from homeassistant.exceptions import HomeAssistantError

from .const import BASE_URL, CSRF_PATH, CUSTOMER_PATH, LISTS_PATH


class WillysApiError(HomeAssistantError):
    """Raised when Willys rejects or cannot complete an API request."""


class WillysAuthError(WillysApiError):
    """Raised when Willys rejects the account credentials."""


def _encrypt_credential(value: str) -> dict[str, str]:
    """Build the credential envelope used by the Willys web login."""
    iv = secrets.token_bytes(16)
    salt = secrets.token_bytes(16)
    key = f"{secrets.randbelow(100_000_000):08d}{secrets.randbelow(100_000_000):08d}"
    kdf = PBKDF2HMAC(algorithm=hashes.SHA1(), length=16, salt=salt, iterations=1000)
    aes_key = kdf.derive(key.encode())

    raw = value.encode("utf-8")
    padding = 16 - len(raw) % 16
    padded = raw + bytes([padding]) * padding
    encryptor = Cipher(algorithms.AES(aes_key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    envelope = f"{iv.hex()}::{salt.hex()}::{base64.b64encode(ciphertext).decode()}"
    return {"key": key, "str": base64.b64encode(envelope.encode()).decode()}


class WillysApi:
    """Use Home Assistant's shared aiohttp session for Willys requests."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._csrf_token: str | None = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        authenticated_write: bool = False,
        parse_json: bool = True,
    ) -> Any:
        headers = {"Accept": "application/json"}
        if authenticated_write:
            if not self._csrf_token:
                raise WillysApiError("Saknar CSRF-token; logga in igen.")
            headers.update(
                {"X-CSRF-TOKEN": self._csrf_token, "Content-Type": "application/json"}
            )
        try:
            async with self._session.request(
                method,
                f"{BASE_URL}{path}",
                params=params,
                json=json,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status >= 400:
                    raise WillysApiError(
                        f"Willys svarade med HTTP {response.status} för {method} {path}."
                    )
                body = await response.read()
                if not body or response.status == 204 or not parse_json:
                    return {"status": response.status}
                return await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise WillysApiError(f"Nätverksfel vid anrop till Willys: {err}") from err

    async def async_login(self, username: str, password: str) -> None:
        """Establish a Willys session and validate the credentials."""
        try:
            await self._request("GET", "/api/config", parse_json=False)
            self._csrf_token = await self._request("GET", CSRF_PATH)
            user = _encrypt_credential(username)
            secret = _encrypt_credential(password)
            await self._request(
                "POST",
                "/login",
                json={
                    "j_username": user["str"],
                    "j_username_key": user["key"],
                    "j_password": secret["str"],
                    "j_password_key": secret["key"],
                    "j_remember_me": True,
                },
                authenticated_write=True,
                parse_json=False,
            )
            self._csrf_token = await self._request("GET", CSRF_PATH)
            await self._request("GET", CUSTOMER_PATH)
        except WillysApiError as err:
            if "HTTP 400" in str(err) or "HTTP 401" in str(err):
                raise WillysAuthError(
                    "Inloggningen misslyckades. Kontrollera användarnamn och lösenord."
                ) from err
            raise

    async def async_get_lists(self) -> list[dict[str, Any]]:
        return await self._request("GET", LISTS_PATH, params={"sorting": "LAST_UPDATED_DESC"})

    async def async_get_list(self, list_id: str) -> dict[str, Any]:
        return await self._request("GET", f"{LISTS_PATH}/{quote(list_id, safe='')}")

    async def async_create_list(self, name: str) -> Any:
        return await self._request(
            "POST", LISTS_PATH, json={"name": name, "entries": []}, authenticated_write=True
        )

    async def async_delete_list(self, list_id: str) -> Any:
        return await self._request(
            "DELETE", f"{LISTS_PATH}/{quote(list_id, safe='')}", authenticated_write=True
        )

    async def async_add_product(
        self, list_id: str, product_code: str, quantity: int, pick_unit: str
    ) -> Any:
        return await self._request(
            "POST",
            f"{LISTS_PATH}/{quote(list_id, safe='')}/add",
            params={"increment": "true"},
            json={
                "entries": [
                    {
                        "entryType": "PRODUCT",
                        "productCode": product_code,
                        "pickUnit": pick_unit,
                        "quantity": quantity,
                    }
                ]
            },
            authenticated_write=True,
        )

    async def async_remove_product(self, list_id: str, product_code: str) -> Any:
        return await self._request(
            "DELETE",
            f"{LISTS_PATH}/{quote(list_id, safe='')}/product/{quote(product_code, safe='')}",
            authenticated_write=True,
        )

    async def async_change_quantity(self, list_id: str, product_code: str, delta: int) -> Any:
        """Adjust an item's count; positive values add, negative values reduce."""
        if delta == 0:
            raise WillysApiError("Ändringen måste vara minst +1 eller -1.")
        if delta > 0:
            return await self.async_add_product(list_id, product_code, delta, "pieces")

        wishlist = await self.async_get_list(list_id)
        entries = wishlist.get("entries", [])
        payload: list[dict[str, Any]] = []
        found = False
        for entry in entries:
            if entry.get("entryType") != "PRODUCT":
                raise WillysApiError(
                    "Listan innehåller en posttyp som mängdändringen ännu inte kan bevara."
                )
            product = entry.get("product") or {}
            code = entry.get("productCode") or product.get("code")
            if not code:
                raise WillysApiError("En listpost saknar produktkod; ingen ändring skickades.")
            row = {
                "entryType": "PRODUCT",
                "productCode": code,
                "pickUnit": entry.get("pickUnit", "pieces"),
                "quantity": entry.get("quantity", 1),
            }
            if code == product_code:
                if found:
                    raise WillysApiError("Produkten finns på flera rader; ändringen avbryts.")
                found = True
                row["quantity"] = max(0, row["quantity"] + delta)
                if row["quantity"] == 0:
                    continue
            payload.append(row)
        if not found:
            raise WillysApiError(f"Produkten {product_code} finns inte i listan.")
        return await self._request(
            "POST",
            f"{LISTS_PATH}/{quote(list_id, safe='')}",
            json={"entries": payload},
            authenticated_write=True,
        )
