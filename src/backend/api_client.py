# -*- coding: utf-8 -*-
"""src/backend/api_client.py

HTTP client used by the PyQt GUI to talk to Flask backend.
"""

from __future__ import annotations

from typing import Tuple, List, Dict, Any, Optional
import requests


class APIClient:
    def __init__(self, base_url: str = "http://127.0.0.1:5000", timeout: int = 15):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    # ---------- PASSWORDS ----------
    def get_passwords(self, user_id: int) -> Tuple[bool, str, List[Dict[str, Any]]]:
        try:
            r = self.session.get(f"{self.base_url}/passwords/{user_id}", timeout=self.timeout)
            if r.ok:
                return True, "ok", r.json()
            return False, f"{r.status_code}: {r.text}", []
        except Exception as e:
            return False, str(e), []

    def add_password(
        self,
        user_id: int,
        site_name: str,
        username: str,
        encrypted_password: str,
        category: str,
        site_url: str = "",
        site_icon: str = "🔒",
        strength: str = "medium",
    ) -> Tuple[bool, str, Dict[str, Any]]:
        try:
            payload = {
                "user_id": user_id,
                "site_name": site_name,
                "username": username,
                "encrypted_password": encrypted_password,
                "category": category,
                "site_url": site_url,
                "site_icon": site_icon,
                "strength": strength,
            }
            r = self.session.post(f"{self.base_url}/passwords", json=payload, timeout=self.timeout)
            if r.ok:
                return True, "ok", r.json()
            return False, f"{r.status_code}: {r.text}", {}
        except Exception as e:
            return False, str(e), {}

    def update_password(self, pid: int, fields: Dict[str, Any]) -> Tuple[bool, str]:
        try:
            r = self.session.put(f"{self.base_url}/passwords/{pid}", json=fields, timeout=self.timeout)
            if r.ok:
                return True, "ok"
            return False, f"{r.status_code}: {r.text}"
        except Exception as e:
            return False, str(e)

    def trash_password(self, pid: int) -> Tuple[bool, str]:
        try:
            r = self.session.post(f"{self.base_url}/passwords/{pid}/trash", timeout=self.timeout)
            if r.ok:
                return True, "ok"
            return False, f"{r.status_code}: {r.text}"
        except Exception as e:
            return False, str(e)

    def restore_password(self, pid: int) -> Tuple[bool, str]:
        try:
            r = self.session.post(f"{self.base_url}/passwords/{pid}/restore", timeout=self.timeout)
            if r.ok:
                return True, "ok"
            return False, f"{r.status_code}: {r.text}"
        except Exception as e:
            return False, str(e)

    def delete_password(self, pid: int) -> Tuple[bool, str]:
        try:
            r = self.session.delete(f"{self.base_url}/passwords/{pid}", timeout=self.timeout)
            if r.ok:
                return True, "ok"
            return False, f"{r.status_code}: {r.text}"
        except Exception as e:
            return False, str(e)

    def reveal_password(self, pid: int) -> Tuple[bool, str, str]:
        try:
            r = self.session.get(f"{self.base_url}/passwords/{pid}/reveal", timeout=self.timeout)
            if r.ok:
                data = r.json()
                return True, "ok", data.get("encrypted_password", "")
            return False, f"{r.status_code}: {r.text}", ""
        except Exception as e:
            return False, str(e), ""

    def toggle_favorite(self, pid: int) -> Tuple[bool, str, bool]:
        try:
            r = self.session.post(f"{self.base_url}/passwords/{pid}/favorite", timeout=self.timeout)
            if r.ok:
                data = r.json()
                return True, "ok", bool(data.get("favorite"))
            return False, f"{r.status_code}: {r.text}", False
        except Exception as e:
            return False, str(e), False

    # ---------- STATS ----------
    def get_stats(self, user_id: int) -> Tuple[bool, str, Dict[str, Any]]:
        try:
            r = self.session.get(f"{self.base_url}/stats/{user_id}", timeout=self.timeout)
            if r.ok:
                return True, "ok", r.json()
            return False, f"{r.status_code}: {r.text}", {}
        except Exception as e:
            return False, str(e), {}

    # ---------- PROFILE ----------
    def get_profile(self, user_id: int) -> Tuple[bool, str, Dict[str, Any]]:
        try:
            r = self.session.get(f"{self.base_url}/profile/{user_id}", timeout=self.timeout)
            if r.ok:
                return True, "ok", r.json().get("user", {})
            return False, f"{r.status_code}: {r.text}", {}
        except Exception as e:
            return False, str(e), {}

    def update_profile(self, user_id: int, username: str, email: str) -> Tuple[bool, str]:
        try:
            r = self.session.put(
                f"{self.base_url}/profile/{user_id}",
                json={"username": username, "email": email},
                timeout=self.timeout,
            )
            if r.ok:
                return True, "ok"
            return False, f"{r.status_code}: {r.text}"
        except Exception as e:
            return False, str(e)

    # ---------- DEVICES / SESSIONS ----------
    def get_devices(self, user_id: int) -> Tuple[bool, str, List[Dict[str, Any]]]:
        try:
            r = self.session.get(f"{self.base_url}/devices/{user_id}", timeout=self.timeout)
            if r.ok:
                return True, "ok", r.json().get("devices", [])
            return False, f"{r.status_code}: {r.text}", []
        except Exception as e:
            return False, str(e), []

    def get_sessions(self, user_id: int) -> Tuple[bool, str, List[Dict[str, Any]]]:
        try:
            r = self.session.get(f"{self.base_url}/sessions/{user_id}", timeout=self.timeout)
            if r.ok:
                return True, "ok", r.json().get("sessions", [])
            return False, f"{r.status_code}: {r.text}", []
        except Exception as e:
            return False, str(e), []

    def revoke_session(self, session_id: int) -> Tuple[bool, str]:
        try:
            r = self.session.delete(f"{self.base_url}/sessions/{session_id}", timeout=self.timeout)
            if r.ok:
                return True, "ok"
            return False, f"{r.status_code}: {r.text}"
        except Exception as e:
            return False, str(e)

    def revoke_device_sessions(self, user_id: int, device_name: str) -> Tuple[bool, str]:
        try:
            payload = {"device_name": device_name}
            r = self.session.delete(
                f"{self.base_url}/devices/{user_id}/revoke",
                json=payload,
                timeout=self.timeout,
            )
            if r.ok:
                return True, "ok"
            return False, f"{r.status_code}: {r.text}"
        except Exception as e:
            return False, str(e)

    # ---------- EXPORT / IMPORT ----------
    def export_vault(self, user_id: int) -> Tuple[bool, str, Dict[str, Any]]:
        try:
            r = self.session.get(f"{self.base_url}/export/{user_id}", timeout=self.timeout)
            if r.ok:
                return True, "ok", r.json().get("vault", {})
            return False, f"{r.status_code}: {r.text}", {}
        except Exception as e:
            return False, str(e), {}

    def import_vault(self, user_id: int, vault: Dict[str, Any]) -> Tuple[bool, str, int]:
        try:
            r = self.session.post(f"{self.base_url}/import/{user_id}", json={"vault": vault}, timeout=self.timeout)
            if r.ok:
                return True, "ok", int(r.json().get("imported", 0))
            return False, f"{r.status_code}: {r.text}", 0
        except Exception as e:
            return False, str(e), 0
