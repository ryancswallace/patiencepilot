# Command Line

Install the command line entry point with the optional extra:

```bash
uv tool install "patiencepilot[cli]"
```

The first CLI is intentionally small and file oriented. It uses saved session
JSON for persistence and canonical state notation for entering a visible or
reconstructed game state.

Deal and save a reproducible game:

```bash
patiencepilot new --seed 7 --draw-count 3 --save game.json
```

List legal move IDs from a saved session:

```bash
patiencepilot moves --load game.json
```

Apply a move and update the saved session:

```bash
patiencepilot apply --load game.json --save game.json DRAW
```

Undo the latest saved move:

```bash
patiencepilot undo --load game.json --save game.json
```

Read canonical state notation from a file or standard input:

```bash
patiencepilot validate --state state.txt
patiencepilot moves --state -
```

An `advice` command is present at the UI boundary. It accepts search limits and
delegates to the configured advice provider once one is available.
