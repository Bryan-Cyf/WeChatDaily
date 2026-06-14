# 环境配置

## 1. 复制环境文件

在项目根目录：

```bat
copy .env.example .env
```

## 2. 填写 WX_RAW_KEY

编辑 `.env`：

```env
WX_RAW_KEY=eba3ae5b42da4379a1a217686ccb4f9c4aa650bedfe74752bde1e9072e2c7ff3
```

- 64 位 hex，来自 `tools\wx_key\wx_key.exe`（微信需保持登录）
- wx_key 从上游 [v2.1.8 Release](https://github.com/ycccccccy/wx_key/releases/tag/v2.1.8) 下载，或运行 `python wechat.py download-wx-key`
- 微信重启后 key 会变，需重新提取并更新 `.env`
- **勿提交 `.env` 到 Git**

## 3. 可选 WECHAT_DEFAULT_GROUPS

在 `.env` 中设置默认导出群（逗号分隔）：

```env
WECHAT_DEFAULT_GROUPS=示例群①,示例群②
```

## 4. 可选 WECHAT_DB_DIR

自动检测失败时在 `.env` 增加：

```env
WECHAT_DB_DIR=D:\Tencent\WeChat\xwechat_files\wxid_xxx\db_storage
```

## 5. 在 Shell 中读取（PowerShell 示例）

```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*([^#=]+)=(.*)$') {
    [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), 'Process')
  }
}
$env:WX_RAW_KEY
```

## 6. setup 命令

```powershell
python wechat.py setup --raw-key $env:WX_RAW_KEY
# 若配置了 WECHAT_DB_DIR：
# python wechat.py setup --raw-key $env:WX_RAW_KEY --db-dir $env:WECHAT_DB_DIR
```
