#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pyserial",
#   "numpy",
# ]
# ///
"""
OpenClaw digital pet — real-time audio emotion engine.

Connects to Trina-Pi-UP201 via UART, starts continuous PDM streaming
via the 'pet' shell command, and translates audio signals into
pet emotions displayed in the terminal.

Usage:
    uv run openclaw_pet.py [PORT] [BAUD]
    uv run openclaw_pet.py COM15
    uv run openclaw_pet.py COM15 921600
"""

import sys
import time
import random
import argparse
import struct
from collections import deque

import serial
import serial.tools.list_ports
import numpy as np

# ── audio config (must match firmware) ───────────────────────────────────────
SAMPLE_RATE      = 16_000
CHANNELS         = 2
BYTES_PER_SAMPLE = 2
BLOCK_BYTES      = 640        # PDM_PACKED_BYTES_PER_BUF: 160 samples × 2ch × 2B
SAMPLES_PER_BLK  = BLOCK_BYTES // (CHANNELS * BYTES_PER_SAMPLE)   # 160

# ── emotion signal thresholds (int16 RMS, range 0..32767) ────────────────────
THR_SILENCE  =   300    # below → silence
THR_GENTLE   =  1200    # gentle pat / touch
THR_VOICE    =  3000    # speaking / calling (also needs high ZCR)
THR_LOUD     =  9000    # excited / shouting
THR_SLAP     = 18000    # sudden impact peak → hurt/scared

CREST_IMPACT = 7.0      # peak/RMS ratio above this = sharp transient (slap)
ZCR_VOICE    = 0.12     # zero-crossing rate above this = voiced sound

HOLD_BLOCKS  = 18       # keep emotion displayed for N×10 ms (~1.8 s)
IDLE_BLOCKS  = 60       # consecutive silence before sleeping (~6 s)

# ── ASCII faces ───────────────────────────────────────────────────────────────
FACES = {
    "sleeping": [
        r"  /\_/\  ",
        r" ( -.- ) ",
        r"  > zzZ  ",
    ],
    "idle": [
        r"  /\_/\  ",
        r" ( o.o ) ",
        r"  > ^ <  ",
    ],
    "happy": [
        r"  /\_/\  ",
        r" ( ^.^ ) ",
        r"  (> <)  ",
    ],
    "excited": [
        r"  /\_/\  ",
        r" ( *.* ) ",
        r" /| ^ |\ ",
    ],
    "hurt": [
        r"  /\_/\  ",
        r" ( >.< ) ",
        r"  > x <  ",
    ],
    "scared": [
        r"  /\_/\  ",
        r" ( o_O ) ",
        r"  > ! <  ",
    ],
    "purring": [
        r"  /\_/\  ",
        r" ( ~w~ ) ",
        r"  >prrr< ",
    ],
    "alert": [
        r"  /\_/\  ",
        r" ( o.O ) ",
        r"  > ? <  ",
    ],
}

REACTIONS = {
    "sleeping": ["Zzz...",          "...zzzz...",         "*snoring softly*"],
    "idle":     ["...",             "*yawns*",            "*stretches*"],
    "happy":    ["Hehe~ tickles!",  "Yay! :3",            "So happy~"],
    "excited":  ["WOOOO!!!",        "Ahhhh!!!",           "SO EXCITING!!!"],
    "hurt":     ["OW! That hurt!",  "Ouch!!!",            ">.<  Stooop!"],
    "scared":   ["AHHH!!!",         "W-what was that?!",  "Scared >_<"],
    "purring":  ["Purrrrrr~",       "Mmm~ so nice~",      "*happy noises*"],
    "alert":    ["Hmm? Who's there?","I hear you~",       "Hello? :3"],
}


# ── signal analysis ───────────────────────────────────────────────────────────

def analyze(pcm_bytes: bytes) -> dict:
    """Analyze one 10 ms stereo int16 PCM block."""
    raw  = np.frombuffer(pcm_bytes, dtype="<i2").astype(np.float32)
    mono = (raw[0::2] + raw[1::2]) * 0.5

    rms   = float(np.sqrt(np.mean(mono ** 2)))
    peak  = float(np.max(np.abs(mono)))
    crest = peak / (rms + 1e-6)
    zcr   = float(np.mean(np.abs(np.diff(np.sign(mono))) > 0))

    return {"rms": rms, "peak": peak, "crest": crest, "zcr": zcr}


# ── emotion state machine ─────────────────────────────────────────────────────

