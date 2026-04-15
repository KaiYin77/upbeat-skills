# MCU Shell Interface

Connect to and interact with the Trina-Pi-UP201 RISC-V MCU shell over a COM port UART.

## Usage

```
/mcu [port] [baud]
```

- `port` — COM port, e.g. `COM3` (Windows) or `/dev/ttyUSB0` (Linux). Default: auto-detect
- `baud` — baud rate matching the firmware build. Default: `921600`

## Steps

$ARGUMENTS

Parse `port` and `baud` from the arguments above (both optional).

### Step 1 — discover the port (if not given)

```bash
uv run ~/.claude/commands/mcu/mcu_shell.py --list
```

Ask the user which port to use if there is more than one candidate.

### Step 2 — connect and run commands

```bash
# Interactive session
uv run ~/.claude/commands/mcu/mcu_shell.py [PORT] [BAUD]

# One-shot queries
uv run ~/.claude/commands/mcu/mcu_shell.py --run ver --run info

# Batch record (max 1960 ms, stores to SRAM then transmits)
uv run ~/.claude/commands/mcu/mcu_shell.py --record 1960
uv run ~/.claude/commands/mcu/mcu_shell.py --record 1000 --out clip.wav

# Real-time stream (no size limit)
uv run ~/.claude/commands/mcu/mcu_shell.py --stream 5000
uv run ~/.claude/commands/mcu/mcu_shell.py --stream 10000 --out long.wav
```

`uv` installs `pyserial` automatically — no manual pip or venv needed.

---

## Host commands (inside the session, prefix `!`)

| Command | Description |
|---------|-------------|
| `!help` | Show host command list |
| `!ports` | List available COM ports |
| `!port <PORT>` | Switch to a different COM port |
| `!baud <RATE>` | Reconnect at a different baud rate |
| `!record <ms> [file.wav]` | Batch record to SRAM then save WAV (max 1960 ms) |
| `!stream <ms> [file.wav]` | Stream audio in real-time, save WAV (no size limit) |
| `!reset` | Reset the MCU |
| `!exit` | Disconnect and quit |

---

## MCU shell commands

| Command | Description |
|---------|-------------|
| `help` | List all commands |
| `ver` | Firmware version + build date |
| `info` | Board type, baud rate, boot cause |
| `echo <text>` | Echo text back |
| `mr <addr> [n]` | Read *n* 32-bit words from hex address |
| `mw <addr> <val>` | Write a 32-bit word to hex address |
| `hist` | Show last 4 commands |
| `record [ms]` | Batch record to SRAM, default 1000 ms, max 1960 ms |
| `stream [ms]` | Real-time stream to host, default 1000 ms, no size limit |
| `pdm start` | Start continuous PDM capture |
| `pdm stop` | Stop PDM capture |
| `pdm status` | Show PDM config, buffer addresses, DMA flags |
| `pdm record [ms]` | Same as `record` |
| `pdm stream [ms]` | Same as `stream` |
| `pet` | Start OpenClaw digital pet continuous audio stream |
| `reset` | Software reset the device |

---

## `record` vs `stream`

| | `record` | `stream` |
|---|---|---|
| Max duration | 1960 ms (SRAM limit) | Unlimited |
| Data flow | Capture all → transmit after | Transmit each 10 ms block live |
| SRAM used | Up to 125 KB | Only 2 × 1280 B (ping-pong) |
| Best for | Short reliable clips | Long recordings, live monitoring |

### Audio format
- Sample rate: 16 000 Hz
- Channels: stereo (2)
- Bit depth: 16-bit PCM
- Output: standard WAV file, saved to `recordings/`

### Wire protocol — `record`
```
REC_START <bytes> <sr> <ch> <bits>\r\n
<raw little-endian PCM bytes>
\r\nREC_END\r\n
mcu>
```

### Wire protocol — `stream`
```
STREAM_START <n_blocks> <sr> <ch> <bits> <block_bytes>\r\n
<n_blocks × block_bytes raw PCM bytes>
\r\nSTREAM_END\r\n
mcu>
```

### Wire protocol — `pet`
```
PET_START <sr> <ch> <bits> <block_bytes>\r\n
<block_bytes raw PCM bytes>   ← repeated indefinitely
<block_bytes raw PCM bytes>
...
\r\nPET_STOP\r\n
mcu>
```

Host sends `'q'` or `0x03` (Ctrl-C) to stop the stream.
Unlike `stream`, no block count is sent upfront — data flows until the host stops it.

---

## OpenClaw digital pet

The pet mode turns the PDM microphone into a live emotion sensor.
Physical interactions near the board are captured and translated into pet feelings.

```bash
uv run ~/.claude/commands/mcu/openclaw_pet.py [PORT] [BAUD]
```

### Signal → emotion mapping

| Interaction | Audio signature | Pet emotion |
|---|---|---|
| **Call / speak** | Voiced (ZCR > 0.12), RMS > 3000 | `alert` → `happy` |
| **Gentle pat** | Low crest factor, RMS 1200–3000 | `purring` |
| **Slap / impact** | Peak > 18000, crest > 7 | `hurt` / `scared` |
| **Shout / loud** | RMS > 9000 | `excited` |
| **Silence ~6 s** | RMS < 300 | `sleeping` |

### Running the pet

```bash
# Auto-detect port
uv run ~/.claude/commands/mcu/openclaw_pet.py

# Explicit port
uv run ~/.claude/commands/mcu/openclaw_pet.py COM15

# Press Ctrl-C to stop — cleanly sends 'q' to device and waits for PET_STOP
```

`uv` installs `pyserial` and `numpy` automatically.

---

## Audio / AI workflow

When asked to check for noise, record a voice sample, or run audio analysis:

1. Call `do_record(ser, ms)` or `do_stream(ser, ms)` from `~/.claude/commands/mcu/mcu_shell.py`
2. The returned WAV is 16 kHz stereo 16-bit — compatible with any audio ML library
3. Pass to `librosa`, `soundfile`, `silero-VAD`, `webrtcvad`, `whisper`, etc.

```bash
# Capture then analyse
uv run ~/.claude/commands/mcu/mcu_shell.py --stream 3000 --out /tmp/sample.wav
# → analyse /tmp/sample.wav with AI model
```

---

## Troubleshooting

- **No prompt after connect**: board still booting — press Enter or power-cycle
- **Garbled output**: baud mismatch — confirm `SERIAL_BAUD` in CMakePresets
- **Port in use**: close TeraTerm / PuTTY / miniterm before running
- **uv not found**: install from `https://docs.astral.sh/uv/`
- **Record returns no data**: check PDM wiring — CLK → OSPI_CSB1 pin, DATA → LCD_RESETB pin
- **Stream dropouts**: UART buffer overflow — reduce duration or check USB-serial adapter
- **Board resets on every connect**: `mcu_shell.py` opens the port with `dsrdtr=False` to prevent DTR toggling from resetting a running board; it checks for a live `mcu>` prompt first and only falls back to a DTR reset if the board is unresponsive
