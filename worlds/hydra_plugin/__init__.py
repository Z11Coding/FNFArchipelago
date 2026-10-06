from __future__ import annotations

import hashlib
import logging
import os
import struct
import zlib
from pathlib import Path
import sys
import threading
import time
from typing import TYPE_CHECKING, Any

from Utils import output_path
from worlds.APAPI import build_playthrough_model
from worlds.APAPI.hard_patch import register_after_patch

if TYPE_CHECKING:
    from BaseClasses import MultiWorld


logger = logging.getLogger("HydraPlugin")


# `.hydra` file format (little-endian throughout so C# BinaryReader just works):
#   magic[6]      ASCII "HYDRA1"
#   version u8    0x01
#   flags u8      bit0 = compressed (raw deflate), bit1 = encrypted (XOR-SHA256-CTR)
#   seed_len u16  + seed bytes (UTF-8 seed name, info only)
#   key_len u16   + key bytes (per-file random file key, stored IN the header
#                 so Hydra can read it back; see HydraFile.cs)
#   nonce_len u16 + nonce bytes (per-file random)
#   payload_len u64 + payload bytes (compressed, then encrypted)
#
# Keystream: SHA256(key || nonce || counter_be64) blocks, XORed sequentially.

MAGIC: bytes = b"HYDRA1"
VERSION: int = 1
FLAG_COMPRESSED: int = 0x01
FLAG_ENCRYPTED: int = 0x02
KEY_SIZE: int = 32
NONCE_SIZE: int = 16

_patched = False


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    """SHA256-CTR keystream (stdlib-only stream cipher)."""
    out = bytearray()
    counter: int = 0
    while len(out) < length:
        out.extend(hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest())
        counter += 1
    return bytes(out[:length])


def _xor(data: bytes, keystream: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(data, keystream))


def build_hydra_file(payload: bytes, seed_name: str) -> bytes:
    """Compress + encrypt ``payload`` into `.hydra` file bytes (random key/nonce)."""
    seed_raw: bytes = seed_name.encode("utf-8")
    key: bytes = os.urandom(KEY_SIZE)
    nonce: bytes = os.urandom(NONCE_SIZE)
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)  # raw deflate for C# DeflateStream
    compressed: bytes = compressor.compress(payload) + compressor.flush()
    encrypted: bytes = _xor(compressed, _keystream(key, nonce, len(compressed)))
    flags: int = FLAG_COMPRESSED | FLAG_ENCRYPTED
    return b"".join([
        MAGIC,
        struct.pack("<B", VERSION),
        struct.pack("<B", flags),
        struct.pack("<H", len(seed_raw)), seed_raw,
        struct.pack("<H", len(key)), key,
        struct.pack("<H", len(nonce)), nonce,
        struct.pack("<Q", len(encrypted)), encrypted,
    ])


def parse_hydra_file(data: bytes) -> dict[str, Any]:
    """Parse a `.hydra` file; returns header fields plus decrypted payload."""
    offset: int = 0

    def take(size: int) -> bytes:
        nonlocal offset
        chunk: bytes = data[offset:offset + size]
        if len(chunk) != size:
            raise ValueError("Truncated .hydra file.")
        offset += size
        return chunk

    if take(6) != MAGIC:
        raise ValueError("Not a .hydra file (bad magic).")
    version: int = struct.unpack("<B", take(1))[0]
    if version != VERSION:
        raise ValueError(f"Unsupported .hydra version {version}.")
    flags: int = struct.unpack("<B", take(1))[0]
    seed: str = take(struct.unpack("<H", take(2))[0]).decode("utf-8")
    key: bytes = take(struct.unpack("<H", take(2))[0])
    nonce: bytes = take(struct.unpack("<H", take(2))[0])
    payload: bytes = take(struct.unpack("<Q", take(8))[0])
    if offset != len(data):
        raise ValueError("Trailing bytes after .hydra payload.")
    if flags & FLAG_ENCRYPTED:
        payload = _xor(payload, _keystream(key, nonce, len(payload)))
    if flags & FLAG_COMPRESSED:
        payload = zlib.decompressobj(-15).decompress(payload)
    return {"version": version, "flags": flags, "seed": seed,
            "key": key, "nonce": nonce, "payload": payload}


def _export_hydra_file(multiworld: "MultiWorld") -> None:
    model = build_playthrough_model(multiworld)
    raw: bytes = model.to_json(indent=2).encode("utf-8")
    target = Path(output_path(f"AP_{multiworld.seed_name}.hydra"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(build_hydra_file(raw, str(multiworld.seed_name)))
    logger.info("[HydraPlugin] Wrote hydra file: %s", target)


def _after_main(
    result,
    args,
    seed: int | None = None,
    baked_server_options: dict[str, object] | None = None,
):
    if result is not None:
        try:
            from BaseClasses import MultiWorld

            if isinstance(result, MultiWorld):
                _export_hydra_file(result)
            else:
                logger.warning(
                    "[HydraPlugin] Main.main returned non-MultiWorld result of type %s",
                    type(result).__name__,
                )
        except Exception as exc:
            logger.warning("[HydraPlugin] Failed to export hydra file: %s", exc)
    return result


def _patch_main() -> None:
    global _patched
    if _patched:
        return

    for _ in range(240):
        if "Main" in sys.modules:
            try:
                register_after_patch("Main.main", _after_main, load_missing=False)
                _patched = True
            except Exception as exc:
                logger.warning("[HydraPlugin] Could not patch Main.main yet: %s", exc)
            return
        time.sleep(0.5)


threading.Thread(target=_patch_main, name="HydraPlugin-PatchMain", daemon=True).start()
