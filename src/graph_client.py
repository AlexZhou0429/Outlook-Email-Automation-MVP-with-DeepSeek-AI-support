from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import msal
import requests

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
SCOPES = [
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Mail.ReadWrite",
]
TOKEN_CACHE_PATH = Path(".msal_token_cache.json")


class GraphError(RuntimeError):
    pass


class GraphClient:
    def __init__(self, tenant_id: str, client_id: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.authority = f"https://login.microsoftonline.com/{tenant_id}"
        self.cache = msal.SerializableTokenCache()
        if TOKEN_CACHE_PATH.exists():
            self.cache.deserialize(TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
        self.app = msal.PublicClientApplication(
            client_id=client_id,
            authority=self.authority,
            token_cache=self.cache,
        )
        self._access_token: str | None = None

    def _persist_cache(self) -> None:
        if self.cache.has_state_changed:
            TOKEN_CACHE_PATH.write_text(self.cache.serialize(), encoding="utf-8")

    def get_access_token(self) -> str:
        if self._access_token:
            return self._access_token

        accounts = self.app.get_accounts()
        result = None
        if accounts:
            result = self.app.acquire_token_silent(SCOPES, account=accounts[0])

        if not result:
            flow = self.app.initiate_device_flow(scopes=SCOPES)
            if "user_code" not in flow:
                raise GraphError(f"Failed to create device flow: {flow}")
            print("\nMicrosoft login required:")
            print(flow["message"])
            result = self.app.acquire_token_by_device_flow(flow)

        self._persist_cache()

        if "access_token" not in result:
            raise GraphError(f"Could not acquire token: {json.dumps(result, indent=2)}")

        self._access_token = result["access_token"]
        return self._access_token

    def request(self, method: str, path_or_url: str, **kwargs: Any) -> Any:
        url = path_or_url if path_or_url.startswith("https://") else f"{GRAPH_ROOT}{path_or_url}"
        headers = kwargs.pop("headers", {}) or {}
        headers["Authorization"] = f"Bearer {self.get_access_token()}"
        headers.setdefault("Content-Type", "application/json")

        for attempt in range(4):
            response = requests.request(method, url, headers=headers, timeout=45, **kwargs)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "2"))
                time.sleep(retry_after)
                continue
            if response.status_code >= 400:
                raise GraphError(f"Graph API error {response.status_code}: {response.text}")
            if response.status_code == 204 or not response.text:
                return None
            return response.json()
        raise GraphError("Graph API throttled repeatedly; retry later.")

    def get_me(self) -> dict:
        return self.request("GET", "/me?$select=displayName,userPrincipalName,mail")

    def _list_child_folders(self, folder_id: str | None = None) -> list[dict]:
        path = "/me/mailFolders?$top=200" if folder_id is None else f"/me/mailFolders/{folder_id}/childFolders?$top=200"
        folders = []
        while path:
            data = self.request("GET", path)
            folders.extend(data.get("value", []))
            path = data.get("@odata.nextLink")
        return folders

    def find_folder_by_name(self, display_name: str) -> dict:
        target = display_name.strip().lower()
        queue: list[dict | None] = [None]
        while queue:
            current = queue.pop(0)
            children = self._list_child_folders(None if current is None else current["id"])
            for folder in children:
                if folder.get("displayName", "").strip().lower() == target:
                    return folder
                queue.append(folder)
        raise GraphError(f"Folder not found: {display_name}. Create it in Outlook first.")

    def list_messages_in_folder(self, folder_id: str, top: int = 5) -> list[dict]:
        select = ",".join([
            "id",
            "subject",
            "from",
            "toRecipients",
            "ccRecipients",
            "receivedDateTime",
            "bodyPreview",
            "body",
            "conversationId",
            "internetMessageId",
            "hasAttachments",
            "categories",
            "isRead",
        ])
        orderby = "receivedDateTime desc"
        path = f"/me/mailFolders/{folder_id}/messages?$top={top}&$select={select}&$orderby={orderby}"
        data = self.request("GET", path)
        return data.get("value", [])

    def create_reply_draft(self, message_id: str, comment_html: str) -> dict:
        # Microsoft Graph creates a draft reply to preserve the original conversation thread.
        payload = {"comment": comment_html}
        return self.request("POST", f"/me/messages/{message_id}/createReply", json=payload)

    def update_message_categories(self, message_id: str, categories: list[str]) -> dict | None:
        payload = {"categories": categories}
        return self.request("PATCH", f"/me/messages/{message_id}", json=payload)

    def mark_read(self, message_id: str) -> dict | None:
        return self.request("PATCH", f"/me/messages/{message_id}", json={"isRead": True})
