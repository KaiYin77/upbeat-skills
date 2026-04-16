# upbeat-skills

Skills for Upbeat / Trina-Pi hardware. Supports **Claude Code** and **Gemini CLI**.

## Available skills

| Skill | Description |
|-------|-------------|
| `/mcu` | Connect to and interact with the Trina-Pi-UP201 RISC-V MCU shell over UART |
| `/pet` | Start and monitor the OpenClaw digital pet. Uses the PDM microphone to sense vibrations and audio to determine the pet's emotion (e.g., happy, sleeping, hurt). |

## Install

```bash
git clone https://github.com/KaiYin77/upbeat-skills
cd upbeat-skills

# Install all skills to current project for Claude Code (default)
bash install.sh

# Install all skills to current project for Gemini CLI
bash install.sh --agent gemini
```

Restart your agent (Claude Code or Gemini CLI) after installing.

## Requirements

- [uv](https://docs.astral.sh/uv/) — both `/mcu` and `/pet` skills use `uv run` to manage Python dependencies automatically. No manual `pip install` needed.

## `/mcu` skill

Connects your agent to the Trina-Pi-UP201 shell via UART. Supports:

- Interactive shell session
- One-shot MCU command queries (`ver`, `info`, etc.)
- Batch audio recording (up to 1960 ms, stored in SRAM then transmitted)
- Real-time audio streaming (unlimited duration, ping-pong DMA)
- WAV file export, ready for `librosa` / `whisper` / `silero-VAD` etc.

See [`skills/mcu.md`](skills/mcu.md) for full documentation.

## `/pet` skill

Turns the OpenClaw PDM microphone into a live emotion sensor. The pet reacts to touch, speech, and movement.

- **Mandatory Rendering:** Every interaction with the pet *must* display its ASCII face and current state.
- **Emotion Mapping:** Recognizes emotions like `happy`, `purring`, `alert`, `excited`, `hurt`, `scared`, and `sleeping`.
- **Vibration Sensing:** Detects structure-borne vibrations through the claw chassis.

See [`skills/pet.md`](skills/pet.md) for full documentation.

## Adding new skills

```
skills/
  <skill-name>.md      # Claude Code / Gemini CLI skill definition
  <companion files>    # tools, configs, etc.
```

Then run `bash install.sh` to install.
