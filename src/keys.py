r"""Generate all_keys.json from wx_key raw_key and WeChat db_storage."""
import argparse
import hashlib
import hmac as hmac_mod
import json
import os
import struct
import sys

from paths import ALL_KEYS_FILE, WECHAT_DECRYPT_DIR

sys.path.insert(0, os.path.abspath(WECHAT_DECRYPT_DIR))
from key_scan_common import collect_db_files  # noqa: E402

PAGE_SZ = 4096
SALT_SZ = 16
RESERVE_SZ = 80
HMAC_SZ = 64
PBKDF2_ITERS = 256000


def verify_raw_key(raw_key, page1):
    """Verify a wx_key raw_key against database page 1."""
    salt = page1[:SALT_SZ]
    page_key = hashlib.pbkdf2_hmac("sha512", raw_key, salt, PBKDF2_ITERS, dklen=32)
    mac_salt = bytes(b ^ 0x3A for b in salt)
    mac_key = hashlib.pbkdf2_hmac("sha512", page_key, mac_salt, 2, dklen=32)
    hmac_data = page1[SALT_SZ: PAGE_SZ - RESERVE_SZ + 16]
    stored_hmac = page1[PAGE_SZ - HMAC_SZ: PAGE_SZ]
    hm = hmac_mod.new(mac_key, hmac_data, hashlib.sha512)
    hm.update(struct.pack("<I", 1))
    return hm.digest() == stored_hmac


def generate_keys(raw_key_hex, db_dir, output=ALL_KEYS_FILE):
    raw_key = bytes.fromhex(raw_key_hex)
    db_dir = os.path.abspath(os.path.expanduser(os.path.expandvars(db_dir)))
    output = os.path.abspath(os.path.expanduser(os.path.expandvars(output)))

    if not os.path.isdir(db_dir):
        raise FileNotFoundError(f"DB 目录不存在: {db_dir}")

    db_files, salt_to_dbs = collect_db_files(db_dir)
    if not db_files:
        raise RuntimeError(f"未找到数据库文件: {db_dir}")

    first = db_files[0]
    if not verify_raw_key(raw_key, first[4]):
        raise RuntimeError(
            "raw_key 验证失败。可能是密钥复制错误、微信重启后密钥变化，或 db_storage 路径不匹配。"
        )

    result = {}
    for rel, path, size, salt_hex, page1 in db_files:
        result[rel] = {
            "enc_key": raw_key.hex(),
            "salt": salt_hex,
            "size_mb": round(size / 1024 / 1024, 1),
        }
    result["_db_dir"] = db_dir

    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return {
        "db_count": len(db_files),
        "salt_count": len(salt_to_dbs),
        "output": output,
        "db_dir": db_dir,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="用 wx_key 提取的 raw_key + DB 目录生成 all_keys.json")
    parser.add_argument("--raw-key", required=True, help="wx_key 提取的 64 位 hex 密钥")
    parser.add_argument("--db-dir", required=True, help="微信 db_storage 目录")
    parser.add_argument("-o", "--output", default=ALL_KEYS_FILE, help="输出路径，默认 export/all_keys.json")
    args = parser.parse_args(argv)

    info = generate_keys(args.raw_key, args.db_dir, args.output)
    print(f"DB 目录: {info['db_dir']}")
    print(f"找到 {info['db_count']} 个数据库, {info['salt_count']} 个不同的 salt")
    print(f"已保存: {info['output']}")


if __name__ == "__main__":
    main()
