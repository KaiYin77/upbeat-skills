#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pyserial",
# ]
# ///
"""
Trina-Pi-UP201 interactive shell client.

Usage:
    uv run ~/.claude/commands/mcu/mcu_shell.py                          # auto-detect port @ 921600
    uv run ~/.claude/commands/mcu/mcu_shell.py COM4                     # explicit port
    uv run ~/.claude/commands/mcu/mcu_shell.py COM4 3000000             # explicit port + baud
    uv run ~/.claude/commands/mcu/mcu_shell.py --list                   # list available COM ports
    uv run ~/.claude/commands/mcu/mcu_shell.py --run ver --run info     # non-interactive batch query
    uv run ~/.claude/commands/mcu/mcu_shell.py --record 1000               # batch record 1 s (max 1960 ms)
    uv run ~/.claude/commands/mcu/mcu_shell.py --record 1000 --out a.wav   # batch with custom filename
    uv run ~/.claude/commands/mcu/mcu_shell.py --stream 5000               # real-time stream 5 s (no limit)
    uv run ~/.claude/commands/mcu/mcu_shell.py --stream 5000 --out b.wav   # stream with custom filename

Interactive host commands (prefix !):
    !help                    show this list
    !ports                   list COM ports
    !port <PORT>             switch port
    !baud <RATE>             switch baud rate
    !record <ms> [file.wav]  batch record to SRAM then save WAV (max 1960 ms)
    !stream <ms> [file.wav]  stream audio in real-time, save WAV (no size limit)
    !reset                   reset MCU
    !exit                    disconnect

MCU shell commands (sent directly):
    help  ver  info  echo  mr  mw  hist  reset
    record [ms]   batch record, default 1000 ms, max 1960 ms
    stream [ms]   real-time stream, default 1000 ms, no size limit
    pdm start|stop|status|record [ms]|stream [ms]
"""

import sys
import os
import time
import wave
import struct
import argparse
import textwrap
import datetime

import serial
import serial.tools.list_ports

# ── constants ──────────────────────────────────────────────────────────────
MCU_PROMPT   = b"mcu> "
HOST_PROMPT  = ">> "
DEFAULT_PORT = "COM3"
DEFAULT_BAUD = 921600
RECV_TIMEOUT = 3.0      # seconds to wait for mcu> after a normal command


# ── serial helpers ─────────────────────────────────────────────────────────

def open_port(port: str, baud: int) -> serial.Serial:
    try:
        ser = serial.Serial()
        ser.port     = port
        ser.baudrate = baud
        ser.timeout  = RECV_TIMEOUT
        ser.dsrdtr   = False   # don't auto-toggle DTR on open (avoids resetting a running board)
        ser.rtscts   = False
        ser.open()
    except serial.SerialException as e:
        print(f"[error] cannot open {port}: {e}", file=sys.stderr)
        sys.exit(1)
    time.sleep(0.2)
    ser.reset_input_buffer()
    return ser


def dtr_reset(ser: serial.Serial, pulse_ms: int = 100) -> None:
    """Toggle DTR low→high to hardware-reset the board."""
    ser.dtr = False
    time.sleep(pulse_ms / 1000)
    ser.dtr = True
    time.sleep(0.1)


def recv_until_prompt(ser: serial.Serial, timeout: float = RECV_TIMEOUT) -> bytes:
    """Read bytes until MCU_PROMPT appears or timeout."""
    buf = b""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        waiting = ser.in_waiting
        chunk = ser.read(waiting if waiting else 1)
        if chunk:
            buf += chunk
            if buf.endswith(MCU_PROMPT):
                break
    return buf


