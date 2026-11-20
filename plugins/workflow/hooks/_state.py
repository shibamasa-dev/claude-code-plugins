"""Where this plugin's hooks keep state (the "Where plugins write" rule in the repo's CLAUDE.md).

state_dir(feature) resolves, in order:
  1. the feature's env override, when the caller names one and it is set (no migration then)
  2. $CLAUDE_PLUGIN_DATA/<feature>
  3. ~/.claude/state/workflow/<feature>            (the variable is unset or not this plugin's: a script run from Bash)

CLAUDE_PLUGIN_DATA is exported to hook processes but not to commands Claude runs through Bash, so a command a hook
prints for Claude to run is built with cli(), which puts the value in front of it. Bash can still carry another
plugin's value (seen: one plugin's data directory leaking into every Bash call), so the variable is used only when it
names this plugin's directory: Claude Code names it after the plugin identifier, `<plugin>-<marketplace>` or
`<plugin>-inline`.

legacy=<dir> migrates once: when the resolved directory does not exist yet and <dir> has files, <dir> is copied to a
temp name next to it and renamed into place. The old directory stays as the backup. "Does not exist" rather than
"is empty", so a directory emptied later (every entry consumed, every file garbage-collected) never pulls the old
copy back. Failures are swallowed: the hook then starts with an empty directory, as it would on a fresh install.
"""
import os
import shlex
import shutil

PLUGIN = "workflow"
LEGACY_ROOT = os.path.join("~", ".claude", "state")


def state_dir(feature, override_env=None, legacy=None):
    if override_env and os.environ.get(override_env):
        return os.path.expanduser(os.environ[override_env])
    data = plugin_data()
    d = os.path.join(data, feature) if data else os.path.expanduser(os.path.join(LEGACY_ROOT, PLUGIN, feature))
    if legacy:
        migrate(os.path.expanduser(os.path.join(LEGACY_ROOT, legacy)), d)
    return d


def plugin_data():
    """$CLAUDE_PLUGIN_DATA when it is this plugin's directory, else None."""
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not data:
        return None
    name = os.path.basename(os.path.normpath(data))
    return data if name == PLUGIN or name.startswith(PLUGIN + "-") else None


def migrate(old, new):
    """Copy old to new once (see the module docstring). Returns True when this call made the copy."""
    if os.path.lexists(new) or not os.path.isdir(old):
        return False
    tmp = f"{new}.migrating-{os.getpid()}"
    try:
        if not os.listdir(old):
            return False
        os.makedirs(os.path.dirname(new), exist_ok=True)
        shutil.copytree(old, tmp, symlinks=True, ignore=shutil.ignore_patterns("*.lock", "*.tmp"))
        os.rename(tmp, new)  # fails when another process got there first; its copy is the same data
        return True
    except OSError:
        shutil.rmtree(tmp, ignore_errors=True)
        return False


def cli(path):
    """How a hook message tells Claude to run the script at path, carrying CLAUDE_PLUGIN_DATA into the Bash call."""
    cmd = f'python3 "{os.path.abspath(path)}"'
    data = plugin_data()
    return f"CLAUDE_PLUGIN_DATA={shlex.quote(data)} {cmd}" if data else cmd
