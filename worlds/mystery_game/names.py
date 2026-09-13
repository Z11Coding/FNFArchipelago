from __future__ import annotations

"""Chained-hash slot/game identities for Mystery lock/scramble modes.

Stdlib-only: unit testable anywhere. The point is server-side wrongness —
renamed games/slots make direct connection via the real server impossible
(``InvalidSlot``/``InvalidGame``), while the proxy resolves them through
the identity map.

Unpredictability comes from three layers:

1. A per-seed, per-player, per-pool salt (seed name + player id + the
   sorted names of items sent to that slot), so the hash moves with the seed
   *and* with what the slot receives.
2. A random 1–3 link chain drawn from a table of encoding/encryption
   methods (sha256/md5 hex, sha1-base32, base64url, xor-hex, rot stages,
   reversal), so the method itself varies per slot.
3. Caller-enforced uniqueness (re-hash with ``#n`` salts on collision).

All output is ASCII alphanumeric of an exact length. Deterministic for
identical inputs (generation-safe).
"""

import base64
import hashlib
import random
from typing import Any, Callable


def _sha256_hex(text: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}|{text}".encode("utf-8")).hexdigest()


def _md5_hex(text: str, salt: str) -> str:
    return hashlib.md5(f"{salt}|{text}".encode("utf-8")).hexdigest()


def _sha1_b32(text: str, salt: str) -> str:
    digest: bytes = hashlib.sha1(f"{salt}|{text}".encode("utf-8")).digest()
    return base64.b32encode(digest).decode("ascii").rstrip("=")


def _b64url(text: str, salt: str) -> str:
    digest: bytes = hashlib.sha256(f"{text}|{salt}".encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _xor_hex(text: str, salt: str) -> str:
    key: bytes = hashlib.sha256(salt.encode("utf-8")).digest()
    data: bytes = text.encode("utf-8")
    return "".join(f"{byte ^ key[i % len(key)]:02x}" for i, byte in enumerate(data))


def _rot_mix(text: str, salt: str) -> str:
    mixed: str = f"{salt}{text}{salt[::-1]}"
    out: list[str] = []
    for i, char in enumerate(mixed):
        code: int = ord(char)
        if "a" <= char <= "z":
            out.append(chr((code - 97 + i) % 26 + 97))
        elif "A" <= char <= "Z":
            out.append(chr((code - 65 + i * 2) % 26 + 65))
        elif char.isascii() and char.isalnum():
            out.append(char)
    return "".join(out)


def _reversed(text: str, salt: str) -> str:
    return f"{salt}{text}"[::-1]


_METHODS: list[tuple[str, Callable[[str, str], str]]] = [
    ("sha256", _sha256_hex),
    ("md5", _md5_hex),
    ("sha1b32", _sha1_b32),
    ("b64url", _b64url),
    ("xor", _xor_hex),
    ("rot", _rot_mix),
    ("rev", _reversed),
]


def _clean(value: str) -> str:
    return "".join(char for char in value if char.isascii() and char.isalnum())


def _seed_int(seed_name: str, player: int, salt_items: list[str], extra: tuple[str, ...]) -> int:
    blob: str = "|".join([str(seed_name), str(player), ",".join(salt_items), ",".join(extra)])
    return int.from_bytes(hashlib.sha256(blob.encode("utf-8")).digest()[:8], "big")


def hash_identity(
    text: str,
    seed_name: str,
    player: int,
    salt_items: list[str] | None = None,
    length: int = 12,
    extra: tuple[str, ...] = (),
) -> str:
    """Hash ``text`` into an unpredictable ASCII-alphanumeric identity."""
    items: list[str] = sorted(salt_items) if salt_items else []
    rng = random.Random(_seed_int(seed_name, player, items, extra))
    chain: list[tuple[str, Callable[[str, str], str]]] = [
        rng.choice(_METHODS) for _ in range(rng.randint(1, 3))]
    value: str = text
    for link, (_name, method) in enumerate(chain):
        value = method(value, f"{seed_name}|{player}|{link}")
    cleaned: str = _clean(value)
    stretch: int = 0
    while len(cleaned) < length:
        cleaned += _sha256_hex(f"{cleaned}|{stretch}", str(seed_name))
        stretch += 1
    return cleaned[:length]


def hash_slot_game(
    real_game: str,
    seed_name: str,
    player: int,
    salt_items: list[str] | None = None,
    extra: tuple[str, ...] = (),
) -> str:
    """Hashed game name for a locked slot (12 chars)."""
    return hash_identity(real_game, seed_name, player, salt_items, length=12, extra=extra)


def hash_slot_name(
    real_name: str,
    seed_name: str,
    player: int,
    salt_items: list[str] | None = None,
    extra: tuple[str, ...] = (),
) -> str:
    """Hashed slot name for full scramble (10 chars)."""
    return hash_identity(real_name, seed_name, player, salt_items, length=10, extra=extra)


def make_unique(
    candidate: str,
    used: set[str],
    rehash: Callable[[tuple[str, ...]], str],
) -> str:
    """Append ``#n`` re-hash salts until ``candidate`` is unused."""
    attempt: int = 1
    while candidate in used:
        candidate = rehash((f"dup{attempt}",))
        attempt += 1
    used.add(candidate)
    return candidate


__all__ = [
    "hash_identity",
    "hash_slot_game",
    "hash_slot_name",
    "make_unique",
]
