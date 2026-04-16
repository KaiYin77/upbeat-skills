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
uv run "$(find .claude/commands/pet .agents/skills/pet -name 'openclaw_pet.py' 2>/dev/null | head -1)" [PORT] [BAUD] --sample 2000
```

Parse the JSON output and **MANDATORILY** render the claw's current emotion and reaction as
ASCII art + text. Example output to interpret:

```json
{"emotion": "happy", "reaction": "好節奏~ :3", "rms": 2340, "peak": 8100, "duration_ms": 2000}
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

| Emotion  | Eyes      | Expr   | Label (STATE_ZH) |
|----------|-----------|--------|------------------|
| sleeping | `_-""-_`  | `(zz)` | 沉睡中           |
| happy    | `_^""^_`  | `(ww)` | 開心             |
| excited  | `_*""*_`  | `(!!)` | 興奮             |
| hurt     | `_>""<_`  | `(xx)` | 受傷             |
| purring  | `_~""~_`  | `(~~)` | 滿足             |

## Reactions (Traditional Chinese)

Reaction messages are displayed in Traditional Chinese. One of the following is picked at random per emotion change:

| Emotion  | Reactions                                                          |
|----------|--------------------------------------------------------------------|
| sleeping | 沒有振動... / ...爪子休息中... / *靜止如石*                        |
| happy    | 敲敲~ 真好！ / 好節奏~ :3 / 我感覺到了~                           |
| excited  | 強烈震動！！！ / 劇烈接觸！！！ / 哇！好激烈！！！                |
| hurt     | 好痛！衝擊太大！ / 那一下是打過來的！ / >.< 太重了！              |
| purring  | 呼嚕嚕~ 穩穩的~ / 好舒服的接觸~ / *順滑的振動*                   |

## Emotion guide (vibration / claw sensing)

| Emotion  | What it means                                    | How to trigger                               | Baseline recording      |
|----------|--------------------------------------------------|----------------------------------------------|-------------------------|
| sleeping | No vibration for ~6 s                            | Leave the device still                       | `quiet_baseline.wav`    |
| happy    | Rhythmic tapping — intermittent transient spikes | Tap the surface repeatedly (敲擊)            | `tapping_baseline.wav`  |
| purring  | Sustained friction — high zero-crossing rate     | Rub the surface vigorously (摩擦 / 搖晃)     | `rubbing_baseline.wav`  |
| excited  | Heavy sustained vibration — saturating RMS       | Shake the device hard (搖晃)                 | `shaking_baseline.wav`  |
| hurt     | Sudden hard impact from near-silence             | Slap the surface hard                        | `hurt_baseline.wav`     |

### Signal → emotion mapping (measured on Trina-Pi-UP201)

| Interaction | Audio signature | Threshold | Emotion |
|---|---|---|---|
| **Silence** | RMS < noise floor | RMS < THR_SILENCE | `sleeping` |
| **Tap / knock** | Intermittent spike, crest ≥ 1.5, ZCR ≈ 0 | RMS ≥ THR_GENTLE | `happy` |
| **Gentle contact** | Low RMS, crest < 1.5, ZCR ≈ 0 | RMS ≥ THR_GENTLE | `purring` |
| **Rub / friction** | Sustained high ZCR ≥ 0.15 | RMS ≥ THR_GENTLE | `purring` |
| **Shake** | Very high RMS, ZCR < 0.15 | RMS ≥ THR_LOUD | `excited` |
| **Slap / impact** | Peak ≥ THR_SLAP, inst. RMS ≥ THR_SLAP×0.5, smoothed RMS < THR_LOUD | `hurt` |

> **Calibration note:** At startup the pet measures 1 s of ambient noise.
> If the device noise floor is high (measured ~5000 RMS on UP201), thresholds are
> scaled up proportionally and capped at safe values so all emotions remain reachable.

## Stopping the loop

```
CronDelete <job-id>
```
