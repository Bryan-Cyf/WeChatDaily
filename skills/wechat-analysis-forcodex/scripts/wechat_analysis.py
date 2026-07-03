#!/usr/bin/env python3
"""Standalone WeChat chat decrypt/export helper for Codex skills."""

from __future__ import annotations

import argparse
import hashlib
import hmac as hmac_mod
import json
import os
import re
import sqlite3
import struct
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

PAGE_SZ = 4096
SALT_SZ = 16
IV_SZ = 16
HMAC_SZ = 64
RESERVE_SZ = 80
SQLITE_HDR = b"SQLite format 3\x00"
PBKDF2_ITERS = 256000
AES = None
SYSTEM_LOCAL_TYPES = {10000, 10002}
FORBIDDEN_SELF_NAMES = {"我", "self", "?"}

STORY_KEYWORD_CATEGORIES = {
    "技术/工作": [
        "代码", "项目", "需求", "bug", "Bug", "接口", "前端", "后端", "数据库", "sql", "SQL", "服务",
        ".net", ".NET", "dotnet", "Dotnet", "c#", "C#", "程序", "开发", "上线", "测试", "服务器",
        "面试", "简历", "工作", "公司", "老板", "工资", "离职", "远程", "外包", "工时", "加班",
    ],
    "AI/工具": [
        "AI", "ai", "Codex", "codex", "chatgpt", "ChatGPT", "Claude", "cursor", "Cursor", "模型",
        "提示词", "token", "agent", "Agent", "MCP", "mcp", "插件", "脚本", "自动化",
    ],
    "吃喝/生活": [
        "吃", "饭", "早餐", "午饭", "晚饭", "奶茶", "咖啡", "火锅", "烧烤", "面",
        "外卖", "菜", "鸡", "肉", "水果", "喝", "饿", "胖", "减肥", "体重", "睡", "困", "起床",
    ],
    "情绪/吐槽": [
        "哈哈", "笑死", "气", "烦", "崩", "裂开", "难受", "emo", "无语", "离谱", "服了",
        "吐槽", "骂", "急", "惨", "累", "害怕", "尴尬", "开心", "快乐", "哭", "疯",
    ],
    "相亲/感情": [
        "相亲", "对象", "男朋友", "女朋友", "结婚", "恋爱", "脱单", "单身", "喜欢", "表白",
        "暧昧", "约会", "见面", "彩礼", "嫁", "娶", "红娘", "媒人", "前任", "老公", "老婆",
    ],
    "群友互动": [
        "@", "群", "大家", "你们", "哥", "姐", "老师", "大佬", "兄弟", "姐妹",
    ],
    "兴趣/娱乐": [
        "游戏", "打游戏", "王者", "无畏", "瓦", "电影", "电视剧", "小说", "音乐", "唱歌",
        "旅游", "出去", "拍照", "照片", "猫", "狗", "宠物", "车", "运动", "羽毛球", "徒步",
    ],
}


class UserError(RuntimeError):
    """Expected user-facing error."""


def default_work_dir() -> Path:
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    return home / ".codex" / "wechat-analysis-forcodex"


def resolve_work_dir(value: str | None) -> Path:
    return Path(value).expanduser().resolve() if value else default_work_dir()


def config_path(work_dir: Path) -> Path:
    return work_dir / "config.json"


def all_keys_path(work_dir: Path) -> Path:
    return work_dir / "all_keys.json"


def decrypted_dir(work_dir: Path) -> Path:
    return work_dir / "decrypted"


def reports_dir(work_dir: Path) -> Path:
    return work_dir / "reports"


def load_config(work_dir: Path) -> dict[str, Any]:
    path = config_path(work_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_config(work_dir: Path, config: dict[str, Any]) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    config_path(work_dir).write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def print_json(payload: dict[str, Any], *, stream=None) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream or sys.stdout)


def md5(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()


def sha_content(value: Any) -> str:
    if isinstance(value, bytes):
        return hashlib.sha1(value).hexdigest()
    return hashlib.sha1(str(value).encode("utf-8", errors="ignore")).hexdigest()


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)[:60] or "chat"


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def normalize_path(value: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(value))).resolve()


def detect_db_dirs() -> list[Path]:
    candidates: list[Path] = []

    appdata = os.environ.get("APPDATA")
    if appdata:
        config_dir = Path(appdata) / "Tencent" / "xwechat" / "config"
        if config_dir.exists():
            for ini_file in config_dir.glob("*.ini"):
                content = None
                for enc in ("utf-8", "gbk"):
                    try:
                        content = ini_file.read_text(encoding=enc, errors="strict").strip()
                        break
                    except UnicodeDecodeError:
                        continue
                    except OSError:
                        break
                if content:
                    root = Path(content)
                    if root.exists():
                        candidates.extend(root.glob("xwechat_files/*/db_storage"))

    roots = []
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        roots.append(Path(userprofile) / "Documents")
    home = Path.home()
    roots.append(home / "Documents")
    onedrive = os.environ.get("OneDrive")
    if onedrive:
        roots.append(Path(onedrive) / "Documents")
        roots.append(Path(onedrive) / "文档")

    for root in roots:
        if root.exists():
            candidates.extend(root.glob("xwechat_files/*/db_storage"))

    unique = []
    seen = set()
    for item in candidates:
        try:
            resolved = item.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_dir():
            continue
        seen.add(resolved)
        unique.append(resolved)

    def sort_time(path: Path) -> float:
        message_dir = path / "message"
        target = message_dir if message_dir.exists() else path
        try:
            return target.stat().st_mtime
        except OSError:
            return 0

    return sorted(unique, key=sort_time, reverse=True)


def collect_db_files(db_dir: Path) -> tuple[list[tuple[str, Path, int, str, bytes]], dict[str, list[str]]]:
    db_files = []
    salt_to_dbs: dict[str, list[str]] = {}
    for path in db_dir.rglob("*.db"):
        if path.name.endswith("-wal") or path.name.endswith("-shm"):
            continue
        size = path.stat().st_size
        if size < PAGE_SZ:
            continue
        with path.open("rb") as handle:
            page1 = handle.read(PAGE_SZ)
        rel = str(path.relative_to(db_dir))
        salt = page1[:SALT_SZ].hex()
        db_files.append((rel, path, size, salt, page1))
        salt_to_dbs.setdefault(salt, []).append(rel)
    return db_files, salt_to_dbs


