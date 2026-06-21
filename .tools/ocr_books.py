#!/usr/bin/env python3
"""批量 OCR 投资书籍 PDF。

扫描 01_knowledge/04_知识体系/04_参考资料/ 下所有 PDF,跳过已 OCR 的,
对剩余 PDF 用 ocrmypdf 加双语 OCR 文字层,输出到 .temp/ocr_books/。

用法:
  python3 .tools/ocr_books.py            # 跑所有未处理的
  python3 .tools/ocr_books.py --dry-run  # 仅打印会跑哪些
  python3 .tools/ocr_books.py --force    # 强制重 OCR(覆盖已有)
  python3 .tools/ocr_books.py --archive  # 把 .temp/ocr_books/ 里的输出归档到
                                         # 04_参考资料/_OCR可搜索版/(镜像源子目录)

依赖:
  - ocrmypdf (brew install ocrmypdf)
  - tesseract chi_sim + eng 字典
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "01_knowledge" / "04_知识体系" / "04_参考资料"
OUTPUT_DIR = ROOT / ".temp" / "ocr_books"
ARCHIVE_DIR = SOURCE_DIR / "_OCR可搜索版"  # 归档目标:镜像 SOURCE_DIR 子目录结构
LOG_FILE = OUTPUT_DIR / "ocr.log"

# 把命名不一致的旧输出迁移到新规则名(一次性,做完即不再生效)
LEGACY_RENAME = {
    "价值投资路线图_OCR.pdf": "价值投资路线图_格雷厄姆智慧家族的制胜之道_OCR.pdf",
}


def derive_output_name(pdf_path: Path) -> str:
    """从源 PDF 文件名派生 _OCR.pdf 输出名。

    规则(按顺序):
      1. 去全/半角括号包裹内容:(高清) （典藏版）
      2. 去方括号包裹内容:[lunarora.com]
      3. 去版次描述:原书第6版 / 全新升级版 / 典藏版
      4. 中/半角冒号变下划线
      5. 多空格折叠成单下划线
      6. 多下划线折叠
      7. 加 _OCR.pdf
    """
    stem = pdf_path.stem
    stem = re.sub(r"[（(][^）)]*[）)]", "", stem)
    stem = re.sub(r"\[[^\]]*\]", "", stem)
    stem = re.sub(r"原书第\d+版|全新升级版|典藏版|第\d+版", "", stem)
    stem = stem.replace(":", "_").replace(":", "_")
    stem = re.sub(r"\s+", "_", stem.strip())
    stem = re.sub(r"_+", "_", stem)
    stem = stem.strip("_")
    return f"{stem}_OCR.pdf"


def list_pdfs() -> list[Path]:
    return sorted(SOURCE_DIR.rglob("*.pdf"))


def is_done(pdf_path: Path) -> bool:
    out = OUTPUT_DIR / derive_output_name(pdf_path)
    return out.exists() and out.stat().st_size > 0


def log(msg: str) -> None:
    ts = datetime.now().isoformat(timespec="seconds")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def migrate_legacy_names() -> None:
    """一次性把旧命名的 _OCR.pdf 迁移到新规则。"""
    for old_name, new_name in LEGACY_RENAME.items():
        old_p = OUTPUT_DIR / old_name
        new_p = OUTPUT_DIR / new_name
        if old_p.exists() and not new_p.exists():
            old_p.rename(new_p)
            log(f"📝 renamed legacy: {old_name} → {new_name}")


def ocr_one(pdf_path: Path, output_path: Path) -> bool:
    cmd = [
        "ocrmypdf",
        "-l", "chi_sim+eng",
        "--skip-text",
        "--jobs", "4",
        str(pdf_path),
        str(output_path),
    ]
    log(f"--- start: {pdf_path.name} → {output_path.name} ---")
    start = datetime.now()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        elapsed = (datetime.now() - start).total_seconds()
        if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
            size_mb = output_path.stat().st_size / 1024 / 1024
            log(f"✅ done in {elapsed:.0f}s, {size_mb:.1f} MB")
            # 把 stderr 末尾(tesseract warning)写日志,便于事后核查
            if result.stderr:
                tail = result.stderr.strip().splitlines()[-30:]
                with LOG_FILE.open("a", encoding="utf-8") as f:
                    f.write("\n".join(tail) + "\n\n")
            return True
        log(f"❌ failed (rc={result.returncode}) in {elapsed:.0f}s")
        if result.stderr:
            log(f"stderr tail: {result.stderr[-500:]}")
        if output_path.exists() and output_path.stat().st_size == 0:
            output_path.unlink()
        return False
    except subprocess.TimeoutExpired:
        log("❌ TIMEOUT after 3600s")
        return False
    except Exception as e:
        log(f"❌ exception: {e}")
        return False


def archive_outputs(dry_run: bool = False) -> int:
    """把 OUTPUT_DIR 里的 _OCR.pdf 按源 PDF 路径镜像到 ARCHIVE_DIR。

    源 04_参考资料/02_价值投资/穷查理宝典.pdf → ARCHIVE_DIR/02_价值投资/穷查理宝典_OCR.pdf
    """
    moved, missing = 0, []
    print(f"📦 归档目标:{ARCHIVE_DIR.relative_to(ROOT)}")
    for src_pdf in list_pdfs():
        rel_dir = src_pdf.parent.relative_to(SOURCE_DIR)
        target_dir = ARCHIVE_DIR / rel_dir
        ocr_name = derive_output_name(src_pdf)
        src_ocr = OUTPUT_DIR / ocr_name
        target_ocr = target_dir / ocr_name

        if not src_ocr.exists():
            missing.append(ocr_name)
            continue
        if target_ocr.exists():
            print(f"  ⏭️  已存在,跳过:{rel_dir}/{ocr_name}")
            continue

        action = "[dry-run] " if dry_run else ""
        print(f"  📄 {action}{ocr_name} → {rel_dir}/")
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            src_ocr.rename(target_ocr)
        moved += 1

    print(f"\n📊 归档完成:{moved} 个文件已移动 / {len(missing)} 个未生成 OCR")
    if missing:
        print("⚠️  以下源 PDF 未找到对应 OCR 输出(可能尚未跑过):")
        for m in missing:
            print(f"  - {m}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="批量 OCR 投资书籍 PDF")
    parser.add_argument("--dry-run", action="store_true", help="只打印,不跑 OCR")
    parser.add_argument("--force", action="store_true", help="强制重 OCR(覆盖)")
    parser.add_argument("--archive", action="store_true",
                        help="归档 .temp/ocr_books/*.pdf → 04_参考资料/_OCR可搜索版/")
    args = parser.parse_args()

    if not SOURCE_DIR.exists():
        print(f"❌ 源目录不存在:{SOURCE_DIR}", file=sys.stderr)
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.archive:
        return archive_outputs(dry_run=args.dry_run)

    migrate_legacy_names()

    all_pdfs = list_pdfs()
    if args.force:
        todo = all_pdfs
        skipped = []
    else:
        todo = [p for p in all_pdfs if not is_done(p)]
        skipped = [p for p in all_pdfs if is_done(p)]

    print(f"📚 共 {len(all_pdfs)} 本,已完成 {len(skipped)},待处理 {len(todo)}")
    if skipped:
        print("\n✅ 已完成(跳过):")
        for p in skipped:
            print(f"  - {p.name}")
    if todo:
        print("\n📋 待处理:")
        for p in todo:
            print(f"  - {p.name} → {derive_output_name(p)}")

    if args.dry_run:
        return 0
    if not todo:
        print("\n🎉 全部已完成,无事可做。")
        return 0

    log(f"=== START batch: {len(todo)} books to OCR ===")
    success = 0
    failed: list[str] = []
    for i, pdf in enumerate(todo, 1):
        out = OUTPUT_DIR / derive_output_name(pdf)
        log(f"[{i}/{len(todo)}] {pdf.name}")
        if ocr_one(pdf, out):
            success += 1
        else:
            failed.append(pdf.name)
    log(f"=== END batch: {success}/{len(todo)} success ===")
    if failed:
        log(f"failed list: {failed}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
