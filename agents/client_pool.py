from __future__ import annotations

from google import genai


class ClientPool:
    def __init__(self, api_keys: list[str]) -> None:
        self.keys = [key for key in api_keys if key]
        if not self.keys:
            raise ValueError("ClientPool requires at least one API key.")
        self._index = 0
        self._client: genai.Client | None = genai.Client(api_key=self.keys[self._index])

    def get_client(self) -> genai.Client:
        if self._client is None or getattr(self._client, "closed", False):
            self._client = genai.Client(api_key=self.keys[self._index])
        return self._client

    def rotate(self) -> str:
        self._index = (self._index + 1) % len(self.keys)
        self._client = genai.Client(api_key=self.keys[self._index])
        return self.keys[self._index]

    def current_key_index(self) -> int:
        return self._index
