"""把 .temp/monthly_review_YYYY-MM.md(或对应 PDF)以邮件发送。

SMTP 配置从 .config/smtp.yaml 读(若不存在,从环境变量 PRESON_SMTP_* 读)。
不在仓库提交凭据,smtp.yaml 由 .gitignore 排除。

用法:
    .venv/bin/python .tools/portfolio/send_monthly_email.py --month 2026-04
    .venv/bin/python .tools/portfolio/send_monthly_email.py --month 2026-04 --to xxx@gmail.com --dry-run

smtp.yaml 示例:
    host: smtp.gmail.com
    port: 587
    user: you@gmail.com
    password: app-specific-password
    from: you@gmail.com
    to: you@gmail.com
    starttls: true
"""
from __future__ import annotations

import argparse
import os
import smtplib
import ssl
import sys
from datetime import date
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMP_DIR = ROOT / ".temp"
PDF_DIR = ROOT / ".temp" / "pdf"
SMTP_CONF = ROOT / ".config" / "smtp.yaml"


def load_smtp_conf() -> dict:
    if SMTP_CONF.exists():
        try:
            import yaml
            return yaml.safe_load(SMTP_CONF.read_text(encoding="utf-8")) or {}
        except Exception as e:
            print(f"⚠️  读取 {SMTP_CONF} 失败:{e}", file=sys.stderr)

    # 环境变量降级
    return {
        "host": os.getenv("PRESON_SMTP_HOST"),
        "port": int(os.getenv("PRESON_SMTP_PORT", "587")),
        "user": os.getenv("PRESON_SMTP_USER"),
        "password": os.getenv("PRESON_SMTP_PASSWORD"),
        "from": os.getenv("PRESON_SMTP_FROM") or os.getenv("PRESON_SMTP_USER"),
        "to": os.getenv("PRESON_SMTP_TO"),
        "starttls": os.getenv("PRESON_SMTP_STARTTLS", "true").lower() in ("1", "true", "yes"),
    }


def build_message(md_path: Path, conf: dict, to: str | None) -> EmailMessage:
    msg = EmailMessage()
    ym = md_path.stem.replace("monthly_review_", "")
    msg["Subject"] = f"📊 preson 月度持仓体检 · {ym}"
    msg["From"] = conf["from"]
    msg["To"] = to or conf["to"]

    md_text = md_path.read_text(encoding="utf-8")

    # 文本主体 = 原 markdown(邮件客户端可渲染)
    msg.set_content(
        f"preson 月度持仓体检 · {ym}\n\n"
        f"完整内容见下方 markdown / PDF 附件。\n\n"
        + "─" * 50 + "\n"
        + md_text
    )

    # HTML 替代版本
    try:
        import markdown as _md
        html = _md.markdown(md_text, extensions=["tables", "fenced_code"])
        msg.add_alternative(f"<html><body>{html}</body></html>", subtype="html")
    except ImportError:
        pass

    # 附件:markdown
    msg.add_attachment(
        md_text.encode("utf-8"),
        maintype="text", subtype="markdown",
        filename=md_path.name,
    )

    # 附件:PDF(若存在)
    pdf_path = PDF_DIR / f"monthly_review_{ym}.pdf"
    if pdf_path.exists():
        msg.add_attachment(
            pdf_path.read_bytes(),
            maintype="application", subtype="pdf",
            filename=pdf_path.name,
        )

    return msg


def send(conf: dict, msg: EmailMessage) -> tuple[bool, str]:
    if not conf.get("host") or not conf.get("user") or not conf.get("password"):
        return False, "❌ SMTP 凭据未配置(.config/smtp.yaml 或 PRESON_SMTP_* 环境变量)"
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(conf["host"], int(conf["port"])) as s:
            if conf.get("starttls", True):
                s.starttls(context=ctx)
            s.login(conf["user"], conf["password"])
            s.send_message(msg)
        return True, f"✅ 已发送至 {msg['To']}"
    except Exception as e:
        return False, f"❌ 发送失败:{e}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="YYYY-MM(默认本月)")
    ap.add_argument("--to", help="覆盖收件人")
    ap.add_argument("--dry-run", action="store_true",
                    help="只构造不发送,打印邮件元信息和附件列表")
    args = ap.parse_args()

    ym = args.month or date.today().strftime("%Y-%m")
    md_path = TEMP_DIR / f"monthly_review_{ym}.md"

    if not md_path.exists():
        print(f"❌ markdown 不存在:{md_path}")
        print(f"   先跑:python3 .tools/portfolio/monthly_review.py --month {ym}")
        return 1

    conf = load_smtp_conf()
    msg = build_message(md_path, conf, args.to)

    if args.dry_run:
        print(f"📧 [DRY RUN] {msg['Subject']}")
        print(f"   From: {msg['From']}")
        print(f"   To:   {msg['To']}")
        print(f"   附件: {[a.get_filename() for a in msg.iter_attachments()]}")
        print(f"   SMTP: {conf.get('host')}:{conf.get('port')} (starttls={conf.get('starttls')})")
        return 0

    ok, info = send(conf, msg)
    print(info)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
