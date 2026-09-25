#!/usr/bin/env python3
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "patches" / "manifest.json"

def main() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != 1:
        raise ValueError("unsupported patch manifest schema")

    checked = 0
    for dependency in data.get("dependencies", []):
        name = dependency.get("name", "<unnamed>")
        for entry in dependency.get("patches", []):
            rel = entry.get("path")
            expected = entry.get("sha256")
            if not isinstance(rel, str) or not rel:
                raise ValueError(f"{name}: patch entry has no path")
            if not isinstance(expected, str) or len(expected) != 64:
                raise ValueError(f"{name}: {rel}: invalid manifest SHA-256")
            path = ROOT / rel
            if not path.is_file():
                raise ValueError(f"{name}: missing patch file: {rel}")
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected.lower():
                raise ValueError(
                    f"{name}: checksum mismatch for {rel}: "
                    f"manifest={expected.lower()} actual={actual}"
                )
            parsed = subprocess.run(
                ["git", "apply", "--numstat", str(path)],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if parsed.returncode != 0:
                detail = (parsed.stderr or parsed.stdout or "invalid patch syntax").strip()
                raise ValueError(f"{name}: malformed patch {rel}: {detail}")
            checked += 1

    print(f"Dependency patch manifest OK: {checked} patch files")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, json.JSONDecodeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Dependency patch manifest invalid: {exc}", file=sys.stderr)
        raise SystemExit(1)
