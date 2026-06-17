from __future__ import annotations

from dataclasses import dataclass

import pytest

import agents.client_pool as client_pool_module
from agents.client_pool import ClientPool


@dataclass
class FakeClient:
    api_key: str
    closed: bool = False


def test_client_pool_filters_empty_keys_and_creates_first_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_keys: list[str] = []

    def fake_client(*, api_key: str) -> FakeClient:
        created_keys.append(api_key)
        return FakeClient(api_key=api_key)

    monkeypatch.setattr(client_pool_module.genai, "Client", fake_client)

    pool = ClientPool(["key-1", "", "key-2"])

    assert pool.keys == ["key-1", "key-2"]
    assert created_keys == ["key-1"]
    assert pool.get_client().api_key == "key-1"


def test_client_pool_raises_when_all_keys_are_empty() -> None:
    with pytest.raises(ValueError, match="at least one API key"):
        ClientPool(["", ""])


def test_get_client_returns_existing_open_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_keys: list[str] = []

    def fake_client(*, api_key: str) -> FakeClient:
        created_keys.append(api_key)
        return FakeClient(api_key=api_key)

    monkeypatch.setattr(client_pool_module.genai, "Client", fake_client)
    pool = ClientPool(["key-1"])

    existing = pool.get_client()
    returned = pool.get_client()

    assert returned is existing
    assert created_keys == ["key-1"]


def test_get_client_recreates_when_client_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_keys: list[str] = []

    def fake_client(*, api_key: str) -> FakeClient:
        created_keys.append(api_key)
        return FakeClient(api_key=api_key)

    monkeypatch.setattr(client_pool_module.genai, "Client", fake_client)
    pool = ClientPool(["key-1"])
    pool._client = None

    recreated = pool.get_client()

    assert recreated.api_key == "key-1"
    assert created_keys == ["key-1", "key-1"]


def test_get_client_recreates_when_client_is_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_keys: list[str] = []

    def fake_client(*, api_key: str) -> FakeClient:
        created_keys.append(api_key)
        return FakeClient(api_key=api_key)

    monkeypatch.setattr(client_pool_module.genai, "Client", fake_client)
    pool = ClientPool(["key-1"])
    pool._client = FakeClient(api_key="key-1", closed=True)

    recreated = pool.get_client()

    assert recreated.closed is False
    assert created_keys == ["key-1", "key-1"]


def test_rotate_switches_key_and_wraps_around(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_keys: list[str] = []

    def fake_client(*, api_key: str) -> FakeClient:
        created_keys.append(api_key)
        return FakeClient(api_key=api_key)

    monkeypatch.setattr(client_pool_module.genai, "Client", fake_client)
    pool = ClientPool(["key-1", "key-2"])

    next_key = pool.rotate()
    wrapped_key = pool.rotate()

    assert next_key == "key-2"
    assert wrapped_key == "key-1"
    assert pool.current_key_index() == 0
    assert created_keys == ["key-1", "key-2", "key-1"]


def test_current_key_index_returns_current_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client_pool_module.genai, "Client", lambda *, api_key: FakeClient(api_key=api_key))
    pool = ClientPool(["key-1", "key-2", "key-3"])

    pool.rotate()

    assert pool.current_key_index() == 1
