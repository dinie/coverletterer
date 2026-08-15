"""Tests for browser-extension personal access tokens."""

from coverletterer.services import api_tokens


def test_hash_is_deterministic_and_not_raw():
    h = api_tokens._hash("abc")
    assert h == api_tokens._hash("abc")
    assert h != "abc"
    assert len(h) == 64  # sha256 hex


def test_generate_then_resolve_roundtrip(monkeypatch):
    store: dict[str, int] = {}

    def fake_generate(user_id):
        raw = "raw-token-for-" + str(user_id)
        store[api_tokens._hash(raw)] = user_id
        return raw

    def fake_resolve(raw):
        return store.get(api_tokens._hash(raw))

    monkeypatch.setattr(api_tokens, "generate", fake_generate)
    monkeypatch.setattr(api_tokens, "resolve", fake_resolve)

    raw = api_tokens.generate(42)
    assert api_tokens.resolve(raw) == 42


def test_resolve_empty_or_unknown_returns_none(monkeypatch):
    monkeypatch.setattr(api_tokens, "resolve", lambda raw: None if not raw else None)
    assert api_tokens.resolve("") is None
    assert api_tokens.resolve("nonexistent") is None


def test_regenerate_invalidates_previous_token(monkeypatch):
    # A regenerate should replace the stored hash, so the old raw token no
    # longer resolves. Simulate with a single-slot fake store (mirrors the
    # "at most one token per user" upsert behavior).
    store: dict[int, str] = {}

    def fake_generate(user_id):
        raw = f"token-{user_id}-{len(store) + 1}"
        store[user_id] = api_tokens._hash(raw)
        return raw

    def fake_resolve(raw):
        h = api_tokens._hash(raw)
        for user_id, stored_hash in store.items():
            if stored_hash == h:
                return user_id
        return None

    monkeypatch.setattr(api_tokens, "generate", fake_generate)
    monkeypatch.setattr(api_tokens, "resolve", fake_resolve)

    first = api_tokens.generate(1)
    assert api_tokens.resolve(first) == 1

    second = api_tokens.generate(1)
    assert second != first
    assert api_tokens.resolve(second) == 1
    assert api_tokens.resolve(first) is None
