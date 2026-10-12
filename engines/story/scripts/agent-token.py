#!/usr/bin/env python3
"""Create (or rotate) the story worker agent's bearer token; never prints it.

    python3 scripts/agent-token.py                       # create ~/.config/studiozero/agent-token (0600) if missing
    python3 scripts/agent-token.py --rotate              # new token (restart the agent, then send it to the Pi again)
    python3 scripts/agent-token.py --send-to-pi --url https://<laptop>.<tailnet>.ts.net --addr 100.x.y.z [--pi scalar-pi]
        pipes the token over ssh into publisher/deploy/studio-worker.sh on the Pi (root-only there; never in git)

STUDIO_AGENT_TOKEN_FILE overrides the path (the agent reads the same variable).
"""
import argparse
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import sys

PATH = Path(os.getenv("STUDIO_AGENT_TOKEN_FILE") or Path.home() / ".config/studiozero/agent-token")
PI_SCRIPT = "/opt/scalar-social/repo/publisher/deploy/studio-worker.sh"


def write_token(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(secrets.token_urlsafe(36))
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rotate", action="store_true")
    parser.add_argument("--send-to-pi", action="store_true")
    parser.add_argument("--url", default="")
    parser.add_argument("--addr", default="")
    parser.add_argument("--pi", default=os.getenv("SCALAR_PI", "scalar-pi"))
    args = parser.parse_args(argv)
    if args.rotate or not PATH.exists():
        write_token(PATH)
        print(f"Token written to {PATH} (0600). Restart the agent to use it.")
    elif PATH.stat().st_mode & 0o077:
        os.chmod(PATH, 0o600)
        print(f"Tightened {PATH} to 0600.")
    else:
        print(f"Token exists: {PATH} (0600).")
    if args.send_to_pi:
        if not args.url or not args.addr:
            parser.error("--send-to-pi needs --url and --addr")
        with open(PATH, "rb") as token:
            result = subprocess.run(["ssh", "-o", "BatchMode=yes", args.pi, f"sudo {PI_SCRIPT} --url {shlex.quote(args.url)} --addr {shlex.quote(args.addr)}"],
                                    stdin=token, capture_output=True, text=True)
        print((result.stdout or result.stderr).strip())
        return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
