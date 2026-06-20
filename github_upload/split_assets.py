"""将超大文件拆分为 GitHub 可推送的分片(单片 < chunk_bytes).

用法:
  python3 .tools/github_upload/split_assets.py --scan
  python3 .tools/github_upload/split_assets.py --apply
  python3 .tools/github_upload/merge_assets.py --restore-all

分片目录: .github_blob_store/<相对路径>/part000, part001, ...
清单: .github_blob_store/manifest.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / ".github_blob_store"
MANIFEST = STORE / "manifest.json"
CHUNK_BYTES = 90 * 1024 * 1024  # 90MB, GitHub 硬限 100MB

SKIP_DIRS = {
    ".git",
    ".venv",
    ".github_blob_store",
    "__pycache__",
    "node_modules",
}
SKIP_PREFIXES = (".venv.",)


def _should_skip(path: Path) -> bool:
    parts = path.parts
    for p in parts:
        if p in SKIP_DIRS:
            return True
        if any(p.startswith(s) for s in SKIP_PREFIXES):
            return True
    return False


def scan_large_files(min_bytes: int = CHUNK_BYTES) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS and not d.startswith(".venv")
        ]
        for name in filenames:
            rel = Path(dirpath, name).relative_to(ROOT)
            if _should_skip(rel):
                continue
            fp = ROOT / rel
            try:
                if fp.stat().st_size >= min_bytes:
                    out.append(rel)
            except OSError:
                continue
    return sorted(out)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def _split_one(rel_path: str, chunk_bytes: int) -> dict:
    src = ROOT / rel_path
    dest_dir = STORE / rel_path
    dest_dir.mkdir(parents=True, exist_ok=True)

    size = src.stat().st_size
    sha = _sha256_file(src)
    parts: list[str] = []

    with src.open("rb") as f:
        idx = 0
        while True:
            data = f.read(chunk_bytes)
            if not data:
                break
            part_name = f"part{idx:03d}"
            part_rel = str(Path(".github_blob_store") / rel_path / part_name)
            part_path = ROOT / part_rel
            part_path.parent.mkdir(parents=True, exist_ok=True)
            part_path.write_bytes(data)
            parts.append(part_rel.replace("\\", "/"))
            idx += 1

    return {
        "original": rel_path.replace("\\", "/"),
        "sha256": sha,
        "size": size,
        "chunk_bytes": chunk_bytes,
        "parts": parts,
    }


def load_manifest() -> dict:
    if not MANIFEST.exists():
        return {"version": 1, "chunk_bytes": CHUNK_BYTES, "files": []}
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def save_manifest(data: dict) -> None:
    STORE.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def apply_split(
    paths: list[Path] | None = None,
    *,
    workers: int = 4,
    chunk_bytes: int = CHUNK_BYTES,
) -> int:
    targets = paths or scan_large_files(chunk_bytes)
    if not targets:
        print("未发现需要拆分的文件(阈值 %d MB)" % (chunk_bytes // (1024 * 1024)))
        return 0

    rels = [str(p).replace("\\", "/") for p in targets]
    print(f"待拆分 {len(rels)} 个文件, workers={workers}")
    entries: list[dict] = []

    if workers <= 1 or len(rels) == 1:
        for rel in rels:
            print(f"  拆分 {rel}")
            entries.append(_split_one(rel, chunk_bytes))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_split_one, rel, chunk_bytes): rel for rel in rels
            }
            for fut in as_completed(futures):
                rel = futures[fut]
                print(f"  完成 {rel}")
                entries.append(fut.result())

    manifest = load_manifest()
    manifest["chunk_bytes"] = chunk_bytes
    by_orig = {e["original"]: e for e in manifest.get("files", [])}
    for e in entries:
        by_orig[e["original"]] = e
    manifest["files"] = sorted(by_orig.values(), key=lambda x: x["original"])
    save_manifest(manifest)
    print(f"已写入 {MANIFEST.relative_to(ROOT)}")
    return len(entries)


def main() -> None:
    parser = argparse.ArgumentParser(description="拆分超大文件供 GitHub 上传")
    parser.add_argument("--scan", action="store_true", help="仅扫描")
    parser.add_argument("--apply", action="store_true", help="执行拆分")
    parser.add_argument("--min-mb", type=int, default=90, help="超过此大小才拆分")
    parser.add_argument("--workers", type=int, default=4, help="并行 worker 数")
    args = parser.parse_args()

    min_bytes = args.min_mb * 1024 * 1024
    large = scan_large_files(min_bytes)

    if args.scan or not args.apply:
        if large:
            print("超过阈值的文件:")
            for p in large:
                sz = (ROOT / p).stat().st_size / (1024 * 1024)
                print(f"  {p}  ({sz:.1f} MB)")
        else:
            print("无超大文件")
        if not args.apply:
            return

    apply_split(large, workers=args.workers, chunk_bytes=min_bytes)


if __name__ == "__main__":
    main()
