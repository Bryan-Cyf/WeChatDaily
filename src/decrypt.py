"""Decrypt WeChat 4.1 databases with wx_key raw_key."""
import argparse
import hashlib
import hmac as hmac_mod
import json
import os
import struct

from Crypto.Cipher import AES

from paths import ALL_KEYS_FILE, DECRYPTED_DIR

PAGE_SZ = 4096
SALT_SZ = 16
IV_SZ = 16
HMAC_SZ = 64
RESERVE_SZ = 80
SQLITE_HDR = b"SQLite format 3\x00"
PBKDF2_ITERS = 256000


def derive_page_key(raw_key, salt, iters=PBKDF2_ITERS):
    return hashlib.pbkdf2_hmac("sha512", raw_key, salt, iters, dklen=32)


def derive_mac_key(page_key, salt):
    mac_salt = bytes(b ^ 0x3A for b in salt)
    return hashlib.pbkdf2_hmac("sha512", page_key, mac_salt, 2, dklen=32)


def decrypt_page(page_key, page_data, pgno):
    iv = page_data[PAGE_SZ - RESERVE_SZ: PAGE_SZ - RESERVE_SZ + IV_SZ]
    if pgno == 1:
        encrypted = page_data[SALT_SZ: PAGE_SZ - RESERVE_SZ]
        decrypted = AES.new(page_key, AES.MODE_CBC, iv).decrypt(encrypted)
        return SQLITE_HDR + decrypted + b"\x00" * RESERVE_SZ

    encrypted = page_data[:PAGE_SZ - RESERVE_SZ]
    decrypted = AES.new(page_key, AES.MODE_CBC, iv).decrypt(encrypted)
    return decrypted + b"\x00" * RESERVE_SZ


def decrypt_database(db_path, out_path, raw_key):
    file_size = os.path.getsize(db_path)
    total_pages = file_size // PAGE_SZ
    if file_size % PAGE_SZ != 0:
        total_pages += 1

    with open(db_path, "rb") as fin:
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

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(db_path, "rb") as fin, open(out_path, "wb") as fout:
        for pgno in range(1, total_pages + 1):
            page = fin.read(PAGE_SZ)
            if len(page) < PAGE_SZ:
                if not page:
                    break
                page = page + b"\x00" * (PAGE_SZ - len(page))
            fout.write(decrypt_page(page_key, page, pgno))
    return True


def decrypt_from_keys(keys_file=ALL_KEYS_FILE, output_dir=DECRYPTED_DIR, only=None):
    keys_file = os.path.abspath(os.path.expanduser(os.path.expandvars(keys_file)))
    output_dir = os.path.abspath(os.path.expanduser(os.path.expandvars(output_dir)))

    with open(keys_file, encoding="utf-8") as f:
        keys = json.load(f)

    db_dir = keys.get("_db_dir")
    if not db_dir:
        raise RuntimeError(f"{keys_file} 缺少 _db_dir")

    raw_key = None
    for rel, info in keys.items():
        if not rel.startswith("_") and info.get("enc_key"):
            raw_key = bytes.fromhex(info["enc_key"])
            break
    if not raw_key:
        raise RuntimeError(f"{keys_file} 中没有 enc_key")

    ok = failed = skipped = 0
    failures = []
    for rel in keys:
        if rel.startswith("_"):
            continue
        normalized_rel = rel.replace("\\", os.sep).replace("/", os.sep)
        if only and only not in rel and only not in normalized_rel:
            skipped += 1
            continue

        db_path = os.path.join(db_dir, normalized_rel)
        out_path = os.path.join(output_dir, normalized_rel)
        if not os.path.exists(db_path):
            failed += 1
            failures.append((rel, "源文件不存在"))
            continue

        if decrypt_database(db_path, out_path, raw_key):
            ok += 1
            print(f"[OK]   {rel}")
        else:
            failed += 1
            failures.append((rel, "HMAC 验证失败"))

    return {"ok": ok, "failed": failed, "skipped": skipped, "failures": failures, "output_dir": output_dir}


def main(argv=None):
    parser = argparse.ArgumentParser(description="解密 all_keys.json 中记录的微信数据库")
    parser.add_argument("--keys-file", default=ALL_KEYS_FILE, help="默认 export/all_keys.json")
    parser.add_argument("--output-dir", default=DECRYPTED_DIR, help="默认 export/decrypted")
    parser.add_argument("--only", help="只解密包含该字符串的相对路径，如 session.db")
    args = parser.parse_args(argv)

    result = decrypt_from_keys(args.keys_file, args.output_dir, args.only)
    for rel, reason in result["failures"]:
        print(f"[FAIL] {rel}: {reason}")
    print(f"\n输出目录: {result['output_dir']}")
    print(f"完成: {result['ok']} 成功, {result['failed']} 失败, {result['skipped']} 跳过")
    if result["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
