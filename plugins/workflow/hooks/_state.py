"""Where this plugin's hooks keep state (the "Where plugins write" rule in the repo's CLAUDE.md).

state_dir(feature) resolves, in order:
  1. the feature's env override, when the caller names one and it is set (no migration then)
  2. $CLAUDE_PLUGIN_DATA/<feature>
  3. ~/.claude/state/workflow/<feature>            (the variable is unset or not this plugin's: a script run from Bash)

CLAUDE_PLUGIN_DATA is exported to hook processes but not to commands Claude runs through Bash, so a command a hook
prints for Claude to run is built with command_for(), which puts the value in front of it. Bash can still carry another
plugin's value (seen: one plugin's data directory leaking into every Bash call), so the variable is used only when it
names this plugin's directory: Claude Code names it after the plugin identifier, `<plugin>-<marketplace>` or
`<plugin>-inline`. A CLI that ends up on the fallback says so on stderr (warn_fallback()).

legacy=<dir> migrates once: when the resolved directory does not exist yet and <dir> has files, <dir> is copied to a
temp name next to it and renamed into place. The old directory stays as the backup. "Does not exist" rather than
"is empty", so a directory emptied later (every entry consumed, every file garbage-collected) never pulls the old
copy back. When the copy fails, state_dir() returns the old directory for that run, so nothing is written to the new
place and the next run tries again.
"""
import os
import shlex
import shutil
import sys

PLUGIN = "workflow"
LEGACY_ROOT = os.path.join("~", ".claude", "state")


def state_dir(feature, override_env=None, legacy=None):
    if override_env and os.environ.get(override_env):
        return os.path.expanduser(os.environ[override_env])
    data = plugin_data()
    d = os.path.join(data, feature) if data else os.path.expanduser(os.path.join(LEGACY_ROOT, PLUGIN, feature))
    if legacy:
        old = os.path.expanduser(os.path.join(LEGACY_ROOT, legacy))
        if migrate(old, d) == "failed":
            return old  # keep using the old place this run, so nothing is written to a half-empty new one
    return d


def plugin_data():
    """$CLAUDE_PLUGIN_DATA when it is this plugin's directory, else None."""
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not data:
        return None
    name = os.path.basename(os.path.normpath(data))
    return data if name == PLUGIN or name.startswith(PLUGIN + "-") else None


def migrate(old, new):
    """Copy old to new once (see the module docstring). Returns "copied", "none" (nothing to do) or "failed"."""
    if os.path.lexists(new) or not os.path.isdir(old):
        return "none"
    tmp = f"{new}.migrating-{os.getpid()}"
    try:
        if not os.listdir(old):
            return "none"
        os.makedirs(os.path.dirname(new), exist_ok=True)
        shutil.copytree(old, tmp, symlinks=True, ignore=shutil.ignore_patterns("*.lock", "*.tmp"))
        if os.path.lexists(new):  # another process finished first (rename would replace an emptied directory)
            shutil.rmtree(tmp, ignore_errors=True)
            return "none"
        os.rename(tmp, new)
        return "copied"
    except OSError:
        shutil.rmtree(tmp, ignore_errors=True)
        return "none" if os.path.lexists(new) else "failed"


def warn_fallback(path, override_env=None):
    """For a script run as a CLI (never as a hook): say on stderr when it is using the fallback directory, which is not
    where the hooks keep their state (the variable is unset, another plugin's, or a placeholder that was not
    substituted). Silent when an env override is set: then the user chose the directory."""
    if (override_env and os.environ.get(override_env)) or plugin_data():
        return
    print(f"[{PLUGIN}] Using {path}: CLAUDE_PLUGIN_DATA is unset or not this plugin's, so this is not where the hooks "
          "keep their state. Run the command as the hook or skill prints it, with its CLAUDE_PLUGIN_DATA=... prefix.",
          file=sys.stderr)


def command_for(path):
    """How a hook message tells Claude to run the script at path, carrying CLAUDE_PLUGIN_DATA into the Bash call."""
    cmd = f'python3 "{os.path.abspath(path)}"'
    data = plugin_data()
    return f"CLAUDE_PLUGIN_DATA={shlex.quote(data)} {cmd}" if data else cmd
