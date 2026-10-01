"""Resolve a server command the way the user's shell would, before Popen.

On Windows, CreateProcess looks for a bare program name in the directory of
the running interpreter's image before it consults PATH. Inside a venv that
image is the base interpreter, so a bare `python` would start the base
interpreter instead of the venv's. Resolving the name against the PATH the
server will receive restores shell behaviour. Elsewhere Popen already
searches PATH, so the command is returned unchanged.
"""
import os
import shutil

PATH_SEPARATORS = ("/", "\\")


def resolve_command(command, env):
    if os.name != "nt" or not command or any(sep in command[0] for sep in PATH_SEPARATORS):
        return command
    found = shutil.which(command[0], path=_path(env))
    # Not found: unchanged, so Popen raises FileNotFoundError exactly as before.
    return [found, *command[1:]] if found else command


def _path(env):
    if env is None:
        return os.environ.get("PATH")
    # Windows environment names are case-insensitive.
    return next((value for key, value in env.items() if key.upper() == "PATH"), None)