class PetEmotion:
    def __init__(self):
        self.state    = "sleeping"
        self.hold     = 0
        self.idle_cnt = 0
        self._rms_q   = deque(maxlen=5)   # 5-block smoothing window (~50 ms)
        self._reaction: str | None = None

    def update(self, a: dict) -> tuple[str, str | None]:
        self._rms_q.append(a["rms"])
        srms  = sum(self._rms_q) / len(self._rms_q)
        peak  = a["peak"]
        crest = a["crest"]
        zcr   = a["zcr"]

        new = None

        if peak >= THR_SLAP and crest >= CREST_IMPACT:
            new = "hurt" if peak >= THR_SLAP * 1.5 else "scared"

        elif srms >= THR_LOUD:
            new = "excited"

        elif srms >= THR_VOICE and zcr >= ZCR_VOICE:
            # voiced sound: call or talking
            new = "alert" if self.state == "sleeping" else "happy"

        elif srms >= THR_GENTLE:
            # soft contact: gentle pat
            new = "purring" if crest < 4.0 else "happy"

        elif srms < THR_SILENCE:
            if self.hold > 0:
                self.hold -= 1
            else:
                self.idle_cnt += 1
                if self.idle_cnt >= IDLE_BLOCKS:
                    new = "sleeping"
                elif self.state not in ("sleeping", "idle"):
                    new = "idle"
        else:
            # between silence and gentle: reset idle counter
            self.idle_cnt = 0

        rx = None
        if new and new != self.state:
            self.state    = new
            self.hold     = HOLD_BLOCKS
            self.idle_cnt = 0
            rx = random.choice(REACTIONS[self.state])

        return self.state, rx


# ── terminal display ──────────────────────────────────────────────────────────

_DISPLAY_LINES = 0

def _bar(value: float, max_val: float = 32767.0, width: int = 20) -> str:
    filled = min(width, int(value / max_val * width))
    return "█" * filled + "░" * (width - filled)

def render(state: str, reaction: str | None, rms: float, peak: float,
           sticky_rx: str) -> None:
    global _DISPLAY_LINES

    face = FACES.get(state, FACES["idle"])
    lines = [
        "",
        *face,
        f"  [{state:^10}]",
        f"  Vol  {_bar(rms)}  {rms:5.0f}",
        f"  Peak {_bar(peak)}  {peak:5.0f}",
        f"  > {reaction or sticky_rx}",
        "",
    ]

    if _DISPLAY_LINES:
        sys.stdout.write(f"\033[{_DISPLAY_LINES}A\033[J")

    for l in lines:
        print(l)

    sys.stdout.flush()
    _DISPLAY_LINES = len(lines)


# ── serial helpers ────────────────────────────────────────────────────────────

PROMPT = b"mcu> "

def open_no_dtr(port: str, baud: int) -> serial.Serial:
    ser = serial.Serial()
    ser.port = port; ser.baudrate = baud; ser.timeout = 1
    ser.dsrdtr = False; ser.rtscts = False
    ser.open()
    time.sleep(0.3)
    ser.reset_input_buffer()
    return ser

def recv_prompt(ser: serial.Serial, timeout: float = 5.0) -> bytes:
    buf = b""; dl = time.monotonic() + timeout
    while time.monotonic() < dl:
        w = ser.in_waiting
        c = ser.read(w if w else 1)
        if c:
            buf += c
            if PROMPT in buf: break
    return buf

def wait_alive(ser: serial.Serial, retries: int = 4) -> bool:
    # Step 1: poke for a live prompt
    for _ in range(retries):
        ser.write(b"\r\n"); time.sleep(0.3)
        if PROMPT in recv_prompt(ser, 1.5): return True
        ser.reset_input_buffer()
    # Step 2: DTR reset and wait for boot
    ser.reset_input_buffer()
    ser.dtr = False; time.sleep(0.15); ser.dtr = True
    buf = b""; dl = time.monotonic() + 12.0
    while time.monotonic() < dl:
        c = ser.read(ser.in_waiting or 1)
        if c:
            buf += c
            if PROMPT in buf: return True
    # Step 3: one last poke
    ser.write(b"\r\n"); time.sleep(0.3)
    return PROMPT in recv_prompt(ser, 2.0)

def auto_detect_port() -> str | None:
    ports = serial.tools.list_ports.comports()
    for p in sorted(ports):
        if any(k in p.description.lower() for k in ("usb", "uart", "serial")):
            return p.device
    return sorted(ports)[0].device if ports else None


# ── pet stream session ────────────────────────────────────────────────────────