def verify_raw_key(raw_key: bytes, page1: bytes) -> bool:
    salt = page1[:SALT_SZ]
    page_key = hashlib.pbkdf2_hmac("sha512", raw_key, salt, PBKDF2_ITERS, dklen=32)
    mac_salt = bytes(b ^ 0x3A for b in salt)
    mac_key = hashlib.pbkdf2_hmac("sha512", page_key, mac_salt, 2, dklen=32)
    hmac_data = page1[SALT_SZ: PAGE_SZ - RESERVE_SZ + IV_SZ]
    stored_hmac = page1[PAGE_SZ - HMAC_SZ: PAGE_SZ]
    hm = hmac_mod.new(mac_key, hmac_data, hashlib.sha512)
    hm.update(struct.pack("<I", 1))
    return hm.digest() == stored_hmac


def validate_raw_key(raw_key_hex: str) -> bytes:
    value = raw_key_hex.strip()
    if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise UserError("raw_key 必须是 64 位 hex 字符串")
    return bytes.fromhex(value)


def generate_keys(raw_key_hex: str, db_dir: Path, output: Path) -> dict[str, Any]:
    raw_key = validate_raw_key(raw_key_hex)
    if not db_dir.is_dir():
        raise UserError(f"DB 目录不存在: {db_dir}")
    db_files, salt_to_dbs = collect_db_files(db_dir)
    if not db_files:
        raise UserError(f"未找到可用数据库文件: {db_dir}")
    if not verify_raw_key(raw_key, db_files[0][4]):
        raise UserError("raw_key 验证失败。可能是 key 复制错误、微信已重启，或 db_storage 路径不匹配。")

    result: dict[str, Any] = {}
    for rel, _path, size, salt, _page1 in db_files:
        result[rel] = {"enc_key": raw_key.hex(), "salt": salt, "size_mb": round(size / 1024 / 1024, 1)}
    result["_db_dir"] = str(db_dir)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"db_count": len(db_files), "salt_count": len(salt_to_dbs), "output": str(output)}


