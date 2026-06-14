"""Project path helpers."""
import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_DIR, "src")
TOOLS_DIR = os.path.join(PROJECT_DIR, "tools")
WECHAT_DECRYPT_DIR = os.path.join(TOOLS_DIR, "wechat-decrypt")
EXPORT_DIR = os.path.join(PROJECT_DIR, "export")

ALL_KEYS_FILE = os.path.join(EXPORT_DIR, "all_keys.json")
DECRYPTED_DIR = os.path.join(EXPORT_DIR, "decrypted")
REPORTS_DIR = os.path.join(EXPORT_DIR, "reports")
LOGS_DIR = os.path.join(EXPORT_DIR, "logs")
WECHAT_DECRYPT_CONFIG = os.path.join(WECHAT_DECRYPT_DIR, "config.json")