def run_pet(ser: serial.Serial) -> None:
    # ── send 'pet' command ────────────────────────────────────────────────
    ser.reset_input_buffer()
    ser.write(b"pet\r\n")

    print("Waiting for PET_START…")
    line_buf = b""
    header: dict | None = None
    deadline = time.monotonic() + 10.0

    while time.monotonic() < deadline:
        ch = ser.read(1)
        if not ch: continue
        if ch == b"\n":
            line = line_buf.decode(errors="replace").strip()
            line_buf = b""
            if line.startswith("PET_START"):
                parts = line.split()
                if len(parts) >= 5:
                    header = {
                        "sr":   int(parts[1]),
                        "ch":   int(parts[2]),
                        "bits": int(parts[3]),
                        "blk":  int(parts[4]),
                    }
                    break
        else:
            line_buf += ch

    if not header:
        print("[error] no PET_START received — is firmware compiled with 'pet' command?",
              file=sys.stderr)
        return

    blk = header["blk"]
    print(f"Stream: {header['sr']} Hz / {header['ch']}ch / {header['bits']}-bit "
          f"/ {blk} B per block")
    print("Ctrl-C to stop.\n")

    emotion   = PetEmotion()
    sticky_rx = "...waking up..."
    render("sleeping", None, 0, 0, sticky_rx)

    try:
        while True:
            # ── read exactly one block ────────────────────────────────────
            data = bytearray()
            while len(data) < blk:
                chunk = ser.read(blk - len(data))
                if chunk:
                    data += chunk
                    # early exit if device sent PET_STOP mid-block
                    if b"PET_STOP" in data:
                        print("\nDevice stopped streaming.")
                        return

            a             = analyze(bytes(data))
            state, rx     = emotion.update(a)

            if rx:
                sticky_rx = rx
            render(state, rx, a["rms"], a["peak"], sticky_rx)

    except KeyboardInterrupt:
        print("\nStopping…")
        ser.write(b"q")
        time.sleep(0.5)
        # drain until PET_STOP
        tail_dl = time.monotonic() + 3.0
        tail    = b""
        while time.monotonic() < tail_dl:
            c = ser.read(1)
            if c:
                tail += c
                if b"PET_STOP" in tail: break
        recv_prompt(ser, timeout=3.0)
        print("Disconnected.")


# ── one-shot sample mode (for Claude Code / non-interactive use) ──────────────

def run_sample(ser: serial.Serial, duration_ms: int) -> None:
    """
    Capture <duration_ms> of audio using the existing 'stream' command,
    analyze it, and print a single JSON result to stdout.

    This mode is designed for Claude Code tool calls — no ANSI, no loops,
    just one clean JSON line and exit.

    Example output:
        {"emotion": "happy", "rms": 2340, "peak": 8100, "reaction": "Hehe~ tickles!"}
    """
    import json

    # Use the existing bounded stream command (no firmware changes needed)
    duration_ms = max(500, min(duration_ms, 10000))
    ser.reset_input_buffer()
    ser.write(f"stream {duration_ms}\r\n".encode())

    # Wait for STREAM_START header
    line_buf = b""
    header: dict | None = None
    deadline = time.monotonic() + 10.0

    while time.monotonic() < deadline:
        ch = ser.read(1)
        if not ch: continue
        if ch == b"\n":
            line = line_buf.decode(errors="replace").strip()
            line_buf = b""
            if line.startswith("STREAM_START"):
                parts = line.split()
                if len(parts) >= 6:
                    header = {"n_blocks": int(parts[1]), "blk": int(parts[5])}
                    break
        else:
            line_buf += ch

    if not header:
        print(json.dumps({"error": "no STREAM_START received"}))
        return

    n_blocks  = header["n_blocks"]
    blk_bytes = header["blk"]
    total     = n_blocks * blk_bytes

    # Read all PCM data
    data = bytearray()
    dl   = time.monotonic() + duration_ms / 1000 * 2 + 5
    while len(data) < total and time.monotonic() < dl:
        chunk = ser.read(min(total - len(data), 4096))
        if chunk:
            data += chunk

    # Drain STREAM_END + prompt
    tail_dl = time.monotonic() + 3.0
    tail    = b""
    while time.monotonic() < tail_dl:
        c = ser.read(1)
        if c:
            tail += c
            if b"STREAM_END" in tail: break
    recv_prompt(ser, timeout=3.0)

    # Analyze the full window
    emotion   = PetEmotion()
    final_rx  = REACTIONS["idle"][0]
    final_st  = "idle"
    block_size = blk_bytes

    for off in range(0, len(data) - block_size + 1, block_size):
        block         = bytes(data[off:off + block_size])
        a             = analyze(block)
        state, rx     = emotion.update(a)
        final_st = state
        if rx:
            final_rx = rx

    a_full = analyze(bytes(data[:min(len(data), block_size * 20)]))

    print(json.dumps({
        "emotion":  final_st,
        "reaction": final_rx,
        "rms":      round(a_full["rms"], 1),
        "peak":     round(a_full["peak"], 1),
        "duration_ms": duration_ms,
    }))


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="OpenClaw digital pet")
    parser.add_argument("port", nargs="?", default=None,
                        help="COM port (default: auto-detect)")
    parser.add_argument("baud", nargs="?", type=int, default=921600,
                        help="Baud rate (default: 921600)")
    parser.add_argument("--sample", metavar="MS", type=int, default=None,
                        help="One-shot: capture MS ms, print emotion JSON, exit. "
                             "For Claude Code / non-interactive use.")
    cfg = parser.parse_args()

    port = cfg.port or auto_detect_port()
    if not port:
        print("No COM port found.", file=sys.stderr)
        sys.exit(1)

    ser = open_no_dtr(port, cfg.baud)

    if not wait_alive(ser):
        print("[error] no prompt from device", file=sys.stderr)
        ser.close()
        sys.exit(1)

    if cfg.sample is not None:
        run_sample(ser, cfg.sample)
    else:
        print(f"Connecting to {port} @ {cfg.baud}…\nConnected.\n")
        run_pet(ser)

    ser.close()


if __name__ == "__main__":
    main()
