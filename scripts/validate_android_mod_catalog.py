#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

CATALOG = Path("android/mod-server/catalog.json")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
SHA_RE = re.compile(r"^[0-9a-fA-F]{64}$")
CATEGORIES = {"translations", "textures", "characters", "tracks", "gameplay", "ui"}
TARGETS = {"library", "custom-track", "texture-pack", "legacy-track", "legacy-character"}
REVISIONS = {"v77", "v80"}
MAX_ARCHIVE = 512 * 1024 * 1024

def fail(message: str) -> None:
    raise ValueError(message)

def expect_id(value, where):
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        fail(f"{where}: invalid id {value!r}")
    return value

def main() -> int:
    root = json.loads(CATALOG.read_text(encoding="utf-8"))
    if root.get("schemaVersion") != 1:
        fail("catalog schemaVersion must be 1")
    mods = root.get("mods")
    if not isinstance(mods, list):
        fail("catalog mods must be an array")

    seen = {}
    for index, mod in enumerate(mods):
        where = f"mods[{index}]"
        if not isinstance(mod, dict):
            fail(f"{where}: entry must be an object")
        mod_id = expect_id(mod.get("id"), where)
        if mod_id in seen:
            fail(f"{where}: duplicate id {mod_id}")
        seen[mod_id] = mod

        for field in ("name", "version", "category", "downloadUrl", "sha256"):
            if not isinstance(mod.get(field), str) or not mod[field].strip():
                fail(f"{where}/{mod_id}: {field} must be a non-empty string")

        category = mod["category"]
        if category not in CATEGORIES:
            fail(f"{where}/{mod_id}: unsupported category {category}")

        target = mod.get("installTarget", "library")
        if target not in TARGETS:
            fail(f"{where}/{mod_id}: unsupported installTarget {target}")
        if target in {"custom-track", "legacy-track"} and category != "tracks":
            fail(f"{where}/{mod_id}: {target} requires category tracks")
        if target == "legacy-character" and category != "characters":
            fail(f"{where}/{mod_id}: legacy-character requires category characters")
        if target == "texture-pack" and category != "textures":
            fail(f"{where}/{mod_id}: texture-pack requires category textures")

        parsed = urlparse(mod["downloadUrl"])
        if parsed.scheme != "https" or not parsed.netloc:
            fail(f"{where}/{mod_id}: downloadUrl must be absolute HTTPS")
        if not SHA_RE.fullmatch(mod["sha256"]):
            fail(f"{where}/{mod_id}: invalid SHA-256")

        size = mod.get("size")
        if size is not None:
            if not isinstance(size, int) or isinstance(size, bool) or size < 0 or size > MAX_ARCHIVE:
                fail(f"{where}/{mod_id}: size must be 0..{MAX_ARCHIVE}")

        revisions = mod.get("gameRevisions", [])
        if not isinstance(revisions, list) or any(r not in REVISIONS for r in revisions):
            fail(f"{where}/{mod_id}: gameRevisions may contain only v77/v80")
        if len(revisions) != len(set(revisions)):
            fail(f"{where}/{mod_id}: duplicate gameRevisions")

        for field in ("dependencies", "conflicts"):
            values = mod.get(field, [])
            if not isinstance(values, list):
                fail(f"{where}/{mod_id}: {field} must be an array")
            normalized = [expect_id(value, f"{where}/{mod_id}/{field}") for value in values]
            if mod_id in normalized:
                fail(f"{where}/{mod_id}: cannot reference itself in {field}")
            if len(normalized) != len(set(normalized)):
                fail(f"{where}/{mod_id}: duplicate ids in {field}")

    all_ids = set(seen)
    for mod_id, mod in seen.items():
        dependencies = set(mod.get("dependencies", []))
        conflicts = set(mod.get("conflicts", []))
        missing = sorted((dependencies | conflicts) - all_ids)
        if missing:
            fail(f"{mod_id}: references unknown catalog ids: {', '.join(missing)}")
        overlap = sorted(dependencies & conflicts)
        if overlap:
            fail(f"{mod_id}: same ids appear in dependencies and conflicts: {', '.join(overlap)}")

    print(f"Android mod catalog OK: {len(mods)} entries")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Android mod catalog invalid: {exc}", file=sys.stderr)
        raise SystemExit(1)
