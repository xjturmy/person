"""从 .github_blob_store 分片还原原始大文件.

用法:
  python3 .tools/github_upload/merge_assets.py --restore-all
  python3 .tools/github_upload/merge_assets.py --restore data/preson.duckdb
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / ".github_blob_store" / "manifest.json"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def restore_one(entry: dict, *, force: bool = False) -> bool:
    original = entry["original"]
    dest = ROOT / original
    expected_sha = entry.get("sha256")
    expected_size = entry.get("size")

    if dest.exists() and not force:
        if expected_sha and _sha256_file(dest) == expected_sha:
            print(f"跳过(已存在且校验一致): {original}")
            return True
        if expected_size and dest.stat().st_size == expected_size:
            print(f"跳过(已存在且大小一致): {original}")
            return True

    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as out:
        for part_rel in entry["parts"]:
            part_path = ROOT / part_rel
            if not part_path.exists():
                raise FileNotFoundError(f"缺少分片: {part_rel}")
            out.write(part_path.read_bytes())

    if expected_sha:
        got = _sha256_file(dest)
        if got != expected_sha:
            dest.unlink(missing_ok=True)
            raise ValueError(f"校验失败 {original}: sha256 mismatch")
    print(f"已还原: {original} ({dest.stat().st_size / (1024*1024):.1f} MB)")
    return True


def restore_all(force: bool = False) -> int:
    if not MANIFEST.exists():
        print("无 manifest, 无需还原")
        return 0
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    n = 0
    for entry in data.get("files", []):
        restore_one(entry, force=force)
        n += 1
    return n


def main() -> None:
    parser = argparse.ArgumentParser(description="合并 GitHub 分片还原大文件")
    parser.add_argument("--restore-all", action="store_true")
    parser.add_argument("--restore", metavar="PATH", help="还原单个原始路径")
    parser.add_argument("--force", action="store_true", help="覆盖已存在文件")
    args = parser.parse_args()

    if not MANIFEST.exists():
        raise SystemExit(f"找不到 {MANIFEST}")

    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if args.restore_all:
        restore_all(force=args.force)
        return

    if args.restore:
        target = args.restore.replace("\\", "/")
        for entry in data.get("files", []):
            if entry["original"] == target:
                restore_one(entry, force=args.force)
                return
        raise SystemExit(f"manifest 中无: {target}")

    parser.print_help()


if __name__ == "__main__":
    main()
