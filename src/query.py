"""
WeChat 4.1 聊天记录查询库 — 直接查询解密后的 SQLite 数据库
"""
import os, hashlib, json, re, sqlite3
from datetime import datetime, timedelta

from paths import DECRYPTED_DIR

def md5(s):
    return hashlib.md5(s.encode()).hexdigest()

class WeChatDB:
    def __init__(self, decrypted_dir=None, self_wxid=None, self_name=None, display_name_mode="remark"):
        self.dir = decrypted_dir or DECRYPTED_DIR
        self._msg_conns = {}  # lazy-load per-DB connections
        self._contact_conn = None
        self._session_conn = None
        self._sender_cache = {}
        self._self_wxid = self_wxid
        self.self_name = self_name or "我"
        self.display_name_mode = display_name_mode

    @property
    def self_wxid(self):
        """检测当前设备主人的 wxid

        启发式方法: 在 contact.db 中找 remark 以 'HOME' 开头且有中文名缩写的联系人。
        'HOME  b1'、'HOME  m1' 等是亲属代号，'HOME  王c' 这种姓名缩写才是自己。
        """
        if self._self_wxid:
            return self._self_wxid
        if self.contact:
            rows = self.contact.execute(
                "SELECT username, remark FROM contact WHERE remark LIKE 'HOME%' AND username LIKE 'wxid_%'"
            ).fetchall()
            # 优先匹配中文姓名缩写模式 (姓+单字，如 'HOME  王c')
            for wxid, remark in rows:
                # 匹配: HOME + 空格 + 中文字符 + 单字母缩写
                if re.search(r'HOME\s+[一-鿿]+[a-z]', remark):
                    self._self_wxid = wxid
                    return self._self_wxid
            # 次选: 任何 HOME 联系人
            if rows:
                self._self_wxid = rows[0][0]
                return self._self_wxid
        self._self_wxid = "?"
        return self._self_wxid

    # ── connections ──────────────────────────────────────────────
    def _get_msg_dbs(self):
        """返回所有消息数据库路径列表 (按文件名排序)"""
        msg_dir = os.path.join(self.dir, "message")
        dbs = []
        for f in sorted(os.listdir(msg_dir)):
            if f.endswith(".db") and f.startswith("message_"):
                dbs.append(os.path.join(msg_dir, f))
        return dbs

    def _get_msg_conn(self, db_path):
        if db_path not in self._msg_conns:
            self._msg_conns[db_path] = sqlite3.connect(db_path)
        return self._msg_conns[db_path]

    @property
    def contact(self):
        if self._contact_conn is None:
            p = os.path.join(self.dir, "contact", "contact.db")
            if os.path.exists(p):
                self._contact_conn = sqlite3.connect(p)
        return self._contact_conn

    @property
    def session(self):
        if self._session_conn is None:
            p = os.path.join(self.dir, "session", "session.db")
            if os.path.exists(p):
                self._session_conn = sqlite3.connect(p)
        return self._session_conn

    def close(self):
        for c in self._msg_conns.values():
            c.close()
        if self._contact_conn:
            self._contact_conn.close()
        if self._session_conn:
            self._session_conn.close()

    # ── table resolution ─────────────────────────────────────────
    def find_msg_table(self, username):
        """在全部 message DB 中查找 username 对应的 Msg_<hash> 表"""
        table_name = f"Msg_{md5(username)}"
        for db_path in self._get_msg_dbs():
            conn = self._get_msg_conn(db_path)
            r = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,)
            ).fetchone()
            if r:
                return db_path, table_name
        return None, None

    # ── sender display name ──────────────────────────────────────
    def get_display_name(self, wxid):
        """通过 wxid 查昵称/备注 (带缓存)"""
        if wxid in self._sender_cache:
            return self._sender_cache[wxid]
        if not self.contact:
            self._sender_cache[wxid] = wxid
            return wxid
        row = self.contact.execute(
            "SELECT nick_name, remark FROM contact WHERE username=?",
            (wxid,)
        ).fetchone()
        if row:
            nick, remark = row
            if self.display_name_mode == "nickname":
                name = nick or remark or wxid
            else:
                name = remark or nick or wxid
        else:
            name = wxid
        self._sender_cache[wxid] = name
        return name

    # ── chatroom metadata ────────────────────────────────────────
    def get_chatroom_name(self, username):
        """获取群聊的显示名称 (来自 contact.db 的 nick_name/remark)"""
        if not self.contact:
            return username
        row = self.contact.execute(
            "SELECT nick_name, remark FROM contact WHERE username=?",
            (username,)
        ).fetchone()
        if row:
            return row[1] or row[0] or username
        return username

    # ── message query ────────────────────────────────────────────
    def query_messages(self, username, start_time=None, end_time=None, limit=500):
        """
        查询指定会话的消息。
        start_time, end_time: datetime 对象或时间戳(秒)
        返回: list[dict]
        """
        db_path, table = self.find_msg_table(username)
        if not table:
            return []

        conn = self._get_msg_conn(db_path)
        cols = [c[1] for c in conn.execute(f'PRAGMA table_info("{table}")')]
        has_packed = "packed_info_data" in cols

        if start_time and isinstance(start_time, datetime):
            start_time = int(start_time.timestamp())
        if end_time and isinstance(end_time, datetime):
            end_time = int(end_time.timestamp())

        sql = f'SELECT * FROM "{table}"'
        conditions = []
        params = []
        if start_time:
            conditions.append("create_time >= ?")
            params.append(start_time)
        if end_time:
            conditions.append("create_time < ?")
            params.append(end_time)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY create_time DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()

        # 解析消息
        messages = []
        for row in rows:
            m = dict(zip(cols, row))
            m["content_text"] = self._parse_content(m)
            messages.append(m)
        return messages

    def _try_decode(self, data):
        """尝试将 bytes 解码为 UTF-8 文本"""
        if isinstance(data, str):
            return data
        if isinstance(data, bytes):
            if len(data) > 2 and data[:2] == b'(\xb5':
                # protobuf 编码的文本消息: 跳过头部，提取 wxid:\n 后的内容
                sep = data.find(b':\n')
                if sep >= 0 and sep < 100:
                    text = data[sep+2:]
                    # errors='ignore' 跳过 protobuf 中夹杂的二进制字节
                    decoded = text.decode("utf-8", errors="ignore")
                    # 检查是否有足够可读内容
                    cjk = sum(1 for c in decoded if '一' <= c <= '鿿')
                    if cjk >= 3 or len(decoded.strip()) > 10:
                        return self._strip_binary(decoded)
                return None
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                return None
        return None

    def _strip_binary(self, text):
        """去除文本末尾的二进制垃圾（控制字符、非可读字节）"""
        # 截断在第一个连续的控制字符序列处
        result = []
        consecutive_ctrl = 0
        for ch in text:
            cp = ord(ch)
            # 允许: 换行、回车、tab、CJK、ASCII可打印、常见 Unicode 标点
            if ch in '\n\r\t' or (32 <= cp <= 126) or (0x4E00 <= cp <= 0x9FFF) or \
               (0x3000 <= cp <= 0x303F) or (0xFF00 <= cp <= 0xFFEF) or \
               (0x2000 <= cp <= 0x206F):
                result.append(ch)
                consecutive_ctrl = 0
            elif cp < 32 or (0x7F <= cp <= 0x9F):
                # C0/C1 控制字符
                consecutive_ctrl += 1
                if consecutive_ctrl >= 3:
                    break  # 连续控制字符 → 二进制垃圾，截断
            else:
                # emoji 和其他符号
                result.append(ch)
                consecutive_ctrl = 0
        return ''.join(result).rstrip()

    def _parse_content(self, m):
        """从 message_content 中提取可读文本"""
        content = m.get("message_content")
        local_type = m.get("local_type", 0)
        if not content:
            return ""

        # 对于可读文本类型，尝试解析
        if isinstance(content, bytes):
            text = self._try_decode(content)
            if text is None:
                # 二进制数据，按类型返回标签
                return self._type_label(local_type)
            content = text

        # 文本类型 (type=1 或 type=47)
        # 格式可能是: "sender_wxid:\ntext" 或纯文本
        if ":\n" in content and not content.startswith("<") and not content.startswith("<?xml"):
            parts = content.split(":\n", 1)
            if len(parts) == 2 and len(parts[0]) < 80 and "\n" not in parts[0]:
                return parts[1]
        return content

    def _type_label(self, local_type):
        """根据 local_type 返回消息类型标签"""
        labels = {
            3: "[图片]", 34: "[语音]", 42: "[名片]", 43: "[音视频通话]",
            47: "[引用回复]", 48: "[位置]", 49: "[分享/链接]",
            50: "[音视频通话]", 62: "[小视频]", 66: "[第三方链接]",
            268435456: "[红包]", 10002: "[系统消息]",
        }
        if local_type in labels:
            return labels[local_type]
        # 大数字类型 (如 244813135921) 通常是引用消息或富媒体
        if local_type > 1000000:
            return "[富媒体消息]"
        return f"[消息类型 {local_type}]"

    def _parse_sender(self, m):
        """从消息中提取发送者 wxid"""
        content = m.get("message_content")

        # 先处理 protobuf 包装的 bytes 内容 — 从 wxid_ 前缀提取
        if isinstance(content, bytes) and content[:2] == b'(\xb5':
            wxid_start = content.find(b'wxid_')
            if wxid_start >= 0:
                sep = content.find(b':\n', wxid_start)
                if sep >= 0 and sep - wxid_start < 80:
                    try:
                        wxid = content[wxid_start:sep].decode("utf-8")
                        if '\n' not in wxid:
                            return wxid
                    except UnicodeDecodeError:
                        pass
            return None

        text = self._try_decode(content) if isinstance(content, bytes) else content

        if text and ":\n" in text and not text.startswith("<") and not text.startswith("<?xml"):
            parts = text.split(":\n", 1)
            if len(parts) == 2 and len(parts[0]) < 80 and "\n" not in parts[0]:
                return parts[0]

        # 从 source 列尝试提取 (二进制 protobuf 中可能包含 sender)
        source = m.get("source")
        if source and isinstance(source, bytes):
            src_text = self._try_decode(source)
            if src_text and ":\n" in src_text:
                parts = src_text.split(":\n", 1)
                if len(parts) == 2 and len(parts[0]) < 80:
                    return parts[0]

        return None

    def format_messages(self, messages, include_system=False):
        """将消息列表格式化为 LLM 可读文本"""
        lines = []
        for m in reversed(messages):  # 正序输出
            local_type = m.get("local_type", 0)
            text = m.get("content_text", "")

            # 跳过空消息和太短的非文本消息
            if not text and local_type != 1:
                continue
            if not include_system and local_type != 1:
                # 非文本消息只在有标签时显示
                if not text.startswith("["):
                    continue

            ts = m.get("create_time", 0)
            dt = datetime.fromtimestamp(ts).strftime("%H:%M") if ts else "??"
            sender = self._parse_sender(m)
            if sender:
                display = self.get_display_name(sender)
            elif m.get("real_sender_id") == 2:
                display = self.self_name
            else:
                display = "?"
            lines.append(f"[{dt}] {display}: {text}")
        return "\n".join(lines)

    def normalize_messages(self, messages, include_system=False):
        """返回带 sender/time/text 的标准消息列表，供统计和报告使用。"""
        normalized = []
        for m in reversed(messages):
            local_type = m.get("local_type", 0)
            text = m.get("content_text", "")
            if not text and local_type != 1:
                continue
            if not include_system and local_type != 1 and not text.startswith("["):
                continue

            ts = m.get("create_time", 0)
            dt = datetime.fromtimestamp(ts) if ts else None
            sender = self._parse_sender(m)
            if sender:
                display = self.get_display_name(sender)
                sender_id = sender
            elif m.get("real_sender_id") == 2:
                display = self.self_name
                sender_id = self._self_wxid or "self"
            else:
                display = "?"
                sender_id = "unknown"
            normalized.append({
                "time": dt,
                "time_text": dt.strftime("%H:%M") if dt else "??",
                "hour": dt.hour if dt else None,
                "sender": display,
                "sender_id": sender_id,
                "text": text,
                "local_type": local_type,
            })
        return normalized

    # ── session listing ──────────────────────────────────────────
    def list_sessions(self, name_filter=None):
        """列出所有会话 (按最近活动排序)"""
        if not self.session:
            return []
        sql = "SELECT username, type, summary, last_timestamp, unread_count FROM SessionTable"
        params = []
        if name_filter:
            sql += " WHERE (username LIKE ? OR summary LIKE ?)"
            params = [f"%{name_filter}%", f"%{name_filter}%"]
        sql += " ORDER BY sort_timestamp DESC LIMIT 100"
        rows = self.session.execute(sql, params).fetchall()
        results = []
        for row in rows:
            username, stype, summary, ts, unread = row
            # timestamp is in seconds
            try:
                dt = datetime.fromtimestamp(ts) if ts else None
            except (OSError, ValueError):
                dt = None
            name = self.get_chatroom_name(username) if "@chatroom" in username else username
            results.append({
                "username": username,
                "display_name": name,
                "type": stype,
                "summary": (summary or "").replace("\n", " "),
                "last_time": dt.strftime("%Y-%m-%d %H:%M") if dt else "N/A",
                "unread": unread,
            })
        return results


# ── convenience ──────────────────────────────────────────────────
def load_config():
    """从 all_keys.json 加载配置"""
    keys_file = os.path.join(os.path.dirname(__file__), "all_keys.json")
    if not os.path.exists(keys_file):
        # fallback: look in current dir
        keys_file = "all_keys.json"
    with open(keys_file) as f:
        return json.load(f)
