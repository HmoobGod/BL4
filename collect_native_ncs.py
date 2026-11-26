"""Offline, read-only collection of specific BL4 NCS inputs; not a runtime mod.

The separately acquired upstream PAK index reader is used only at its exact
reviewed source identity. No upstream code, game data, or binary is bundled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import types
import zipfile
from pathlib import Path

BACKEND_SHA = "55f7b3766afba4b7954e044acce055f4e1ec203a"
BACKEND_COMMIT = "4e25cc3b2e540c1265f77eac7ba8b71363e012fb"
TARGETS = ("inv", "inv_stat", "inv_custom", "inventorypart", "attribute",
           "loot_config", "luck_category", "luckcategory", "resource_pool",
           "resourcepool", "game_resource_pool", "ui_stat", "ui_stat_group")
TARGET_RE = re.compile(r"Nexus-Data-(" + "|".join(TARGETS) + r")(?:_?\d+)?\.ncs", re.I)
PAK_RE = re.compile(r"pakchunk(\d+)-Windows(?:_(\d+)_P)?\.pak", re.I)
MAX_FILE = 128 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_ENTRIES = 4096


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def load_backend(path: Path):
    data = path.read_bytes()
    if git_blob_sha(data) != BACKEND_SHA:
        raise ValueError("PAK reader source does not match reviewed Git blob")
    module = types.ModuleType("bl4_reviewed_pak_reader")
    module.__file__ = str(path)
    # Exact reviewed source, no __main__ entrypoint or import-cache writes.
    exec(compile(data, str(path), "exec"), module.__dict__)
    if not callable(module.list_entries) or not callable(module.read_entry):
        raise ValueError("PAK reader interface missing")
    return module


def _priority(path: Path):
    m = PAK_RE.fullmatch(path.name)
    if not m:
        return None
    return (int(m[2]) if m[2] is not None else -1, int(m[1]))


def _stamp(path: Path):
    s = path.stat()
    return (s.st_size, s.st_mtime_ns)


def discover(game: Path, patch: Path | None):
    game = game.resolve(strict=True)
    root = game / "OakGame" / "Content" / "Paks"
    if not root.is_dir():
        raise ValueError("game root must contain OakGame/Content/Paks")
    paks = list(root.iterdir())
    if patch is not None:
        patch = patch.resolve(strict=True)
        if not patch.is_dir():
            raise ValueError("patch root must be a directory")
        paks.extend(patch.glob("*/*.pak"))
        paks.extend(patch.glob("*.pak"))
    found = []
    for p in paks:
        if _priority(p) is None:
            continue
        if p.is_symlink() or not p.is_file():
            raise ValueError(f"unexpected PAK path: {p.name}")
        found.append(p.resolve(strict=True))
    if not found:
        raise ValueError("no supported base/patch PAK filenames found")
    return sorted(set(found), key=lambda p: (_priority(p), str(p)))


def _target(entry_path: str):
    name = entry_path.replace("\\", "/").rsplit("/", 1)[-1]
    m = TARGET_RE.fullmatch(name)
    return (name, m[1].lower()) if m else None


def choose_entries(paks, backend):
    """Highest recognized patch priority per exact NCS basename; reject ties."""
    chosen = {}
    stamps = {}
    for pak in paks:
        priority = _priority(pak)
        if priority is None:
            raise ValueError("non-base PAK supplied")
        stamp = stamps[pak] = _stamp(pak)
        try:
            index = backend.list_entries(pak)
        except Exception as e:
            # No assumptions about a failed newer index: do not use stale data.
            raise ValueError(f"cannot read index {pak.name}: {e}") from e
        if _stamp(pak) != stamp:
            raise ValueError(f"PAK changed during index read: {pak.name}")
        for entry_path, entry in index.items():
            target = _target(entry_path)
            if target is None:
                continue
            name, kind = target
            key = name.casefold()
            old = chosen.get(key)
            if old is not None and old[0] == priority:
                raise ValueError(f"ambiguous same-priority NCS: {name}")
            if old is None or old[0] < priority:
                chosen[key] = (priority, pak, entry_path, entry, name, kind)
            if len(chosen) > MAX_ENTRIES:
                raise ValueError("too many selected NCS entries")
    return chosen, stamps


def _outside(output: Path, roots):
    for root in roots:
        if root is not None and output.is_relative_to(root.resolve()):
            raise ValueError("output must be outside the game and patch roots")


def collect(game: Path, patch: Path | None, output: Path, backend):
    output = output.resolve()
    _outside(output, (game, patch))
    if output.suffix.lower() != ".zip" or output.exists():
        raise ValueError("output must be a new .zip file")
    paks = discover(game, patch)
    chosen, stamps = choose_entries(paks, backend)
    active = [v for v in chosen.values() if v[3] is not None]
    if not active:
        raise ValueError("no active target NCS entries found")
    total = 0
    for _, pak, _, entry, name, _ in active:
        if not isinstance(entry, tuple) or len(entry) != 4 or any(type(v) is not int for v in entry):
            raise ValueError(f"invalid PAK entry: {name}")
        offset, usize, csize, method = entry
        if not (0 <= offset < stamps[pak][0] and 16 <= usize <= MAX_FILE and
                0 < csize <= stamps[pak][0] and method >= 0):
            raise ValueError(f"out-of-bounds or oversized PAK entry: {name}")
        total += usize
        if total > MAX_TOTAL:
            raise ValueError("selected data exceeds collection size limit")
    manifest = {"format": 1, "backend_commit": BACKEND_COMMIT,
                "backend_blob": BACKEND_SHA, "targets": list(TARGETS),
                "files": [], "deleted": [], "coverage": {}}
    output.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with output.open("xb") as stream:
            created = True
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as z:
                for _, pak, entry_path, entry, name, kind in sorted(chosen.values(), key=lambda v: v[4].casefold()):
                    if entry is None:
                        manifest["deleted"].append({"name": name, "pak": pak.name})
                        continue
                    if _stamp(pak) != stamps[pak]:
                        raise ValueError(f"PAK changed before read: {pak.name}")
                    data = backend.read_entry(pak, entry)
                    if _stamp(pak) != stamps[pak]:
                        raise ValueError(f"PAK changed during read: {pak.name}")
                    if type(data) is not bytes or len(data) != entry[1] or data[:4] != b"\x01NCS":
                        raise ValueError(f"invalid NCS payload: {name}")
                    z.writestr("ncs/" + name, data)
                    manifest["files"].append({"name": name, "type": kind, "pak": pak.name,
                                              "entry": entry_path, "size": len(data),
                                              "sha256": hashlib.sha256(data).hexdigest()})
                    manifest["coverage"][kind] = manifest["coverage"].get(kind, 0) + 1
                for pak, stamp in stamps.items():
                    if _stamp(pak) != stamp:
                        raise ValueError(f"PAK changed during collection: {pak.name}")
                z.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        with zipfile.ZipFile(output) as z:
            if z.testzip() is not None or len(z.namelist()) != len(active) + 1:
                raise ValueError("output archive verification failed")
            for row in manifest["files"]:
                if hashlib.sha256(z.read("ncs/" + row["name"])).hexdigest() != row["sha256"]:
                    raise ValueError("output payload hash mismatch")
    except BaseException:
        if created:
            output.unlink(missing_ok=True)
        raise
    return manifest


def configure_oodle(backend, path: Path | None):
    if path is None:
        def missing_oodle(*_args):
            raise ValueError("compressed PAK entry requires --oodle pointing to a trusted installed Oodle DLL")
        backend.oodle = missing_oodle
        return
    path = path.resolve(strict=True)
    if not path.is_file() or path.name.casefold() != "oo2core_9_win64.dll":
        raise ValueError("--oodle must identify the trusted oo2core_9_win64.dll file")
    backend.OODLE_DLL = str(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--game", type=Path, required=True, help="installed Borderlands 4 root")
    p.add_argument("--patch-root", type=Path, help="optional official downloaded patch root")
    p.add_argument("--backend", type=Path, required=True, help="separately acquired pinned pakncs.py")
    p.add_argument("--oodle", type=Path, help="optional trusted installed Oodle DLL path")
    p.add_argument("--output", type=Path, required=True, help="new private ZIP, outside game/patch roots")
    args = p.parse_args()
    try:
        backend = load_backend(args.backend)
        configure_oodle(backend, args.oodle)
        report = collect(args.game, args.patch_root, args.output, backend)
    except (ValueError, OSError, RuntimeError) as e:
        p.exit(1, f"Collection stopped: {e}\n")
    print("Collected NCS files:", len(report["files"]))
    print("Coverage:", json.dumps(report["coverage"], sort_keys=True))
    print("Private output:", args.output.resolve())


if __name__ == "__main__":
    main()