def decode(raw: bytes) -> str:
    return raw.decode(errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def send_cmd(ser: serial.Serial, cmd: str, timeout: float = RECV_TIMEOUT) -> str:
    """Send one command, wait for mcu> , return output lines (echo stripped)."""
    ser.write((cmd + "\r\n").encode())
    raw = recv_until_prompt(ser, timeout)
    text = decode(raw)

    lines = text.splitlines()
    lines = [l for l in lines if not l.startswith("mcu>")]

    if lines and lines[0].strip() == cmd.strip():
        lines = lines[1:]

    return "\n".join(lines).strip()


# ── port listing ────────────────────────────────────────────────────────────

def list_ports():
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("No COM ports found.")
        return
    print(f"{'Port':<12} {'Description'}")
    print("-" * 50)
    for p in sorted(ports):
        print(f"{p.device:<12} {p.description}")


# ── connection check ────────────────────────────────────────────────────────

def wait_for_prompt(ser: serial.Serial, retries: int = 3) -> bool:
    for _ in range(retries):
        ser.write(b"\r\n")
        time.sleep(0.3)
        raw = recv_until_prompt(ser, timeout=1.0)
        if MCU_PROMPT in raw:
            return True
        ser.reset_input_buffer()
    return False


def reset_and_wait(ser: serial.Serial, boot_timeout: float = 10.0) -> bool:
    """DTR-reset the board and wait for the shell prompt."""
    print("Resetting board via DTR\u2026")
    ser.reset_input_buffer()
    dtr_reset(ser)
    buf = b""
    deadline = time.monotonic() + boot_timeout
    while time.monotonic() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            buf += chunk
            sys.stdout.write(chunk.decode(errors="replace"))
            sys.stdout.flush()
            if buf.endswith(MCU_PROMPT):
                print()
                return True
    return MCU_PROMPT in buf


# ── audio recording ─────────────────────────────────────────────────────────

def receive_recording(ser: serial.Serial,
                      duration_ms: int) -> tuple[bytes, int, int, int] | None:
    """
    Send 'pdm record <ms>' to the MCU, receive the binary framed response,
    and return (pcm_bytes, sample_rate, channels, bit_depth).

    Wire protocol from device:
        Recording <ms> ms...\r\n
        REC_START <bytes> <sr> <ch> <bits>\r\n
        <bytes of raw little-endian PCM>
        \r\nREC_END\r\n
        mcu>
    """
    # generous timeout: record duration + TX time + margin
    total_timeout = (duration_ms / 1000) + (duration_ms / 1000 * 1.5) + 10

    ser.write(f"pdm record {duration_ms}\r\n".encode())

    # ── read text lines until REC_START ──────────────────────────────────
    line_buf = b""
    header: dict | None = None
    deadline = time.monotonic() + total_timeout

    while time.monotonic() < deadline:
        ch = ser.read(1)
        if not ch:
            continue
        if ch == b"\n":
            line = line_buf.decode(errors="replace").strip()
            line_buf = b""
            if line and not line.startswith("mcu>") and not line == f"pdm record {duration_ms}":
                print(f"  {line}")
            if line.startswith("REC_START"):
                parts = line.split()
                if len(parts) >= 5:
                    header = {
                        "bytes":      int(parts[1]),
                        "rate":       int(parts[2]),
                        "channels":   int(parts[3]),
                        "bit_depth":  int(parts[4]),
                    }
                    break
        else:
            line_buf += ch

    if header is None:
        print("[error] REC_START marker not received.", file=sys.stderr)
        return None

    n = header["bytes"]
    print(f"  Receiving {n} bytes "
          f"({header['rate']} Hz / {header['channels']}ch / {header['bit_depth']}-bit)\u2026")

    # ── read exactly n raw PCM bytes ──────────────────────────────────────
    data = bytearray()
    rx_deadline = time.monotonic() + n / 80_000 + 10   # ~80 KB/s + margin
    while len(data) < n and time.monotonic() < rx_deadline:
        chunk = ser.read(min(n - len(data), 4096))
        if chunk:
            data += chunk

    if len(data) < n:
        print(f"[warn] only received {len(data)}/{n} bytes.", file=sys.stderr)

    # ── drain until REC_END then mcu> ────────────────────────────────────
    tail = b""
    tail_deadline = time.monotonic() + 5
    while time.monotonic() < tail_deadline:
        c = ser.read(1)
        if c:
            tail += c
            if b"REC_END" in tail:
                break

    recv_until_prompt(ser, timeout=3.0)

    return bytes(data), header["rate"], header["channels"], header["bit_depth"]


def receive_stream(ser: serial.Serial,
                   duration_ms: int) -> tuple[bytes, int, int, int] | None:
    """
    Send 'stream <ms>' to the MCU and receive audio blocks in real-time,
    writing each block to a bytearray as it arrives.

    Wire protocol from device:
        STREAM_START <n_blocks> <sr> <ch> <bits> <block_bytes>\r\n
        <n_blocks × block_bytes raw PCM bytes>
        \r\nSTREAM_END\r\n
        mcu>
    """
    total_timeout = (duration_ms / 1000) * 2 + 10

    ser.write(f"stream {duration_ms}\r\n".encode())

    # ── read text lines until STREAM_START ───────────────────────────────
    line_buf = b""
    header: dict | None = None
    deadline = time.monotonic() + total_timeout

    while time.monotonic() < deadline:
        ch = ser.read(1)
        if not ch:
            continue
        if ch == b"\n":
            line = line_buf.decode(errors="replace").strip()
            line_buf = b""
            if line and not line.startswith("mcu>") and \
               not line.strip() == f"stream {duration_ms}":
                print(f"  {line}")
            if line.startswith("STREAM_START"):
                parts = line.split()
                if len(parts) >= 6:
                    header = {
                        "n_blocks":    int(parts[1]),
                        "rate":        int(parts[2]),
                        "channels":    int(parts[3]),
                        "bit_depth":   int(parts[4]),
                        "block_bytes": int(parts[5]),
                    }
                    break
        else:
            line_buf += ch

    if header is None:
        print("[error] STREAM_START marker not received.", file=sys.stderr)
        return None

    n_blocks    = header["n_blocks"]
    block_bytes = header["block_bytes"]
    total_bytes = n_blocks * block_bytes

    print(f"  Streaming {n_blocks} blocks × {block_bytes} B "
          f"= {total_bytes} B  "
          f"({header['rate']} Hz / {header['channels']}ch / {header['bit_depth']}-bit)")

    # ── receive blocks, show live progress ───────────────────────────────
    data = bytearray()
    rx_deadline = time.monotonic() + total_timeout
    last_pct = -1

    while len(data) < total_bytes and time.monotonic() < rx_deadline:
        want  = min(total_bytes - len(data), 4096)
        chunk = ser.read(want)
        if chunk:
            data += chunk
            pct = len(data) * 100 // total_bytes
            if pct != last_pct and pct % 10 == 0:
                print(f"  {pct:3d}%  {len(data)}/{total_bytes} bytes")
                last_pct = pct

    if len(data) < total_bytes:
        print(f"[warn] only received {len(data)}/{total_bytes} bytes.", file=sys.stderr)

    # ── drain tail (STREAM_END + mcu>) ───────────────────────────────────
    tail = b""
    tail_deadline = time.monotonic() + 5
    while time.monotonic() < tail_deadline:
        c = ser.read(1)
        if c:
            tail += c
            if b"STREAM_END" in tail:
                break

    recv_until_prompt(ser, timeout=3.0)

    return bytes(data), header["rate"], header["channels"], header["bit_depth"]


def do_stream(ser: serial.Serial, duration_ms: int,
              out_path: str | None = None) -> str | None:
    """Stream audio from the MCU in real-time and save as WAV."""
    if out_path is None:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = f"recordings/stream_{ts}_{duration_ms}ms.wav"

    print(f"Streaming {duration_ms} ms \u2192 {out_path}")
    result = receive_stream(ser, duration_ms)
    if result is None:
        return None

    pcm, sr, ch, bits = result
    return save_wav(pcm, sr, ch, bits, out_path)


def save_wav(pcm: bytes, sample_rate: int, channels: int,
             bit_depth: int, filename: str) -> str:
    """
    Write raw PCM bytes to a mono WAV file (matching reference audio.py).

    Firmware sends interleaved stereo int16-LE (L,R,L,R,...) where each
    16-bit sample = (24-bit DMA word >> 8) & 0xFFFF — bytes 1 and 2 of the
    32-bit DMA word, preserving sign from the MSByte.

    Since the board has a single PDM mic (L == R), we downmix to mono by
    averaging the two channels, matching audio.py's nchannels=1 output.
    """
    os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)

    bytes_per_sample = bit_depth // 8
    fmt = "<" + "h" * (len(pcm) // bytes_per_sample)
    samples = struct.unpack(fmt, pcm)

    if channels == 2:
        # Average L and R (both from same PDM mic) → mono
        mono = [
            (samples[i] + samples[i + 1]) // 2
            for i in range(0, len(samples), 2)
        ]
        out_channels = 1
    else:
        mono = list(samples)
        out_channels = channels

    packed = struct.pack("<" + "h" * len(mono), *mono)

    with wave.open(filename, "wb") as wf:
        wf.setnchannels(out_channels)
        wf.setsampwidth(bytes_per_sample)
        wf.setframerate(sample_rate)
        wf.writeframes(packed)

    duration_s = len(mono) / sample_rate
    print(f"  Saved {filename}  ({duration_s:.2f} s, {len(packed)} bytes)")
    return filename


def do_record(ser: serial.Serial, duration_ms: int,
              out_path: str | None = None) -> str | None:
    """
    Record audio from the MCU and save as WAV.
    Returns the saved filepath, or None on failure.
    """
    if out_path is None:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = f"recordings/rec_{ts}_{duration_ms}ms.wav"

    print(f"Recording {duration_ms} ms \u2192 {out_path}")
    result = receive_recording(ser, duration_ms)
    if result is None:
        return None

    pcm, sr, ch, bits = result
    return save_wav(pcm, sr, ch, bits, out_path)


# ── built-in host commands (prefixed with !) ────────────────────────────────

HELP_TEXT = textwrap.dedent("""\
    Host commands (prefix !):
      !help                    show this message
      !ports                   list available COM ports
      !port <PORT>             switch to a different COM port (same baud)
      !baud <RATE>             switch baud rate (reconnects)
      !record <ms> [file.wav]  batch record to SRAM then save WAV (max 1960 ms)
      !stream <ms> [file.wav]  stream audio in real-time, save WAV (no size limit)
      !reset                   reset the MCU
      !exit / !quit            disconnect and exit

    All other input is forwarded to the Trina-Pi-UP201 shell.
    MCU commands:
      help  ver  info  echo  mr  mw  hist  reset
      record [ms]   batch record, default 1000 ms, max 1960 ms
      stream [ms]   real-time stream, default 1000 ms, no size limit
      pdm start|stop|status|record [ms]|stream [ms]
""")


def handle_host_cmd(token: str, args: list[str], ser: serial.Serial,
                    port: str, baud: int) -> tuple[serial.Serial, str, int, bool]:
    match token:
        case "help":
            print(HELP_TEXT)
        case "ports":
            list_ports()
        case "port":
            if not args:
                print("[error] usage: !port <COM_PORT>")
            else:
                new_port = args[0]
                ser.close()
                print(f"Switching to {new_port} @ {baud}\u2026")
                ser = open_port(new_port, baud)
                if wait_for_prompt(ser):
                    print(f"Connected to {new_port}.")
                    port = new_port
                else:
                    print("[warn] no prompt received.")
        case "baud":
            if not args:
                print("[error] usage: !baud <RATE>")
            else:
                new_baud = int(args[0])
                ser.close()
                print(f"Switching to {port} @ {new_baud}\u2026")
                ser = open_port(port, new_baud)
                if wait_for_prompt(ser):
                    print(f"Connected at {new_baud}.")
                    baud = new_baud
                else:
                    print("[warn] no prompt received.")
        case "record":
            if not args:
                print("[error] usage: !record <duration_ms> [output.wav]")
            else:
                dur = int(args[0])
                out = args[1] if len(args) > 1 else None
                do_record(ser, dur, out)
        case "stream":
            if not args:
                print("[error] usage: !stream <duration_ms> [output.wav]")
            else:
                dur = int(args[0])
                out = args[1] if len(args) > 1 else None
                do_stream(ser, dur, out)
        case "reset":
            print(send_cmd(ser, "reset"))
        case "exit" | "quit":
            return ser, port, baud, True
        case _:
            print(f"[error] unknown host command: !{token}  (try !help)")

    return ser, port, baud, False


# ── main loop ───────────────────────────────────────────────────────────────

def auto_detect_port() -> str | None:
    ports = serial.tools.list_ports.comports()
    for p in sorted(ports):
        desc = p.description.lower()
        if "usb" in desc or "uart" in desc or "serial" in desc:
            return p.device
    if ports:
        return sorted(ports)[0].device
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Trina-Pi-UP201 interactive shell client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("port", nargs="?", default=None,
                        help="COM port (default: auto-detect)")
    parser.add_argument("baud", nargs="?", type=int, default=DEFAULT_BAUD,
                        help=f"Baud rate (default: {DEFAULT_BAUD})")
    parser.add_argument("--list", action="store_true",
                        help="List available COM ports and exit")
    parser.add_argument("--run", metavar="CMD", action="append", default=[],
                        help="Run a MCU command non-interactively (repeatable)")
    parser.add_argument("--record", metavar="MS", type=int, default=None,
                        help="Batch record MS ms to SRAM then save WAV (max 1960)")
    parser.add_argument("--stream", metavar="MS", type=int, default=None,
                        help="Stream audio in real-time for MS ms, save WAV (no size limit)")
    parser.add_argument("--out", metavar="FILE", default=None,
                        help="Output WAV filename (used with --record or --stream)")
    cfg = parser.parse_args()

    if cfg.list:
        list_ports()
        return

    port = cfg.port or auto_detect_port()
    if port is None:
        print("ERROR: no COM port found.", file=sys.stderr)
        sys.exit(1)
    if cfg.port is None:
        print(f"Auto-detected port: {port}")

    print(f"Connecting to Trina-Pi-UP201 on {port} @ {cfg.baud}\u2026")
    ser = open_port(port, cfg.baud)

    alive = wait_for_prompt(ser)
    if not alive:
        alive = reset_and_wait(ser)
    if not alive:
        alive = wait_for_prompt(ser)

    if not alive:
        print("[warn] no prompt from device.")
        if cfg.run or cfg.record or cfg.stream:
            print("ERROR: cannot run without a prompt.", file=sys.stderr)
            ser.close()
            sys.exit(1)
        print("       Continuing anyway. Press Enter to retry.\n")
    else:
        if not cfg.run and not cfg.record and not cfg.stream:
            print(f"Connected.  Type !help for host commands, !exit to quit.\n")

    # ── non-interactive --run batch ──────────────────────────────────────
    if cfg.run:
        for cmd in cfg.run:
            print(f"$ {cmd}")
            print(send_cmd(ser, cmd))
            print()
        if not cfg.record:
            ser.close()
            return

    # ── non-interactive --record ─────────────────────────────────────────
    if cfg.record:
        do_record(ser, cfg.record, cfg.out)
        ser.close()
        return

    # ── non-interactive --stream ─────────────────────────────────────────
    if cfg.stream:
        do_stream(ser, cfg.stream, cfg.out)
        ser.close()
        return

    # ── interactive session ──────────────────────────────────────────────
    port, baud = port, cfg.baud
    try:
        while True:
            try:
                line = input(HOST_PROMPT).strip()
            except EOFError:
                print()
                break

            if not line:
                continue

            if line.startswith("!"):
                parts = line[1:].split()
                token = parts[0].lower() if parts else ""
                ser, port, baud, should_exit = handle_host_cmd(
                    token, parts[1:], ser, port, baud
                )
                if should_exit:
                    break
                continue

            response = send_cmd(ser, line)
            if response:
                print(response)

    except KeyboardInterrupt:
        print()
    finally:
        ser.close()
        print("Disconnected.")


if __name__ == "__main__":
    main()
