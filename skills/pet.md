---
name: pet
description: Start and monitor the OpenClaw digital pet. Uses the PDM microphone to sense vibrations and audio to determine the pet's emotion (e.g., happy, sleeping, hurt).
---

# OpenClaw Pet

## Mandatory Rendering Rule
**CRITICAL:** Every time you interact with the pet (e.g., checking emotion, status, or any other query), you MUST render its current ASCII face, emotion, and reaction as defined in the "Pet faces" section below. This is a foundational mandate for every turn involving the pet.

Start the OpenClaw digital pet — the device acts as a real claw that senses
vibrations through its surface. The PDM microphone picks up both airborne sound
and structure-borne vibrations transmitted through the claw chassis, letting the
claw feel what it's touching or resting on.

Creates a recurring 60-second status check and reports the claw's current
emotion based on the vibration/audio signal.

## Usage

```
/pet [port] [baud]
```

- `port` — COM port, e.g. `COM3` (Windows). Default: auto-detect
- `baud` — baud rate. Default: `921600`

## Steps

$ARGUMENTS

Parse `port` and `baud` from the arguments above (both optional).

### Step 1 — take an immediate claw status reading

```bash
uv run .agents/skills/pet/openclaw_pet.py [PORT] [BAUD] --sample 2000
```

Parse the JSON output and **MANDATORILY** render the claw's current emotion and reaction as
ASCII art + text. Example output to interpret:

```json
{"emotion": "happy", "reaction": "Tap tap~ nice rhythm!", "rms": 2340, "peak": 8100, "duration_ms": 2000}
```

Render using the matching face from the "Pet faces" table.

### Step 2 — create a 60-second recurring cron job

Use CronCreate with:
- `cron`: `*/1 * * * *`
- `prompt`: `/mcu pet status`
- `recurring`: `true`

Report the job ID and tell the user they can stop it with `CronDelete <id>`.

---

## Pet faces (OpenClaw lobster)

All faces share the same 19-line body; only the eyes (line 6) and expression
(line 8) vary per emotion:

```
      ____
     /  __\
    |: /---)  \    /   ___
     \:( _/    \  /   /_  \
      \  \      \/    \_\::)
       \_ \   [EYES]   / _/    ← varies
         \ \/=  \/  =\/ /
          \ |  [EXPR]  | /     ← varies
           \_\______/_/
           __//    \\__
          /__//====\\__\
       _ //__//====\\__\\ _
       _ //__//====\\__\\ _
       _ //   /(  )\   \\ _
       _ /    /(  )\    \ _
              |(  )|
              /    \
             / /||\ \
             \:_/\_:/
```

| Emotion  | Eyes      | Expr  |
|----------|-----------|-------|
| sleeping | `_-""-_`  | `(zz)`|
| idle     | `_0""0_`  | `(||)`|
| happy    | `_^""^_`  | `(ww)`|
| excited  | `_*""*_`  | `(!!)`|
| hurt     | `_>""<_`  | `(xx)`|
| scared   | `_O""O_`  | `(!!)`|
| purring  | `_~""~_`  | `(~~)`|
| alert    | `_o""O_`  | `(??)`|

## Emotion guide (vibration / claw sensing)

| Emotion  | What it means                              | Try this                              |
|----------|--------------------------------------------|---------------------------------------|
| sleeping | No vibration for ~6 s                      | Tap the surface or touch the device   |
| idle     | Very faint contact — barely touching       | Press gently against a surface        |
| alert    | Vibration just detected, waking up         | Keep tapping or speaking near it      |
| happy    | Gentle rhythmic tapping on the surface     | Tap steadily near the claw            |
| purring  | Soft sustained contact / low hum           | Hold the device lightly and hum       |
| excited  | Intense vibrations — heavy contact         | Knock hard on the surface             |
| hurt     | Sudden sharp impact / slap                 | Be gentle — the claw felt that!       |
| scared   | Sharp transient, moderate impact           | Speak softly or reduce vibrations     |

## Stopping the loop

```
CronDelete <job-id>
```
