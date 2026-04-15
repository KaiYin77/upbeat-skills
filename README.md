# upbeat-skills

Claude Code skills for Upbeat / Trina-Pi hardware.

## Available skills

| Skill | Description |
|-------|-------------|
| `/mcu` | Connect to and interact with the Trina-Pi-UP201 RISC-V MCU shell over UART |

## Install

```bash
git clone https://github.com/KaiYin77/upbeat-skills
cd upbeat-skills

# Install all skills globally (available in every repo)
bash install.sh

# Install a single skill globally
bash install.sh mcu

# Install into the current project only
bash install.sh --project
bash install.sh mcu --project
```

Restart Claude Code after installing.

## Requirements

- [uv](https://docs.astral.sh/uv/) — the `/mcu` skill uses `uv run` to manage Python dependencies automatically. No manual `pip install` needed.

## `/mcu` skill

Connects Claude Code to the Trina-Pi-UP201 shell via UART. Supports:

- Interactive shell session
- One-shot MCU command queries (`ver`, `info`, etc.)
- Batch audio recording (up to 1960 ms, stored in SRAM then transmitted)
- Real-time audio streaming (unlimited duration, ping-pong DMA)
- WAV file export, ready for `librosa` / `whisper` / `silero-VAD` etc.

See [`skills/mcu/mcu.md`](skills/mcu/mcu.md) for full documentation.

## Adding new skills

```
skills/
  <skill-name>/
    <skill-name>.md      # Claude Code command definition
    <companion files>    # tools, configs, etc.
```

Then run `bash install.sh` to install.
