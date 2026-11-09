#!/usr/bin/env python3
"""Maakt een klein, zelfgegenereerd testbestand (WAV-sinus, 2 s) voor de stock-client-smoketest.

Geen auteursrechtelijk materiaal, geen netwerk, deterministisch (zelfde bytes bij elke run).
Gebruik: make_test_media.py <muziekmap>  → <muziekmap>/Jelly Leon Test/Smoketest/01 - Sinus 440 Hz.wav
"""

from __future__ import annotations

import math
import struct
import sys
import wave
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("gebruik: make_test_media.py <muziekmap>", file=sys.stderr)
        return 2
    target = Path(argv[1]) / "Jelly Leon Test" / "Smoketest" / "01 - Sinus 440 Hz.wav"
    target.parent.mkdir(parents=True, exist_ok=True)
    rate = 22050
    frames = b"".join(
        struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(rate * 2)
    )
    with wave.open(str(target), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(frames)
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
