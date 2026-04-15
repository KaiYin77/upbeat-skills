# OpenClaw Pet

Start the OpenClaw digital pet — creates a recurring 60-second status check and
reports the pet's current emotion from the PDM microphone.

## Usage

```
/pet [port] [baud]
```

- `port` — COM port, e.g. `COM3` (Windows). Default: auto-detect
- `baud` — baud rate. Default: `921600`

## Steps

$ARGUMENTS

Parse `port` and `baud` from the arguments above (both optional).

### Step 1 — take an immediate pet status reading

```bash
uv run ~/.claude/commands/mcu/openclaw_pet.py [PORT] [BAUD] --sample 2000
```

Parse the JSON output and render the pet's current emotion and reaction as
ASCII art + text. Example output to interpret:

```json
{"emotion": "happy", "reaction": "Hehe~ tickles!", "rms": 2340, "peak": 8100, "duration_ms": 2000}
```

Render like this (use the matching face from the table below):

```
  /\_/\
 ( ^.^ )
  (> <)
  [  happy   ]
  > Hehe~ tickles!
```

### Step 2 — create a 60-second recurring cron job

Use CronCreate with:
- `cron`: `*/1 * * * *`
- `prompt`: `/mcu pet status`
- `recurring`: `true`

Report the job ID and tell the user they can stop it with `CronDelete <id>`.

---

## Pet faces

| Emotion   | Face lines                                  |
|-----------|---------------------------------------------|
| sleeping  | `( -.- )` / `> zzZ`                         |
| idle      | `( o.o )` / `> ^ <`                         |
| happy     | `( ^.^ )` / `(> <)`                         |
| excited   | `( *.* )` / `/\| ^ \|\\`                   |
| hurt      | `( >.< )` / `> x <`                         |
| scared    | `( o_O )` / `> ! <`                         |
| purring   | `( ~w~ )` / `>prrr<`                        |
| alert     | `( o.O )` / `> ? <`                         |

## Emotion guide

| Emotion  | What it means                        | Try this                        |
|----------|--------------------------------------|---------------------------------|
| sleeping | Silence for ~6 s                     | Make any sound to wake it       |
| idle     | Very quiet environment               | Speak softly                    |
| alert    | Heard a voice, waking up             | Keep talking                    |
| happy    | Gentle voice or soft touch           | Speak gently or pat near mic    |
| purring  | Soft sustained contact               | Gentle steady sound near mic    |
| excited  | Loud environment                     | Try quieting down               |
| hurt     | Sudden sharp impact / slap           | Be gentle!                      |
| scared   | Sharp transient, moderate impact     | Speak softly to calm it down    |

## Stopping the loop

```
CronDelete <job-id>
```
