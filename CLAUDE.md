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
- **Commit and push when a change is ready.** The user's desktop shortcut updates from GitHub, so changes
  only reach them once pushed. Test first (against a pretend OBS when real OBS isn't available), then
  commit and push to `main` without waiting for approval, and summarize what changed.

## Context

- The six layouts in `build_scenes.py` are a starting point. The templates are still being designed,
  so expect them to change; keep layout code easy to edit rather than baking in assumptions.

## Next up

See `TODO.md`. Test against real OBS first, then the per-episode recording split hotkey.
