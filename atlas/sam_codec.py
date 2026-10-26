"""Decoder for SAM 3.1 'one_bit' mask payloads (Meta Model API).

Written for Atlas from the published format (Meta's meta-sam-parser documents it):
a base85 payload (ASCII 0x21-0x7E without " \\ , ; < > |, radix 85, a 5-digit
length prefix, then 4-byte groups) carrying a binary range-coded raster. Each
pixel's bit is coded with adaptive counts selected by a 12-pixel causal context
(two pixels to the left and five in each of the two rows above).
"""
from __future__ import annotations

from array import array

import numpy as np

_EXCLUDED = set('"\\,;<>|')
_ALPHABET = "".join(chr(c) for c in range(0x21, 0x7F) if chr(c) not in _EXCLUDED)
_VAL = {ch: i for i, ch in enumerate(_ALPHABET[:85])}
_M32 = 0xFFFFFFFF
_TOP, _BOTTOM = 1 << 24, 1 << 16
_INC, _LIMIT = 14, 4096
_PAD = 2


def unpack(payload: str) -> bytes:
    n = 0
    for ch in payload[:5]:
        n = n * 85 + _VAL[ch]
    out = bytearray(n)
    src, dst = 5, 0
    full = n - n % 4
    while dst < full:
        v = 0
        for ch in payload[src:src + 5]:
            v = v * 85 + _VAL[ch]
        out[dst:dst + 4] = v.to_bytes(4, "big")
        src += 5
        dst += 4
    rem = n % 4
    if rem:
        v = 0
        for i in range(5):
            v = v * 85 + (_VAL[payload[src + i]] if i < rem + 1 else 84)
        out[dst:dst + rem] = v.to_bytes(4, "big")[:rem]
    return bytes(out)


def decode_one_bit(payload: str, h: int, w: int) -> np.ndarray:
    """payload without the leading '!' marker -> (h, w) bool array."""
    data = unpack(payload)
    pos = 4
    code = int.from_bytes(data[:4], "big")
    low, rng = 0, _M32
    counts = array("H", [1]) * (8192)
    pw = w + 2 * _PAD
    pad = bytearray(pw * (h + _PAD))
    out = bytearray(w * h)
    ln = len(data)
    for y in range(h):
        row = (y + _PAD) * pw + _PAD
        for x in range(w):
            p = row + x
            pr = p - pw
            er = p - 2 * pw
            ctx = (pad[p - 1] | (pad[p - 2] << 1) | (pad[pr - 2] << 2) | (pad[pr - 1] << 3) | (pad[pr] << 4)
                   | (pad[pr + 1] << 5) | (pad[pr + 2] << 6) | (pad[er - 2] << 7) | (pad[er - 1] << 8)
                   | (pad[er] << 9) | (pad[er + 1] << 10) | (pad[er + 2] << 11))
            o = ctx << 1
            z, one = counts[o], counts[o + 1]
            tot = z + one
            scaled = rng // tot
            val = ((code - low) & _M32) // scaled
            if val >= tot:
                val = tot - 1
            if val < z:
                bit, cum, freq = 0, 0, z
            else:
                bit, cum, freq = 1, z, one
            low = (low + scaled * cum) & _M32
            rng = scaled * freq
            while True:
                if (low ^ ((low + rng) & _M32)) < _TOP:
                    pass
                elif rng < _BOTTOM:
                    rng = (-low) & _M32 & (_BOTTOM - 1)
                else:
                    break
                code = ((code << 8) | (data[pos] if pos < ln else 0)) & _M32
                pos += 1
                low = (low << 8) & _M32
                rng = (rng << 8) & _M32
            pad[p] = bit
            out[y * w + x] = bit
            c = counts[o + bit] + _INC
            counts[o + bit] = c & 0xFFFF
            if counts[o] + counts[o + 1] >= _LIMIT:
                counts[o] = (counts[o] >> 1) or 1
                counts[o + 1] = (counts[o + 1] >> 1) or 1
    return np.frombuffer(bytes(out), dtype=np.uint8).reshape(h, w).astype(bool)
