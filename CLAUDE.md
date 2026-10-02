# CLAUDE.md

Guidance for Claude Code when working in this repo.

## Start here

- Read `README.md` for the project idea and goals before making changes.
- `TODO.md` is the single list of work still to do, including the roadmap. Check items off there as
  they're done.

## Rules

- **No real names in the repo.** Use "Host 1", "Host 2", "Host 3" in examples, docs, and defaults.
  Real names only go in each person's git-ignored `config.py`.
- **Generic paths in docs.** Write paths as `C:\Users\<you>\source\repos\podcast-deck`, never a real
  username.
- **Target platform is Windows + OBS 28+** (obs-websocket built in). Test changes against the real OBS
  on this PC when possible.
- **Approval before every commit and push.** Show the diff and wait for explicit approval before each
  commit and each push.

## Context

- The six layouts in `build_scenes.py` are a starting point. The templates are still being designed,
  so expect them to change; keep layout code easy to edit rather than baking in assumptions.

## Next up

See `TODO.md`. Test against real OBS first, then the per-episode recording split hotkey.
