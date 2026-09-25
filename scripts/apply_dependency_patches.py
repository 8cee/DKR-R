#!/usr/bin/env python3
"""Verify and apply DKR-R's checksummed dependency patch manifest."""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "patches" / "manifest.json"


def run(*args: str, cwd: pathlib.Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=str(cwd) if cwd else None,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def main() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != 1:
        raise RuntimeError("Unsupported patch manifest schema")

    for dependency in data["dependencies"]:
        repo = ROOT / dependency["repositoryPath"]
        if not (repo / ".git").exists():
            print(f"[SKIP] {dependency['name']}: checkout not present at {repo}")
            continue

        commit = run("git", "rev-parse", "HEAD", cwd=repo).stdout.strip()
        expected = dependency["expectedCommit"]
        if commit != expected:
            raise RuntimeError(
                f"{dependency['name']} commit mismatch: expected {expected}, got {commit}"
            )

        patches: list[tuple[dict[str, str], pathlib.Path]] = []
        for entry in dependency["patches"]:
            patch = ROOT / entry["path"]
            digest = hashlib.sha256(patch.read_bytes()).hexdigest()
            if digest != entry["sha256"]:
                raise RuntimeError(f"Patch checksum mismatch: {entry['path']}")
            patches.append((entry, patch))

        def check_patch(reverse: bool, patch: pathlib.Path) -> bool:
            args = ["git", "apply"]
            if reverse:
                args.append("--reverse")
            args.extend(["--check", str(patch)])
            return run(*args, cwd=repo, check=False).returncode == 0

        def apply_patch(entry: dict[str, str], patch: pathlib.Path) -> None:
            result = run("git", "apply", str(patch), cwd=repo, check=False)
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "git apply failed").strip()
                raise RuntimeError(
                    f"{dependency['name']}: failed to apply {entry['path']}: {detail}"
                )
            print(f"[OK] {dependency['name']}: {entry['path']} (applied)")

        if all(check_patch(True, patch) for _, patch in patches):
            for entry, _ in patches:
                print(f"[OK] {dependency['name']}: {entry['path']} (already-applied)")
            continue

        if all(check_patch(False, patch) for _, patch in patches):
            for entry, patch in patches:
                apply_patch(entry, patch)
            continue

        print(
            f"[INFO] {dependency['name']}: resetting to pinned commit and "
            "re-applying all patches"
        )
        run("git", "checkout", "--", ".", cwd=repo)
        for entry, patch in patches:
            apply_patch(entry, patch)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, KeyError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
