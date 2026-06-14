"""One-command entry for WeChat chat analysis."""
import argparse
import glob
import json
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta
from urllib.error import URLError
from urllib.request import urlopen

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(PROJECT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from decrypt import decrypt_from_keys
from keys import generate_keys
from paths import ALL_KEYS_FILE, DECRYPTED_DIR, EXPORT_DIR, LOGS_DIR, REPORTS_DIR, WECHAT_DECRYPT_CONFIG
from query import WeChatDB

WX_KEY_DIR = os.path.join(PROJECT_DIR, "tools", "wx_key")
WX_KEY_MANIFEST = os.path.join(PROJECT_DIR, "tools", "wx_key.manifest.json")


def load_env_file():
    """Load .env into os.environ when keys are not already set."""
    env_path = os.path.join(PROJECT_DIR, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def report_settings():
    load_env_file()
    return {
        "default_groups": [
            g.strip()
            for g in os.environ.get("WECHAT_DEFAULT_GROUPS", "").split(",")
            if g.strip()
        ],
        "self_wxid": os.environ.get("WECHAT_SELF_WXID", ""),
        "self_name": os.environ.get("WECHAT_SELF_NAME", "我"),
        "display_name_mode": os.environ.get("WECHAT_DISPLAY_NAME_MODE", "remark"),
    }


def detect_db_dir_windows():
    appdata = os.environ.get("APPDATA", "")
    config_dir = os.path.join(appdata, "Tencent", "xwechat", "config")
    candidates = []
    if os.path.isdir(config_dir):
        for ini_file in glob.glob(os.path.join(config_dir, "*.ini")):
            content = None
            for enc in ("utf-8", "gbk"):
                try:
                    with open(ini_file, "r", encoding=enc) as f:
                        content = f.read(1024).strip()
                    break
                except UnicodeDecodeError:
                    continue
                except OSError:
                    break
            if content and os.path.isdir(content):
                candidates.extend(glob.glob(os.path.join(content, "xwechat_files", "*", "db_storage")))

    candidates = [c for c in candidates if os.path.isdir(c)]

    def sort_time(path):
        message_dir = os.path.join(path, "message")
        target = message_dir if os.path.isdir(message_dir) else path
        try:
            return os.path.getmtime(target)
        except OSError:
            return 0

    candidates = sorted(set(candidates), key=sort_time, reverse=True)
    return candidates[0] if candidates else None


def ensure_export_dirs():
    for path in (EXPORT_DIR, DECRYPTED_DIR, REPORTS_DIR, LOGS_DIR):
        os.makedirs(path, exist_ok=True)


def write_wechat_decrypt_config(db_dir):
    ensure_export_dirs()
    cfg = {
        "db_dir": db_dir,
        "keys_file": ALL_KEYS_FILE,
        "decrypted_dir": DECRYPTED_DIR,
        "decoded_image_dir": os.path.join(EXPORT_DIR, "decoded_images"),
        "wechat_process": "Weixin.exe",
        "wxwork_db_dir": "",
        "wxwork_keys_file": os.path.join(EXPORT_DIR, "wxwork_keys.json"),
        "wxwork_decrypted_dir": os.path.join(EXPORT_DIR, "wxwork_decrypted"),
        "wxwork_export_dir": os.path.join(EXPORT_DIR, "wxwork_export"),
        "wxwork_process": "WXWork.exe",
        "transcription_backend": "local",
        "local_whisper_model": "base",
        "openai_api_key": "",
    }
    os.makedirs(os.path.dirname(WECHAT_DECRYPT_CONFIG), exist_ok=True)
    with open(WECHAT_DECRYPT_CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)
    return WECHAT_DECRYPT_CONFIG


def find_group(db, name):
    if "@chatroom" in name:
        return name

    if db.contact:
        row = db.contact.execute(
            "SELECT username FROM contact WHERE (nick_name=? OR remark=?) AND username LIKE ?",
            (name, name, "%@chatroom%"),
        ).fetchone()
        if row:
            return row[0]

        rows = db.contact.execute(
            "SELECT username, nick_name, remark FROM contact WHERE (nick_name LIKE ? OR remark LIKE ?) AND username LIKE ?",
            (f"%{name}%", f"%{name}%", "%@chatroom%"),
        ).fetchall()
        if len(rows) == 1:
            return rows[0][0]
        if len(rows) > 1:
            print(f"[WARN] 找到多个匹配 '{name}' 的群，使用第一个:")
            for username, nick, remark in rows:
                print(f"  {remark or nick or username}  {username}")
            return rows[0][0]

    if db.session:
        row = db.session.execute(
            "SELECT username FROM SessionTable WHERE username LIKE ? AND username LIKE ?",
            (f"%{name}%", "%@chatroom%"),
        ).fetchone()
        if row:
            return row[0]
    return None


def day_range(date_str=None):
    d = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.now()
    start = d.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def safe_group_filename(group_name):
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in group_name)[:60]


def format_group_md_body(info):
    md = f"_消息数: {info['count']} 条_\n\n"
    if info.get("sample"):
        md += f"### 聊天记录\n\n```\n{info['sample']}\n```\n\n"
    return md


def format_group_md(group_name, date_str, info):
    return f"# 微信群聊天记录 - {group_name} - {date_str}\n\n{format_group_md_body(info)}"


def render_group_md(group_name, date_str, info):
    ensure_export_dirs()
    path = os.path.join(REPORTS_DIR, f"report_{date_str}_{safe_group_filename(group_name)}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(format_group_md(group_name, date_str, info))
    return path


def render_report(summaries, date_str):
    ensure_export_dirs()
    md = f"# 微信群日报 - {date_str}\n\n"
    for group_name, info in summaries.items():
        md += f"## {group_name}\n\n"
        md += format_group_md_body(info)
        md += "---\n\n"

    path = os.path.join(REPORTS_DIR, f"report_{date_str}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    return path


def load_wx_key_manifest():
    if not os.path.exists(WX_KEY_MANIFEST):
        return {
            "version": "2.1.8",
            "archive": "wx_key-windows-v2.1.8.zip",
            "exe": "wx_key.exe",
            "urls": [
                "https://github.com/ycccccccy/wx_key/releases/download/v2.1.8/wx_key-windows-v2.1.8.zip",
            ],
        }
    with open(WX_KEY_MANIFEST, encoding="utf-8") as f:
        return json.load(f)


def wx_key_ready():
    manifest = load_wx_key_manifest()
    exe_name = manifest.get("exe", "wx_key.exe")
    return os.path.isfile(os.path.join(WX_KEY_DIR, exe_name))


def download_wx_key(url, dest_path):
    print(f"下载: {url}")
    with urlopen(url, timeout=120) as response:
        total = int(response.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 1024 * 256
        with open(dest_path, "wb") as out:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                out.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    print(f"\r进度: {pct}% ({downloaded // (1024 * 1024)} MB)", end="", flush=True)
    print()


def extract_wx_key_archive(archive_path, target_dir):
    with tempfile.TemporaryDirectory() as staging:
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(staging)

        exe_roots = []
        for root, _, files in os.walk(staging):
            if "wx_key.exe" in files:
                exe_roots.append(root)
        if not exe_roots:
            raise FileNotFoundError("压缩包中未找到 wx_key.exe")

        source_root = exe_roots[0]
        if os.path.isdir(target_dir):
            shutil.rmtree(target_dir)
        shutil.copytree(source_root, target_dir)


def cmd_download_wx_key(args):
    manifest = load_wx_key_manifest()
    exe_name = manifest.get("exe", "wx_key.exe")
    exe_path = os.path.join(WX_KEY_DIR, exe_name)

    if wx_key_ready() and not args.force:
        print(f"wx_key 已存在: {exe_path}")
        print("如需重新下载，请加 --force")
        return 0

    urls = []
    if args.url:
        urls.append(args.url)
    urls.extend(manifest.get("urls", []))
    if not urls:
        print("[ERROR] 未配置 wx_key 下载地址，请编辑 tools/wx_key.manifest.json")
        return 1

    if os.path.isdir(WX_KEY_DIR) and args.force:
        shutil.rmtree(WX_KEY_DIR)

    archive_name = manifest.get("archive", "wx_key-windows-v2.1.8.zip")
    last_error = None
    for url in urls:
        if not url:
            continue
        try:
            with tempfile.TemporaryDirectory() as tmp:
                archive_path = os.path.join(tmp, archive_name)
                download_wx_key(url, archive_path)
                extract_wx_key_archive(archive_path, WX_KEY_DIR)
            if wx_key_ready():
                print(f"wx_key 已就绪: {exe_path}")
                print(f"版本: v{manifest.get('version', 'unknown')}")
                return 0
            last_error = "解压后未找到 wx_key.exe"
        except (URLError, OSError, zipfile.BadZipFile) as exc:
            last_error = str(exc)
            print(f"[WARN] 下载失败: {exc}")

    print(f"[ERROR] wx_key 下载失败: {last_error}")
    return 1


def cmd_setup(args):
    if args.download_wx_key and not wx_key_ready():
        code = cmd_download_wx_key(argparse.Namespace(force=False, url=None))
        if code != 0:
            return code

    db_dir = args.db_dir or detect_db_dir_windows()
    if not db_dir:
        print("[ERROR] 未能自动检测 db_storage，请手动传 --db-dir")
        return 1
    config_path = write_wechat_decrypt_config(db_dir)
    print(f"DB 目录: {db_dir}")
    print(f"已写入配置: {config_path}")
    print(f"输出目录: {EXPORT_DIR}")
    if args.raw_key:
        info = generate_keys(args.raw_key, db_dir, ALL_KEYS_FILE)
        print(f"已生成密钥文件: {info['output']}")
    else:
        print("未传 --raw-key，跳过 all_keys.json 生成")
    return 0


def cmd_decrypt(args):
    result = decrypt_from_keys(ALL_KEYS_FILE, DECRYPTED_DIR, args.only)
    for rel, reason in result["failures"]:
        print(f"[FAIL] {rel}: {reason}")
    print(f"\n输出目录: {result['output_dir']}")
    print(f"完成: {result['ok']} 成功, {result['failed']} 失败, {result['skipped']} 跳过")
    return 1 if result["failed"] else 0


def cmd_groups(_args):
    db = WeChatDB(DECRYPTED_DIR)
    try:
        for s in db.list_sessions():
            if "@chatroom" in s["username"]:
                dn = db.get_chatroom_name(s["username"])
                marker = " *" if dn != s["username"] else ""
                print(f'{dn:30s} {s["username"]:45s} {s["last_time"]}{marker}')
    finally:
        db.close()
    return 0


def cmd_export(args):
    settings = report_settings()
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    start, end = day_range(date_str)
    groups = [g.strip() for g in (args.groups or ",".join(settings["default_groups"])).split(",") if g.strip()]
    if not groups:
        print("[ERROR] 未指定群名。请传 --groups，或在 .env 中设置 WECHAT_DEFAULT_GROUPS")
        return 1

    db = WeChatDB(
        DECRYPTED_DIR,
        self_wxid=settings.get("self_wxid") or None,
        self_name=settings.get("self_name") or "我",
        display_name_mode=settings.get("display_name_mode", "remark"),
    )
    summaries = {}
    md_outputs = []
    try:
        print(f"日期: {date_str}")
        print(f"目标群: {groups}")
        for group_name in groups:
            print(f"\n--- {group_name} ---")
            username = find_group(db, group_name)
            if not username:
                print(f"[SKIP] 未找到群: {group_name}")
                continue
            display = db.get_chatroom_name(username)
            messages = db.query_messages(username, start_time=start, end_time=end, limit=args.limit)
            print(f"chatroom: {username} ({display})")
            print(f"消息数: {len(messages)}")
            if not messages:
                continue

            normalized = db.normalize_messages(messages)
            formatted = "\n".join(f'[{m["time_text"]}] {m["sender"]}: {m["text"]}' for m in normalized)
            summaries[display] = {
                "count": len(messages),
                "sample": formatted,
            }
            md_path = render_group_md(display, date_str, summaries[display])
            md_outputs.append(md_path)
    finally:
        db.close()

    if not summaries:
        print("\n没有数据可导出")
        return 0
    path = render_report(summaries, date_str)
    print(f"\n汇总报告: {path}")
    for output in md_outputs:
        print(f"聊天记录: {output}")
    print("\n提示: AI 话题分析请通过 AI Coding 工具加载 Skill，再运行 scripts/render_manual_report.py 生成 HTML/PNG。")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="WeChatDaily — 微信群聊日报工具")
    sub = parser.add_subparsers(dest="command")

    dl_wx = sub.add_parser("download-wx-key", help="从 wx_key 上游 Release 下载并解压到 tools/wx_key/")
    dl_wx.add_argument("--force", action="store_true", help="强制重新下载")
    dl_wx.add_argument("--url", help="自定义下载 URL，优先于 manifest")
    dl_wx.set_defaults(func=cmd_download_wx_key)

    setup = sub.add_parser("setup", help="自动检测 db_storage、写配置、生成 all_keys.json")
    setup.add_argument("--raw-key", help="wx_key 输出的 64 位 hex raw_key")
    setup.add_argument("--db-dir", help="微信 db_storage 目录；不传则尝试自动检测")
    setup.add_argument("--download-wx-key", action="store_true", help="若本地缺少 wx_key，先自动下载")
    setup.set_defaults(func=cmd_setup)

    decrypt = sub.add_parser("decrypt", help="解密 export/all_keys.json 中记录的数据库")
    decrypt.add_argument("--only", help="只解密包含该字符串的相对路径，如 session.db")
    decrypt.set_defaults(func=cmd_decrypt)

    groups = sub.add_parser("groups", help="列出可用群聊")
    groups.set_defaults(func=cmd_groups)

    export = sub.add_parser("export", help="导出群聊 Markdown 记录（不含 AI 分析）")
    export.add_argument("--date", help="日期 YYYY-MM-DD，默认今天")
    export.add_argument("--groups", help="群名列表，逗号分隔")
    export.add_argument("--limit", type=int, default=1000, help="每个群最多读取消息数")
    export.set_defaults(func=cmd_export)

    report = sub.add_parser("report", help="导出群聊 Markdown（同 export，兼容旧命令）")
    report.add_argument("--date", help="日期 YYYY-MM-DD，默认今天")
    report.add_argument("--groups", help="群名列表，逗号分隔")
    report.add_argument("--limit", type=int, default=1000, help="每个群最多读取消息数")
    report.add_argument("--dry-run", action="store_true", help="兼容旧参数，无效果")
    report.set_defaults(func=cmd_export)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        raise SystemExit(1)
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
