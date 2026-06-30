# Command Line

Install the command line entry point with the optional extra:

```bash
uv tool install "patiencepilot[cli]"
```

The first CLI is intentionally small and file oriented. It uses saved session
JSON for persistence and canonical state notation for entering a visible or
reconstructed game state.

The long command is `patiencepilot-cli`; the shorter equivalent alias is
`patp-cli`.

Deal and save a reproducible game:

```bash
patiencepilot-cli new --seed 7 --draw-count 3 --save game.json
```

List legal move IDs from a saved session:

```bash
patiencepilot-cli moves --load game.json
```

Apply a move and update the saved session:

```bash
patiencepilot-cli apply --load game.json --save game.json DRAW
```

Undo the latest saved move:

```bash
patiencepilot-cli undo --load game.json --save game.json
```

Read canonical state notation from a file or standard input:

```bash
patiencepilot-cli validate --state state.txt
patiencepilot-cli moves --state -
```

Ask the built-in dummy solver for the next move:

```bash
patiencepilot-cli advice --load game.json
```

Select a registered solver by name or alias and pass search limits:

```bash
patiencepilot-cli advice --load game.json --solver dummy --depth-limit 1
```

The dummy solver is deterministic and recommends the first listed legal move.
The command accepts `--time-limit`, `--node-limit`, and `--depth-limit` so
future solvers can reuse the same interface.
