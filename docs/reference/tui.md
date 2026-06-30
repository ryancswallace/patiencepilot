# Terminal User Interface

Install the Textual terminal interface with the optional extra:

```bash
uv tool install "patiencepilot[tui]"
```

The long command is `patiencepilot-tui`; the shorter equivalent alias is
`patp-tui`.

Launch a playable Klondike session:

```bash
patiencepilot-tui
```

Start from a reproducible deal:

```bash
patiencepilot-tui --seed 7 --draw-count 3
```

Choose a registered solver and advice search limits:

```bash
patiencepilot-tui --solver dummy --advice-depth-limit 1
```

Save and load a session JSON payload:

```bash
patiencepilot-tui --save game.json
patiencepilot-tui --load game.json --save game.json
```

Mirror a physical-card game instead of starting from an internal deal:

```bash
patiencepilot-tui --real-world --draw-count 3
```

Real-world mode starts with a guided setup wizard for the seven visible tableau
cards. After that, the TUI tracks a player-known view of the game: hidden
tableau and stock cards remain unknown, drawn cards and newly revealed tableau
cards are prompted for immediately, and visible duplicate/impossible cards are
rejected.

The interface shows the current board, legal move IDs, recent history, and the
latest move effects. Hidden tableau cards are rendered as `##`, so the TUI does
not reveal unseen card identities.

Useful controls:

* Type a canonical move ID such as `DRAW`, `W->F`, `W->T3`, `T0->F`, or
    `T0->T3:2`, then press Enter or select Apply.
* Type a displayed legal-move number such as `2` to apply the second listed
    move.
* Press `d` or select Draw to draw from stock, or recycle waste when that is the
    legal stock action.
* Press `u` and `r` for undo and redo.
* Press `n` to start a new game with the launch options.
* Press `s` to save when launched with `--save PATH`.
* Select Load to load from `--load PATH`, or from `--save PATH` when no load path
    was supplied.
* Select Advice to ask the built-in dummy solver for the next move. The dummy
    solver recommends the first listed legal move and fills the move input with
    that move ID.

Advice uses the solver selected with `--solver`. The TUI also accepts
`--advice-time-limit`, `--advice-node-limit`, and `--advice-depth-limit`; the
depth limit defaults to `1` for quick interactive advice.

In real-world mode, Save and Load are currently disabled while persistence for
player-known mirror sessions is still being designed.
