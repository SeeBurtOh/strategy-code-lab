"""Check publishable files and Git history without displaying secret values.

Optionally compare against a private local dotenv file: --compare-env /path/to/.env.
This is a focused release check, not a general-purpose secret detection guarantee.
"""

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = [
    re.compile(rb"sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{30,}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"(?:ghp_|github_pat_)[A-Za-z0-9_]{30,}"),
    re.compile(rb"AKIA[A-Z0-9]{16}"),
    re.compile(
        rb"(?i)(?:api_key|secret_key|access_token)\s*[=:]\s*[\"'][A-Za-z0-9_/-]{16,}[\"']"
    ),
]


def git(*args):
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *args], stderr=subprocess.DEVNULL
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare-env", type=Path)
    args = parser.parse_args()
    known = []
    if args.compare_env:
        from dotenv import dotenv_values

        known = [
            value.encode()
            for name, value in dotenv_values(args.compare_env).items()
            if value
            and len(value) >= 12
            and any(
                word in name.upper() for word in ("KEY", "TOKEN", "SECRET", "PASSWORD")
            )
        ]
        if not known:
            raise SystemExit(
                "No credential values found for comparison; refusing an empty check."
            )
    failures = []

    def scan(label, data):
        if any(value in data for value in known) or any(
            pattern.search(data) for pattern in PATTERNS
        ):
            failures.append(f"Credential-like content: {label}")

    files = (
        git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
        .decode()
        .split("\0")
    )
    for name in filter(None, files):
        path = ROOT / name
        if path.name.startswith(".env") and path.name != ".env.example":
            failures.append(f"Private environment file: {name}")
        if "local" in path.relative_to(ROOT).parts or path.suffix in {".pem", ".key"}:
            failures.append(f"Private artifact: {name}")
        scan(name, path.read_bytes())
        if path.suffix == ".ipynb":
            notebook = json.loads(path.read_text())
            if any(
                cell.get("outputs") or cell.get("execution_count") is not None
                for cell in notebook["cells"]
            ):
                failures.append(f"Notebook contains execution outputs: {name}")
    blobs = set()
    try:
        objects = git("rev-list", "--objects", "--all").decode().splitlines()
    except subprocess.CalledProcessError:
        objects = []  # New repository before its first commit.
    for row in objects:
        oid = row.split()[0]
        if git("cat-file", "-t", oid).strip() == b"blob" and oid not in blobs:
            blobs.add(oid)
            scan(f"Git blob {oid[:12]}", git("cat-file", "blob", oid))
    if failures:
        raise SystemExit("\n".join(failures))
    print(
        f"PASS: {len(list(filter(None, files)))} files and {len(blobs)} history blobs checked; "
        f"{len(known)} private credential values compared. No values displayed."
    )


if __name__ == "__main__":
    main()