def derive_page_key(raw_key: bytes, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha512", raw_key, salt, PBKDF2_ITERS, dklen=32)


def derive_mac_key(page_key: bytes, salt: bytes) -> bytes:
    mac_salt = bytes(b ^ 0x3A for b in salt)
    return hashlib.pbkdf2_hmac("sha512", page_key, mac_salt, 2, dklen=32)


def decrypt_page(page_key: bytes, page_data: bytes, pgno: int) -> bytes:
    iv = page_data[PAGE_SZ - RESERVE_SZ: PAGE_SZ - RESERVE_SZ + IV_SZ]
    if pgno == 1:
        encrypted = page_data[SALT_SZ: PAGE_SZ - RESERVE_SZ]
        decrypted = AES.new(page_key, AES.MODE_CBC, iv).decrypt(encrypted)
        return SQLITE_HDR + decrypted + b"\x00" * RESERVE_SZ
    encrypted = page_data[:PAGE_SZ - RESERVE_SZ]
    decrypted = AES.new(page_key, AES.MODE_CBC, iv).decrypt(encrypted)
    return decrypted + b"\x00" * RESERVE_SZ


def decrypt_database(db_path: Path, out_path: Path, raw_key: bytes) -> bool:
    file_size = db_path.stat().st_size
    total_pages = file_size // PAGE_SZ + (1 if file_size % PAGE_SZ else 0)
    with db_path.open("rb") as fin:
        page1 = fin.read(PAGE_SZ)
    if len(page1) < PAGE_SZ:
        return False
    salt = page1[:SALT_SZ]
    page_key = derive_page_key(raw_key, salt)
    mac_key = derive_mac_key(page_key, salt)
    hmac_data = page1[SALT_SZ: PAGE_SZ - RESERVE_SZ + IV_SZ]
    stored_hmac = page1[PAGE_SZ - HMAC_SZ: PAGE_SZ]
    hm = hmac_mod.new(mac_key, hmac_data, hashlib.sha512)
    hm.update(struct.pack("<I", 1))
    if hm.digest() != stored_hmac:
        return False

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with db_path.open("rb") as fin, out_path.open("wb") as fout:
        for pgno in range(1, total_pages + 1):
            page = fin.read(PAGE_SZ)
            if len(page) < PAGE_SZ:
                if not page:
                    break
                page = page + b"\x00" * (PAGE_SZ - len(page))
            fout.write(decrypt_page(page_key, page, pgno))
    return True


def load_keys(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise UserError(f"未找到 all_keys.json: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def decrypt_from_keys(keys_file: Path, output_dir: Path, only: str | None = None) -> dict[str, Any]:
    keys = load_keys(keys_file)
    db_dir_raw = keys.get("_db_dir")
    if not db_dir_raw:
        raise UserError(f"{keys_file} 缺少 _db_dir")
    db_dir = Path(db_dir_raw)

    raw_key = None
    for rel, info in keys.items():
        if not str(rel).startswith("_") and isinstance(info, dict) and info.get("enc_key"):
            raw_key = bytes.fromhex(info["enc_key"])
            break
    if not raw_key:
        raise UserError(f"{keys_file} 中没有 enc_key")

    ok = failed = skipped = 0
    failures = []
    for rel in keys:
        if str(rel).startswith("_"):
            continue
        normalized_rel = str(rel).replace("\\", os.sep).replace("/", os.sep)
        if only and only not in str(rel) and only not in normalized_rel:
            skipped += 1
            continue
        db_path = db_dir / normalized_rel
        out_path = output_dir / normalized_rel
        if not db_path.exists():
            failed += 1
            failures.append({"path": str(rel), "reason": "源文件不存在"})
            continue
        if decrypt_database(db_path, out_path, raw_key):
            ok += 1
        else:
            failed += 1
            failures.append({"path": str(rel), "reason": "HMAC 验证失败"})
    return {"ok": ok, "failed": failed, "skipped": skipped, "failures": failures, "output_dir": str(output_dir)}


def db_connect(path: Path) -> sqlite3.Connection | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def decode_db_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        for encoding in ("utf-8", "gb18030", "gbk"):
            try:
                return value.decode(encoding)
            except UnicodeDecodeError:
                continue
        return value.decode("utf-8", errors="replace")
    return str(value)


def display_from_contact(row: sqlite3.Row | None, fallback: str) -> str:
    if not row:
        return fallback
    return row["remark"] or row["nick_name"] or fallback


def read_pb_varint(data: bytes, offset: int) -> tuple[int | None, int]:
    value = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
    return None, offset


def pb_top_level_varint(data: bytes | None, field_number: int) -> int | None:
    if not data:
        return None
    offset = 0
    while offset < len(data):
        key, offset = read_pb_varint(data, offset)
        if key is None:
            return None
        current_field = key >> 3
        wire_type = key & 0x07
        if wire_type == 0:
            value, offset = read_pb_varint(data, offset)
            if current_field == field_number:
                return value
        elif wire_type == 2:
            length, offset = read_pb_varint(data, offset)
            if length is None:
                return None
            offset += length
        elif wire_type == 1:
            offset += 8
        elif wire_type == 5:
            offset += 4
        else:
            return None
    return None


def gender_from_extra_buffer(extra_buffer: bytes | None) -> tuple[str, str]:
    value = pb_top_level_varint(extra_buffer, 2)
    if value == 1:
        return "male", "wechat"
    if value == 2:
        return "female", "wechat"
    if value == 0:
        return "unknown", "wechat"
    return "unknown", "unknown"


def load_contact_map(dec_dir: Path) -> dict[str, str]:
    conn = db_connect(dec_dir / "contact" / "contact.db")
    names: dict[str, str] = {}
    if not conn:
        return names
    try:
        for row in conn.execute("SELECT username, nick_name, remark FROM contact"):
            names[row["username"]] = row["remark"] or row["nick_name"] or row["username"]
    finally:
        conn.close()
    return names


def load_group_member_display_map(dec_dir: Path, chat_username: str) -> dict[str, str]:
    if not chat_username.endswith("@chatroom"):
        return {}
    contact_db = dec_dir / "contact" / "contact.db"
    contact_fts_db = dec_dir / "contact" / "contact_fts.db"
    if not contact_db.exists() or not contact_fts_db.exists():
        return {}

    id_to_username: dict[int, str] = {}
    username_to_id: dict[str, int] = {}
    contact_conn = sqlite3.connect(str(contact_db))
    contact_conn.row_factory = sqlite3.Row
    contact_conn.text_factory = bytes
    try:
        for row in contact_conn.execute("SELECT id, username FROM contact"):
            username = decode_db_text(row["username"])
            if not username:
                continue
            contact_id = int(row["id"])
            id_to_username[contact_id] = username
            username_to_id[username] = contact_id
    finally:
        contact_conn.close()

    room_id = username_to_id.get(chat_username)
    if not room_id:
        return {}

    fts_conn = sqlite3.connect(str(contact_fts_db))
    fts_conn.row_factory = sqlite3.Row
    fts_conn.text_factory = bytes
    try:
        hit = fts_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chatroom_member_fts_v3'"
        ).fetchone()
        if not hit:
            return {}
        names: dict[str, str] = {}
        for row in fts_conn.execute(
            "SELECT a_group_remark, member_id FROM chatroom_member_fts_v3 WHERE room_id=?",
            (room_id,),
        ):
            member_username = id_to_username.get(int(row["member_id"] or 0), "")
            group_display = decode_db_text(row["a_group_remark"]).strip()
            if member_username and group_display:
                names[member_username] = group_display
        return names
    finally:
        fts_conn.close()


def add_group_member_profile_aliases(
    group_member_names: dict[str, str],
    by_username: dict[str, dict[str, Any]],
    by_display: dict[str, dict[str, Any]],
) -> None:
    for username, group_display in group_member_names.items():
        profile = by_username.get(username)
        if not profile:
            continue
        group_profile = {**profile, "name": group_display, "group_display_name": group_display}
        by_username[username] = group_profile
        by_display[group_display] = group_profile


def load_contact_profiles(dec_dir: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    conn = db_connect(dec_dir / "contact" / "contact.db")
    by_username: dict[str, dict[str, Any]] = {}
    by_display: dict[str, dict[str, Any]] = {}
    if not conn:
        return by_username, by_display
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(contact)").fetchall()}
        select_columns = ["username", "nick_name", "remark"]
        if "extra_buffer" in columns:
            select_columns.append("extra_buffer")
        sql = "SELECT " + ", ".join(f"[{col}]" for col in select_columns) + " FROM contact"
        if "local_type" in columns:
            sql += " WHERE local_type != 3"
        rows = conn.execute(sql).fetchall()
        for row in rows:
            data = dict(zip(select_columns, row))
            username = data.get("username") or ""
            nick_name = data.get("nick_name") or ""
            remark = data.get("remark") or ""
            display = remark or nick_name or username
            gender, gender_source = gender_from_extra_buffer(data.get("extra_buffer"))
            profile = {
                "username": username,
                "name": display,
                "nick_name": nick_name,
                "remark": remark,
                "gender": gender,
                "gender_source": gender_source,
            }
            if username:
                by_username[username] = profile
            for key in {display, nick_name, remark}:
                if key and key not in by_display:
                    by_display[key] = profile
    finally:
        conn.close()
    return by_username, by_display


def get_contact_display(dec_dir: Path, username: str) -> str:
    conn = db_connect(dec_dir / "contact" / "contact.db")
    if not conn:
        return username
    try:
        row = conn.execute("SELECT nick_name, remark FROM contact WHERE username=?", (username,)).fetchone()
        return display_from_contact(row, username)
    finally:
        conn.close()


def list_sessions(dec_dir: Path, name_filter: str | None = None) -> list[dict[str, Any]]:
    session_conn = db_connect(dec_dir / "session" / "session.db")
    contact_conn = db_connect(dec_dir / "contact" / "contact.db")
    if not session_conn:
        raise UserError("未找到 session.db，请先执行 decrypt")
    rows = []
    try:
        sql = "SELECT username, type, summary, last_timestamp, sort_timestamp, last_sender_display_name FROM SessionTable"
        sql += " ORDER BY sort_timestamp DESC LIMIT 500"
        for row in session_conn.execute(sql):
            username = row["username"]
            display = username
            if contact_conn:
                contact = contact_conn.execute(
                    "SELECT nick_name, remark FROM contact WHERE username=?",
                    (username,),
                ).fetchone()
                display = display_from_contact(contact, username)
            if name_filter and name_filter not in username and name_filter not in display and name_filter not in (row["summary"] or ""):
                continue
            ts = row["last_timestamp"]
            last_time = ""
            if ts:
                try:
                    last_time = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M")
                except (OSError, ValueError):
                    last_time = ""
            rows.append({
                "username": username,
                "display": display,
                "kind": "group" if str(username).endswith("@chatroom") else "single",
                "last_time": last_time,
                "summary": (row["summary"] or "").replace("\n", " "),
            })
    finally:
        session_conn.close()
        if contact_conn:
            contact_conn.close()
    return rows


def find_chat(dec_dir: Path, chat: str) -> tuple[str, str, list[dict[str, str]]]:
    contact_conn = db_connect(dec_dir / "contact" / "contact.db")
    session_conn = db_connect(dec_dir / "session" / "session.db")
    candidates: list[dict[str, str]] = []

    def add(username: str, display: str, source: str) -> None:
        if not username:
            return
        if any(item["username"] == username for item in candidates):
            return
        candidates.append({"username": username, "display": display or username, "source": source})

    try:
        if contact_conn:
            exact = contact_conn.execute(
                "SELECT username, nick_name, remark FROM contact WHERE username=? OR nick_name=? OR remark=?",
                (chat, chat, chat),
            ).fetchall()
            for row in exact:
                add(row["username"], display_from_contact(row, row["username"]), "contact-exact")
            if not candidates:
                like = f"%{chat}%"
                fuzzy = contact_conn.execute(
                    "SELECT username, nick_name, remark FROM contact WHERE username LIKE ? OR nick_name LIKE ? OR remark LIKE ?",
                    (like, like, like),
                ).fetchall()
                for row in fuzzy:
                    add(row["username"], display_from_contact(row, row["username"]), "contact-fuzzy")
        if session_conn:
            exact = session_conn.execute("SELECT username FROM SessionTable WHERE username=?", (chat,)).fetchall()
            for row in exact:
                add(row["username"], get_contact_display(dec_dir, row["username"]), "session-exact")
            if not candidates:
                like = f"%{chat}%"
                fuzzy = session_conn.execute(
                    "SELECT username, summary FROM SessionTable WHERE username LIKE ? OR summary LIKE ?",
                    (like, like),
                ).fetchall()
                for row in fuzzy:
                    add(row["username"], get_contact_display(dec_dir, row["username"]), "session-fuzzy")
    finally:
        if contact_conn:
            contact_conn.close()
        if session_conn:
            session_conn.close()

    exact_matches = [c for c in candidates if c["username"] == chat or c["display"] == chat]
    if len(exact_matches) == 1:
        chosen = exact_matches[0]
        return chosen["username"], chosen["display"], candidates
    if len(candidates) == 1:
        chosen = candidates[0]
        return chosen["username"], chosen["display"], candidates
    return "", "", candidates


def try_decode(data: Any) -> str | None:
    if isinstance(data, str):
        return data
    if isinstance(data, bytes):
        if len(data) > 2 and data[:2] == b"(\xb5":
            sep = data.find(b":\n")
            if 0 <= sep < 100:
                decoded = data[sep + 2:].decode("utf-8", errors="ignore")
                if sum(1 for ch in decoded if "\u4e00" <= ch <= "\u9fff") >= 3 or len(decoded.strip()) > 10:
                    return strip_binary(decoded)
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None
    return None


def strip_binary(text: str) -> str:
    result = []
    consecutive_ctrl = 0
    for ch in text:
        cp = ord(ch)
        if ch in "\n\r\t" or 32 <= cp <= 126 or 0x4E00 <= cp <= 0x9FFF or 0x3000 <= cp <= 0x30FF or 0xFF00 <= cp <= 0xFFEF or 0x2000 <= cp <= 0x206F:
            result.append(ch)
            consecutive_ctrl = 0
        elif cp < 32 or 0x7F <= cp <= 0x9F:
            consecutive_ctrl += 1
            if consecutive_ctrl >= 3:
                break
        else:
            result.append(ch)
            consecutive_ctrl = 0
    return "".join(result).rstrip()


def type_label(local_type: int) -> str:
    labels = {
        3: "[图片]",
        34: "[语音]",
        42: "[名片]",
        43: "[音视频通话]",
        47: "[引用回复]",
        48: "[位置]",
        49: "[分享/链接]",
        50: "[音视频通话]",
        62: "[小视频]",
        66: "[第三方链接]",
        268435456: "[红包]",
        10000: "[系统消息]",
        10002: "[系统消息]",
    }
    if local_type in labels:
        return labels[local_type]
    if local_type > 1000000:
        return "[富媒体消息]"
    return f"[消息类型 {local_type}]"


def parse_content(message: dict[str, Any]) -> str:
    content = message.get("message_content")
    local_type = int(message.get("local_type") or 0)
    if content in (None, b"", ""):
        return ""
    if isinstance(content, bytes):
        text = try_decode(content)
        if text is None:
            return type_label(local_type)
        content = text
    if isinstance(content, str) and ":\n" in content and not content.startswith("<") and not content.startswith("<?xml"):
        sender, text = content.split(":\n", 1)
        if len(sender) < 80 and "\n" not in sender:
            return text
    return str(content)


def parse_sender(message: dict[str, Any]) -> str | None:
    content = message.get("message_content")
    if isinstance(content, bytes) and content[:2] == b"(\xb5":
        wxid_start = content.find(b"wxid_")
        if wxid_start >= 0:
            sep = content.find(b":\n", wxid_start)
            if 0 <= sep - wxid_start < 80:
                try:
                    wxid = content[wxid_start:sep].decode("utf-8")
                    if "\n" not in wxid:
                        return wxid
                except UnicodeDecodeError:
                    pass
        return None
    text = try_decode(content) if isinstance(content, bytes) else content
    if text and ":\n" in text and not str(text).startswith("<") and not str(text).startswith("<?xml"):
        sender, _body = str(text).split(":\n", 1)
        if len(sender) < 80 and "\n" not in sender:
            return sender
    source = message.get("source")
    if isinstance(source, bytes):
        source_text = try_decode(source)
        if source_text and ":\n" in source_text:
            sender, _body = source_text.split(":\n", 1)
            if len(sender) < 80:
                return sender
    return None


def infer_self_name(raw_messages: list[dict[str, Any]], contact_names: dict[str, str]) -> str | None:
    for message in raw_messages:
        if int(message.get("real_sender_id") or 0) != 2:
            continue
        sender = parse_sender(message)
        if sender and sender in contact_names:
            name = contact_names[sender]
            if name and name not in FORBIDDEN_SELF_NAMES:
                return name
        if sender and sender not in FORBIDDEN_SELF_NAMES:
            return sender
    return None


def message_table(username: str) -> str:
    return f"Msg_{md5(username)}"


def query_raw_messages(
    dec_dir: Path,
    username: str,
    start: datetime | None = None,
    end_exclusive: datetime | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    msg_dir = dec_dir / "message"
    if not msg_dir.exists():
        raise UserError("未找到 decrypted/message，请先执行 decrypt")
    table = message_table(username)
    raw: list[dict[str, Any]] = []
    source_dbs: list[str] = []
    for db_path in sorted(msg_dir.glob("message_*.db")):
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            hit = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if not hit:
                continue
            where = []
            params: list[int] = []
            if start:
                where.append("create_time >= ?")
                params.append(int(start.timestamp()))
            if end_exclusive:
                where.append("create_time < ?")
                params.append(int(end_exclusive.timestamp()))
            sql = f'SELECT * FROM "{table}"'
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY create_time ASC"
            rows = conn.execute(sql, params).fetchall()
            if rows:
                source_dbs.append(db_path.name)
            for row in rows:
                item = dict(row)
                item["_source_db"] = db_path.name
                raw.append(item)
        finally:
            conn.close()

    deduped: dict[Any, dict[str, Any]] = {}
    for item in raw:
        key = item.get("server_id") or (
            item.get("local_id"),
            item.get("create_time"),
            item.get("real_sender_id"),
            sha_content(item.get("message_content")),
        )
        deduped[key] = item
    return sorted(deduped.values(), key=lambda m: (m.get("create_time") or 0, m.get("local_id") or 0)), source_dbs


def build_real_sender_map(dec_dir: Path, username: str) -> dict[int, str]:
    msg_dir = dec_dir / "message"
    if not msg_dir.exists():
        return {}
    table = message_table(username)
    candidates: dict[int, Counter[str]] = {}
    for db_path in sorted(msg_dir.glob("message_*.db")):
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            hit = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if not hit:
                continue
            for row in conn.execute(f'SELECT real_sender_id, message_content, source FROM "{table}"'):
                real_sender_id = int(row["real_sender_id"] or 0)
                sender = parse_sender(dict(row))
                if not real_sender_id or not sender or sender in FORBIDDEN_SELF_NAMES:
                    continue
                candidates.setdefault(real_sender_id, Counter())[sender] += 1
        finally:
            conn.close()
    return {real_id: counter.most_common(1)[0][0] for real_id, counter in candidates.items()}


def is_system_message(message: dict[str, Any], text: str | None = None) -> bool:
    local_type = int(message.get("local_type") or 0)
    if local_type in SYSTEM_LOCAL_TYPES:
        return True
    value = text if text is not None else parse_content(message)
    return compact_text(value).startswith("[系统消息]")


def requires_self_name(message: dict[str, Any], real_sender_map: dict[int, str], is_group: bool) -> bool:
    if parse_sender(message):
        return False
    real_sender_id = int(message.get("real_sender_id") or 0)
    if real_sender_id == 2:
        return True
    if real_sender_id in real_sender_map:
        return False
    if is_system_message(message):
        return False
    return is_group


def normalize_messages(
    raw_messages: list[dict[str, Any]],
    sender_names: dict[str, str],
    self_name: str,
    chat_username: str,
    chat_display: str,
    real_sender_map: dict[int, str],
) -> list[dict[str, Any]]:
    normalized = []
    is_group = chat_username.endswith("@chatroom")
    for message in raw_messages:
        local_type = int(message.get("local_type") or 0)
        text = parse_content(message)
        if not text and local_type != 1:
            continue
        sender_id = parse_sender(message)
        real_sender_id = int(message.get("real_sender_id") or 0)
        if sender_id:
            display = sender_names.get(sender_id, sender_id)
        elif real_sender_id in real_sender_map:
            sender_id = real_sender_map[real_sender_id]
            display = sender_names.get(sender_id, sender_id)
        elif real_sender_id == 2:
            if not self_name:
                raise UserError("记录中存在自己发送的消息，但缺少 self_name。请补充 --self-name。")
            display = self_name
            sender_id = "self"
        elif is_system_message(message, text):
            display = "系统"
            sender_id = "system"
        elif is_group:
            if not self_name:
                raise UserError("群聊记录中存在无发送者前缀的自己消息。请补充 --self-name。")
            display = self_name
            sender_id = "self"
        else:
            display = chat_display
            sender_id = "unknown"
        if display in FORBIDDEN_SELF_NAMES:
            raise UserError("导出结果中出现了禁止的自己名称“我”，请用 --self-name 指定真实微信名或群内名。")
        ts = int(message.get("create_time") or 0)
        dt = datetime.fromtimestamp(ts) if ts else None
        normalized.append({
            "time": dt,
            "time_text": dt.strftime("%Y-%m-%d %H:%M") if dt else "",
            "sender": display,
            "sender_id": sender_id,
            "text": compact_text(text),
            "local_type": local_type,
        })
    return normalized


def compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def build_speaker_profiles(
    messages: list[dict[str, Any]],
    by_username: dict[str, dict[str, Any]],
    by_display: dict[str, dict[str, Any]],
    limit: int = 30,
) -> list[dict[str, Any]]:
    by_sender = Counter(m["sender"] for m in messages)
    sender_ids: dict[str, str] = {}
    for message in messages:
        sender = message.get("sender")
        sender_id = message.get("sender_id")
        if sender and sender_id and sender not in sender_ids:
            sender_ids[sender] = sender_id

    profiles = []
    for sender, count in by_sender.most_common(limit):
        sender_id = sender_ids.get(sender, "")
        profile = by_username.get(sender_id) or by_display.get(sender) or {}
        gender = profile.get("gender") or "unknown"
        gender_source = profile.get("gender_source") or "unknown"
        profiles.append({
            "name": sender,
            "username": profile.get("username") or (sender_id if sender_id not in {"self", "system", "unknown"} else ""),
            "message_count": count,
            "gender": gender,
            "gender_source": gender_source,
        })
    return profiles


def contains_alias(value: str, aliases: list[str]) -> bool:
    text = (value or "").lower()
    return any(alias.lower() in text for alias in aliases if alias)


def message_score(message: dict[str, Any]) -> int:
    text = message.get("text") or ""
    score = min(len(text), 160)
    for marker in ("哈哈", "笑死", "离谱", "相亲", "工作", "AI", "Codex", "bug", "吃", "群", "服了"):
        if marker in text:
            score += 18
    if message.get("local_type") == 1:
        score += 6
    return score


def serialize_story_message(message: dict[str, Any], limit: int = 260) -> dict[str, Any]:
    text = compact_text(message.get("text") or "")
    if len(text) > limit:
        text = text[:limit] + "..."
    return {
        "time": message.get("time_text") or "",
        "sender": message.get("sender") or "",
        "sender_id": message.get("sender_id") or "",
        "text": text,
        "local_type": message.get("local_type"),
    }


def build_story_windows(
    messages: list[dict[str, Any]],
    hit_indexes: set[int],
    *,
    before: int = 8,
    after: int = 12,
    limit: int = 180,
) -> list[dict[str, Any]]:
    windows = []
    consumed_until = -1
    for index in sorted(hit_indexes):
        start = max(0, index - before)
        end = min(len(messages), index + after + 1)
        if start <= consumed_until:
            if windows and end > windows[-1]["end_index"]:
                windows[-1]["end_index"] = end
                items = messages[windows[-1]["start_index"]:end]
                windows[-1]["range"] = [items[0]["time_text"], items[-1]["time_text"]]
                windows[-1]["items"] = [serialize_story_message(item) for item in items]
                consumed_until = end
            continue
        items = messages[start:end]
        windows.append({
            "start_index": start,
            "end_index": end,
            "range": [items[0]["time_text"], items[-1]["time_text"]],
            "items": [serialize_story_message(item) for item in items],
        })
        consumed_until = end
        if len(windows) >= limit:
            break
    return windows


def category_counts(messages: list[dict[str, Any]]) -> list[tuple[str, int]]:
    counts = []
    for category, keywords in STORY_KEYWORD_CATEGORIES.items():
        count = 0
        for message in messages:
            text = message.get("text") or ""
            if any(keyword in text for keyword in keywords):
                count += 1
        counts.append((category, count))
    return sorted(counts, key=lambda item: item[1], reverse=True)


def find_story_profile(
    target: str,
    aliases: list[str],
    messages: list[dict[str, Any]],
    by_username: dict[str, dict[str, Any]],
    by_display: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    for alias in aliases:
        if alias in by_display:
            return by_display[alias]
    for message in messages:
        sender = message.get("sender") or ""
        if not contains_alias(sender, aliases):
            continue
        sender_id = message.get("sender_id") or ""
        profile = by_username.get(sender_id) or by_display.get(sender)
        if profile:
            return profile
        return {
            "username": sender_id if sender_id not in {"self", "system", "unknown"} else "",
            "name": sender,
            "nick_name": "",
            "remark": "",
            "gender": "unknown",
            "gender_source": "unknown",
        }
    return by_display.get(target)


def write_story_outputs(
    work_dir: Path,
    chat_display: str,
    username: str,
    target_type: str,
    target: str,
    aliases: list[str],
    messages: list[dict[str, Any]],
    source_dbs: list[str],
    profile: dict[str, Any] | None,
) -> dict[str, str]:
    out_dir = reports_dir(work_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if messages:
        start_s = messages[0]["time"].strftime("%Y-%m-%d") if messages[0].get("time") else "unknown"
        end_s = messages[-1]["time"].strftime("%Y-%m-%d") if messages[-1].get("time") else "unknown"
    else:
        start_s = end_s = "empty"

    target_messages = []
    mention_messages = []
    hit_indexes: set[int] = set()
    for index, message in enumerate(messages):
        sender = message.get("sender") or ""
        text = message.get("text") or ""
        sender_hit = target_type == "person" and contains_alias(sender, aliases)
        text_hit = contains_alias(text, aliases)
        if sender_hit:
            target_messages.append(message)
        if text_hit and not sender_hit:
            mention_messages.append(message)
        if target_type == "topic" and text_hit:
            target_messages.append(message)
        if sender_hit or text_hit:
            hit_indexes.add(index)

    if target_type == "person":
        top_days = Counter(m["time"].strftime("%Y-%m-%d") for m in target_messages if m.get("time"))
        hot_days = {day for day, _count in top_days.most_common(12)}
        for index, message in enumerate(messages):
            if not message.get("time"):
                continue
            if message["time"].strftime("%Y-%m-%d") not in hot_days:
                continue
            if contains_alias(message.get("sender") or "", aliases) and message_score(message) >= 34:
                hit_indexes.add(index)
    else:
        top_days = Counter(m["time"].strftime("%Y-%m-%d") for m in target_messages if m.get("time"))

    windows = build_story_windows(messages, hit_indexes)
    topic_counts = category_counts(target_messages or [item for window in windows for item in window["items"]])
    gender = (profile or {}).get("gender") or "unknown"
    gender_source = (profile or {}).get("gender_source") or "unknown"
    base = f"{start_s}_to_{end_s}_{safe_name(chat_display)}_{safe_name(target)}"
    md_path = out_dir / f"story_{base}.md"
    json_path = out_dir / f"story_{base}.json"

    story = {
        "chat": chat_display,
        "username": username,
        "target_type": target_type,
        "target": target,
        "aliases": aliases,
        "profile": profile or None,
        "gender": gender,
        "gender_source": gender_source,
        "message_count": len(messages),
        "target_message_count": len(target_messages),
        "mention_message_count": len(mention_messages),
        "top_days": top_days.most_common(30),
        "topic_counts": topic_counts,
        "relevant_windows": windows,
        "first_time": messages[0]["time_text"] if messages else "",
        "last_time": messages[-1]["time_text"] if messages else "",
        "source_dbs": sorted(source_dbs),
        "markdown_path": str(md_path),
    }
    json_path.write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# {chat_display} - {target} 故事线素材",
        "",
        f"- 目标类型: {target_type}",
        f"- 别名: {'、'.join(aliases)}",
        f"- 群消息范围: {story['first_time']} 至 {story['last_time']}",
        f"- 群消息数: {len(messages)}",
        f"- 目标命中数: {len(target_messages)}",
        f"- 被提及数: {len(mention_messages)}",
        f"- 性别: {gender} ({gender_source})",
        "",
        "## 高活跃日期",
    ]
    for day, count in top_days.most_common(20):
        lines.append(f"- {day}: {count}")
    lines.extend(["", "## 主题计数"])
    for category, count in topic_counts:
        if count:
            lines.append(f"- {category}: {count}")
    lines.extend(["", "## 相关上下文窗口"])
    for window in windows:
        lines.append("")
        lines.append(f"### {window['range'][0]} - {window['range'][1]}")
        for item in window["items"]:
            marker = " ★" if target_type == "person" and contains_alias(item["sender"], aliases) else ""
            lines.append(f"- [{item['time']}] {item['sender']}{marker}: {item['text']}")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {"markdown": str(md_path), "json": str(json_path)}


def write_outputs(
    work_dir: Path,
    chat_display: str,
    username: str,
    start: datetime,
    end_inclusive: datetime,
    messages: list[dict[str, Any]],
    source_dbs: list[str],
    self_name: str,
    contact_profiles_by_username: dict[str, dict[str, Any]],
    contact_profiles_by_display: dict[str, dict[str, Any]],
) -> dict[str, str]:
    out_dir = reports_dir(work_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    start_s = start.strftime("%Y-%m-%d")
    end_s = end_inclusive.strftime("%Y-%m-%d")
    base = f"{start_s}_to_{end_s}_{safe_name(chat_display)}"
    md_path = out_dir / f"report_{base}.md"
    stats_path = out_dir / f"stats_{base}.json"

    by_day = Counter(m["time"].strftime("%Y-%m-%d") for m in messages if m.get("time"))
    by_sender = Counter(m["sender"] for m in messages)
    by_hour = Counter(m["time"].strftime("%H") for m in messages if m.get("time"))
    speaker_profiles = build_speaker_profiles(messages, contact_profiles_by_username, contact_profiles_by_display)

    lines = [
        f"# 微信聊天记录 - {chat_display} - {start_s}_to_{end_s}",
        "",
        f"_消息数: {len(messages)} 条_",
        "",
        "## 按天消息数",
        "",
    ]
    for day, count in sorted(by_day.items()):
        lines.append(f"- {day}: {count}")
    lines.extend(["", "## 活跃成员 Top 20", ""])
    for sender, count in by_sender.most_common(20):
        lines.append(f"- {sender}: {count}")
    lines.extend(["", "## 聊天记录", "", "```"])
    for item in messages:
        if item["text"]:
            lines.append(f'[{item["time_text"]}] {item["sender"]}: {item["text"]}')
    lines.append("```")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    stats = {
        "chat": chat_display,
        "username": username,
        "start": start_s,
        "end": end_s,
        "message_count": len(messages),
        "self_name": self_name,
        "by_day": dict(sorted(by_day.items())),
        "top_senders": by_sender.most_common(30),
        "speaker_profiles": speaker_profiles,
        "by_hour": dict(sorted(by_hour.items())),
        "source_dbs": sorted(source_dbs),
        "markdown_path": str(md_path),
    }
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"markdown": str(md_path), "json": str(stats_path)}


def cmd_doctor(args: argparse.Namespace) -> int:
    checks = []
    try:
        import Crypto.Cipher.AES as _aes  # noqa: F401
        checks.append({"name": "pycryptodome", "ok": True})
    except Exception as exc:
        checks.append({"name": "pycryptodome", "ok": False, "detail": str(exc)})
    work_dir = resolve_work_dir(args.work_dir)
    cfg = load_config(work_dir)
    checks.extend([
        {"name": "work_dir", "ok": True, "path": str(work_dir)},
        {"name": "config", "ok": bool(cfg), "path": str(config_path(work_dir))},
        {"name": "all_keys", "ok": all_keys_path(work_dir).exists(), "path": str(all_keys_path(work_dir))},
        {"name": "decrypted", "ok": decrypted_dir(work_dir).exists(), "path": str(decrypted_dir(work_dir))},
    ])
    ok = all(item.get("ok") for item in checks if item["name"] in {"pycryptodome", "work_dir"})
    print_json({"ok": ok, "checks": checks})
    return 0 if ok else 1


def cmd_setup(args: argparse.Namespace) -> int:
    work_dir = resolve_work_dir(args.work_dir)
    db_dir = normalize_path(args.db_dir) if args.db_dir else None
    if not db_dir:
        candidates = detect_db_dirs()
        if not candidates:
            raise UserError("未自动检测到 db_storage，请使用 --db-dir 指定。")
        if len(candidates) > 1:
            print_json({"error": "检测到多个 db_storage 候选，请使用 --db-dir 指定", "candidates": [str(c) for c in candidates]}, stream=sys.stderr)
            return 2
        db_dir = candidates[0]
    info = generate_keys(args.raw_key, db_dir, all_keys_path(work_dir))
    cfg = load_config(work_dir)
    cfg["db_dir"] = str(db_dir)
    if args.self_name:
        if args.self_name in FORBIDDEN_SELF_NAMES:
            raise UserError("--self-name 不能是 我/self/?，请使用真实微信名或群内名。")
        cfg["self_name"] = args.self_name
    save_config(work_dir, cfg)
    print_json({"ok": True, "work_dir": str(work_dir), "db_dir": str(db_dir), **info})
    return 0


def cmd_decrypt(args: argparse.Namespace) -> int:
    work_dir = resolve_work_dir(args.work_dir)
    result = decrypt_from_keys(all_keys_path(work_dir), decrypted_dir(work_dir), args.only)
    print_json(result)
    return 1 if result["failed"] else 0


def cmd_sessions(args: argparse.Namespace) -> int:
    work_dir = resolve_work_dir(args.work_dir)
    rows = list_sessions(decrypted_dir(work_dir), args.filter)
    print_json({"count": len(rows), "sessions": rows})
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    work_dir = resolve_work_dir(args.work_dir)
    cfg = load_config(work_dir)
    self_name = args.self_name or cfg.get("self_name")
    if self_name in FORBIDDEN_SELF_NAMES:
        raise UserError("self_name 不能是 我/self/?，请使用真实微信名或群内名。")

    start = parse_date(args.start)
    end_inclusive = parse_date(args.end)
    end_exclusive = end_inclusive + timedelta(days=1)
    dec_dir = decrypted_dir(work_dir)
    username, display, candidates = find_chat(dec_dir, args.chat)
    if not username:
        print_json({"error": "未能唯一匹配聊天对象", "chat": args.chat, "candidates": candidates[:30]}, stream=sys.stderr)
        return 2
    raw, source_dbs = query_raw_messages(dec_dir, username, start, end_exclusive)
    contact_names = load_contact_map(dec_dir)
    contact_profiles_by_username, contact_profiles_by_display = load_contact_profiles(dec_dir)
    real_sender_map = build_real_sender_map(dec_dir, username)
    is_group = username.endswith("@chatroom")
    group_member_names = load_group_member_display_map(dec_dir, username) if is_group else {}
    sender_names = {**contact_names, **group_member_names}
    add_group_member_profile_aliases(
        group_member_names,
        contact_profiles_by_username,
        contact_profiles_by_display,
    )

    if any(requires_self_name(m, real_sender_map, is_group) for m in raw):
        if not self_name:
            inferred = infer_self_name(raw, sender_names)
            self_name = inferred
        if not self_name or self_name in FORBIDDEN_SELF_NAMES:
            raise UserError("记录中存在自己发送的消息，但无法解析自己的微信名。请补充 --self-name。")
    elif not self_name:
        inferred = infer_self_name(raw, sender_names)
        self_name = inferred or ""

    messages = normalize_messages(raw, sender_names, self_name or "", username, display, real_sender_map)
    outputs = write_outputs(
        work_dir,
        display,
        username,
        start,
        end_inclusive,
        messages,
        source_dbs,
        self_name or "",
        contact_profiles_by_username,
        contact_profiles_by_display,
    )
    print_json({
        "chat": display,
        "username": username,
        "message_count": len(messages),
        "self_name": self_name,
        "source_dbs": sorted(source_dbs),
        "outputs": outputs,
    })
    return 0


def cmd_story(args: argparse.Namespace) -> int:
    work_dir = resolve_work_dir(args.work_dir)
    cfg = load_config(work_dir)
    self_name = args.self_name or cfg.get("self_name")
    if self_name in FORBIDDEN_SELF_NAMES:
        raise UserError("self_name 不能是 我/self/?，请使用真实微信名或群内名。")

    start = parse_date(args.start) if args.start else None
    end_inclusive = parse_date(args.end) if args.end else None
    end_exclusive = end_inclusive + timedelta(days=1) if end_inclusive else None
    if start and end_inclusive and end_inclusive < start:
        raise UserError("--end 不能早于 --start")

    dec_dir = decrypted_dir(work_dir)
    username, display, candidates = find_chat(dec_dir, args.chat)
    if not username:
        print_json({"error": "未能唯一匹配聊天对象", "chat": args.chat, "candidates": candidates[:30]}, stream=sys.stderr)
        return 2

    raw, source_dbs = query_raw_messages(dec_dir, username, start, end_exclusive)
    contact_names = load_contact_map(dec_dir)
    contact_profiles_by_username, contact_profiles_by_display = load_contact_profiles(dec_dir)
    real_sender_map = build_real_sender_map(dec_dir, username)
    is_group = username.endswith("@chatroom")
    group_member_names = load_group_member_display_map(dec_dir, username) if is_group else {}
    sender_names = {**contact_names, **group_member_names}
    add_group_member_profile_aliases(
        group_member_names,
        contact_profiles_by_username,
        contact_profiles_by_display,
    )

    if any(requires_self_name(m, real_sender_map, is_group) for m in raw):
        if not self_name:
            inferred = infer_self_name(raw, sender_names)
            self_name = inferred
        if not self_name or self_name in FORBIDDEN_SELF_NAMES:
            raise UserError("记录中存在自己发送的消息，但无法解析自己的微信名。请补充 --self-name。")
    elif not self_name:
        inferred = infer_self_name(raw, sender_names)
        self_name = inferred or ""

    messages = normalize_messages(raw, sender_names, self_name or "", username, display, real_sender_map)
    target_type = "person" if args.person else "topic"
    target = args.person or args.topic
    aliases = []
    for value in [target, *(args.alias or [])]:
        value = compact_text(value)
        if value and value not in aliases:
            aliases.append(value)
    profile = None
    if target_type == "person":
        profile = find_story_profile(target, aliases, messages, contact_profiles_by_username, contact_profiles_by_display)

    outputs = write_story_outputs(
        work_dir,
        display,
        username,
        target_type,
        target,
        aliases,
        messages,
        source_dbs,
        profile,
    )
    print_json({
        "chat": display,
        "username": username,
        "target_type": target_type,
        "target": target,
        "aliases": aliases,
        "message_count": len(messages),
        "outputs": outputs,
    })
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="独立微信聊天解密、导出与总结辅助工具")
    parser.add_argument("--work-dir", help="工作目录，默认 USERPROFILE\\.codex\\wechat-analysis-forcodex")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="检查运行环境")
    doctor.add_argument("--work-dir", default=argparse.SUPPRESS, help="工作目录，默认 USERPROFILE\\.codex\\wechat-analysis-forcodex")
    doctor.set_defaults(func=cmd_doctor)

    setup = sub.add_parser("setup", help="校验 raw_key 并生成 all_keys.json")
    setup.add_argument("--work-dir", default=argparse.SUPPRESS, help="工作目录，默认 USERPROFILE\\.codex\\wechat-analysis-forcodex")
    setup.add_argument("--raw-key", required=True, help="64 位 hex raw_key")
    setup.add_argument("--db-dir", help="微信 db_storage 路径；不传则自动检测")
    setup.add_argument("--self-name", help="自己的微信名或群内名，禁止使用“我”")
    setup.set_defaults(func=cmd_setup)

    decrypt = sub.add_parser("decrypt", help="解密数据库")
    decrypt.add_argument("--work-dir", default=argparse.SUPPRESS, help="工作目录，默认 USERPROFILE\\.codex\\wechat-analysis-forcodex")
    decrypt.add_argument("--only", help="只解密包含该字符串的相对路径")
    decrypt.set_defaults(func=cmd_decrypt)

    sessions = sub.add_parser("sessions", help="列出群聊和私聊候选")
    sessions.add_argument("--work-dir", default=argparse.SUPPRESS, help="工作目录，默认 USERPROFILE\\.codex\\wechat-analysis-forcodex")
    sessions.add_argument("--filter", help="按名称、username 或摘要过滤")
    sessions.set_defaults(func=cmd_sessions)

    export = sub.add_parser("export", help="导出指定聊天对象的日期范围记录")
    export.add_argument("--work-dir", default=argparse.SUPPRESS, help="工作目录，默认 USERPROFILE\\.codex\\wechat-analysis-forcodex")
    export.add_argument("--chat", required=True, help="群聊或私聊名称、备注、昵称或 username")
    export.add_argument("--start", required=True, help="开始日期 YYYY-MM-DD")
    export.add_argument("--end", required=True, help="结束日期 YYYY-MM-DD，包含当天")
    export.add_argument("--self-name", help="自己的微信名或群内名，优先于配置")
    export.set_defaults(func=cmd_export)

    story = sub.add_parser("story", help="抽取某个人或话题的群聊故事线素材")
    story.add_argument("--work-dir", default=argparse.SUPPRESS, help="工作目录，默认 USERPROFILE\\.codex\\wechat-analysis-forcodex")
    story.add_argument("--chat", required=True, help="群聊或私聊名称、备注、昵称或 username")
    target = story.add_mutually_exclusive_group(required=True)
    target.add_argument("--person", help="要总结的成员名、群昵称、备注或昵称")
    target.add_argument("--topic", help="要总结的话题、八卦或事件关键词")
    story.add_argument("--alias", action="append", help="补充别名、群昵称、外号或相关关键词；可重复传入")
    story.add_argument("--start", help="开始日期 YYYY-MM-DD；不传则从该会话最早消息开始")
    story.add_argument("--end", help="结束日期 YYYY-MM-DD，包含当天；不传则到该会话最新消息")
    story.add_argument("--self-name", help="自己的微信名或群内名，优先于配置")
    story.set_defaults(func=cmd_story)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "decrypt":
            global AES
            try:
                from Crypto.Cipher import AES as _AES
            except Exception as exc:
                raise UserError("缺少 pycryptodome，请先安装：python -m pip install pycryptodome") from exc
            AES = _AES
        return args.func(args)
    except UserError as exc:
        print_json({"error": str(exc)}, stream=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
