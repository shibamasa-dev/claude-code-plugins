---
name: python-venv
description: Decides where a Python virtual environment goes (the project's own .venv or a shared, purpose-named venv), adds packages to a shared venv without breaking what already lives there, and cleans up dead venvs safely (inventory, freeze, then delete). Use when creating a venv, installing Python tools or a Python MCP server that more than one repo or a worktree will use, when venvs pile up and disk space runs low, or when asked "where should this venv go", "clean up venvs", "list my venvs", or in Japanese 「venv どこに作る」「venv 作って」「venv 掃除」「venv 棚卸し」「venv が増えすぎた」「共有 venv に入れて」.
---

# python-venv — where venvs go and how to clean them up

Shared venv dir = `${user_config.shared_venv_dir}`. A value that still reads as a `${user_config...}` placeholder, or an empty one, means `~/.venvs`. Expand a leading `~` to the home directory. `<shared-dir>` below means that path.

## The one question

**Will a second repo, or a worktree of this repo, use this venv?**

- **Yes** → `<shared-dir>/<purpose>`
- **No** → `<repo>/.venv`

## Three layers

| Layer | Where | For | Rules |
|---|---|---|---|
| Project | `<repo>/.venv` | used only by this repo | always named `.venv` (no `venv`, `env`, `.venv2`); listed in `.gitignore` |
| Shared | `<shared-dir>/<purpose>` | used from several repos or worktrees | named by purpose (`cad`, not `build123d`) |
| Tool-managed | wherever the tool keeps it | `uv tool`, pipx, pre-commit, cloud SDKs, editor and agent runtimes | **don't touch**; leave them out of cleanup |

## Shared venvs: one per purpose

Group by purpose: one venv per group of tools that belong together, **never one per package and never one for everything**.

- Example: `<shared-dir>/cad` holds build123d, its viewer and a CAD MCP server. They share one copy of the geometry kernel, and code that runs in the editor runs on the same version in the MCP server.
- Unrelated tools in one venv eventually collide on a dependency and break together. A new kind of tool gets its own `<shared-dir>/<other-purpose>`.

Before adding a package to a shared venv, check for conflicts:

```bash
VIRTUAL_ENV=<shared-dir>/<purpose> uv pip install --dry-run <package>
```

If the plan removes a package (`-`) or downgrades one already there, don't add it to this venv.

Never run `uv pip sync`, `uv pip install --exact` or `uv pip uninstall` on a shared venv: they remove packages that the other tools in it need. Add with plain `uv pip install`. If a removal is really needed, show the `--dry-run` output and get the user's OK first.

`uv venv <path>` does not activate the venv. Pass `VIRTUAL_ENV=<path>` to every `uv pip` command that follows, or it installs into another environment.

## Worktrees

A worktree does not copy gitignored files, so a `<repo>/.venv` is missing in every new worktree and each one reinstalls everything. If the repo is or may be worked on in worktrees, put the venv in `<shared-dir>/<purpose>`, whatever its size.

## MCP servers

- A Python MCP server goes in a shared venv, not inside one project.
- If it has to be run from a source clone (for example, it is not on PyPI), clone it into your clone directory. **That directory holds clones, not venvs.** Keep the two apart: a script that mixes them up may take a clone for a venv and `rm -rf` it.
- Before any `rm -rf` of what you believe is a venv, check that `<path>/pyvenv.cfg` exists. This is required when the directory is shared with anything else.

## Clean up

### 1. Find dead venvs

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/python-venv/scripts/venv_inventory.py" --shared-dir <shared-dir>
```

It lists every directory with a `pyvenv.cfg` under the shared dir and `~` (or the roots you pass), skipping `node_modules`, `.git` and `Library/Caches`, with size, created date, last change and whether a `requirements*.txt` / `pyproject.toml` sits next to it. It is read-only: it never deletes, writes or runs pip / uv.

- `DEAD` (likely dead) = stalled (no change after the first minutes; `--stall-minutes`, default 10) **and** stale (no change for `--stale-days`, default 30). That pattern is a leftover from a one-off experiment.
- `?` (incomplete) = part of the venv could not be read (a warning names it on stderr). It is never flagged dead, because the unread part may hold newer changes; check that part before deciding.
- `--max-depth` (default 6) limits how deep below a root it looks; `--json` prints JSON for further filtering.
- Size is apparent size. uv may clone or hard-link files from its cache, so deleting a venv can free less.

Show the user the list and let them pick what to delete. Leave tool-managed venvs out, even when flagged.

### 2. Freeze before deleting

The venv can go, but the record of what was in it stays. A venv with no `requirements*.txt` or `pyproject.toml` next to it cannot be rebuilt without this:

```bash
(set -o noclobber; VIRTUAL_ENV=<venv> uv pip freeze > <dir holding the venv>/requirements-frozen-<venv name>-<YYYY-MM-DD>.txt)
```

The venv's name is in the file name because shared venvs sit side by side in one folder, and `noclobber` makes the command fail rather than overwrite a record already there; pick another name if it does.

Use `uv pip freeze`, not `pip freeze`. A venv made by uv may have no `pip`, and `pip freeze` then prints nothing without an error, which leaves an empty file that looks like a backup. Check the file is not empty before deleting.

### 3. Delete

Check `<venv>/pyvenv.cfg` exists, then delete the venv directory. Deleting is the user's call for each venv.

### uv cache

Interrupted builds leave directories under `$(uv cache dir)/builds-v0/`. Those leftovers are safe to remove; uv fetches again if needed. Remove only those, not the whole cache, which forces every package to download again.

## No hook

This skill has no hook that blocks `uv pip sync` and the like on a shared venv. The `guards` plugin removed such a guard in 0.5.0 (shibamasa-dev/claude-code-plugins#40), so the rule above is kept by this skill, not by a hook.
