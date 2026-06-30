# Terminal User Interface

Install the Textual terminal interface with the optional extra:

```bash
uv tool install "patiencepilot[tui]"
```

Launch a playable Klondike session:

```bash
patiencepilot-tui
```

Start from a reproducible deal:

```bash
patiencepilot-tui --seed 7 --draw-count 3
```

Save and load a session JSON payload:

```bash
patiencepilot-tui --save game.json
patiencepilot-tui --load game.json --save game.json
```

The interface shows the current board, legal move IDs, recent history, and the
latest move effects. Hidden tableau cards are rendered as `##`, so the TUI does
not reveal unseen card identities.

Useful controls:

* Type a canonical move ID such as `DRAW`, `W->F`, `W->T3`, `T0->F`, or
    `T0->T3:2`, then press Enter or select Apply.
* Press `d` or select Draw to draw from stock, or recycle waste when that is the
    legal stock action.
* Press `u` and `r` for undo and redo.
* Press `n` to start a new game with the launch options.
* Press `s` to save when launched with `--save PATH`.
* Select Load to load from `--load PATH`, or from `--save PATH` when no load path
    was supplied.
* Select Advice to ask the configured advice provider. Until a solver is wired
    into the app service, the TUI reports that no advice provider is configured.
