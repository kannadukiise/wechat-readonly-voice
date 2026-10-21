# wechat-readonly-voice

面向Codex的Windows微信只读skill与本地MCP运行时。查询聊天时读取微信已有语音转文字；没有文字时，对本机已保存的音频使用Whisper small离线识别。文字保留来源、时间及消息ID，可参与关键词搜索。

## 安装skill

把本仓库放到 `~/.codex/skills/wechat-readonly-voice`，或使用Codex的skill-installer安装此仓库根目录。安装skill只添加工作指引；若本机已有升级后的wechat-readonly MCP，可立即复用，无需重装运行时。

## 安装MCP运行时

适用Windows 64位、Python 3.12、个人微信4.x。验证版本为微信4.1.13.65，其他版本需要重新检查。企业微信不包含在内。

```powershell
python -B scripts/setup_runtime.py --install-dir C:/Tools/wechat-readonly --dry-run
python -B scripts/setup_runtime.py --install-dir C:/Tools/wechat-readonly
python -B scripts/configure_account.py --runtime C:/Tools/wechat-readonly --db-dir C:/path/to/xwechat_files --account YOUR_LOCAL_ACCOUNT_DIRECTORY
```

安装脚本在指定新目录隔离安装依赖，并从公开仓库下载约486MB固定版本模型，不发送用户音频。账号配置只留在本机，不覆盖既有配置。需要联网安装依赖，查询与转写阶段离线。具体连接方法见 [安装说明](references/setup.md)。

## 使用

- “读取某联系人本周的语音，按时间逐条列出来。”
- “查某项目群最近两周的报价讨论，包括语音内容。”
- “找出对某产品有需求的联系人，区分其所属公司和终端客户。”

每页最多自动识别3条缺失语音，必须继续next_cursor直到has_more=false。已有转写标记wechat_local，新识别标记local_whisper。未在本机保存的音频无法补齐，识别出的姓名、数字和专有名词可能有误。

## 验证与限制

```powershell
python -B scripts/test_runtime.py --runtime C:/Tools/wechat-readonly
```

22项合成数据测试覆盖只读与网络限制、时间边界、跨分片分页、转写解析与关键词、音频会话隔离、音频限额、分页预算及失败/取消/超时清理。已在Windows实机通过8条语音样本验证：5条复用微信文字，3条离线补齐。样本语音和聊天内容不包含在仓库中。

不发消息、不自动切换账号、不调用微信界面、不回写数据库、不调用云端转写、不保存密钥或新增转写缓存。临时解密副本在成功、失败、取消及超时后清理；异常断电不保证物理安全擦除。结果仍会进入发起请求的Codex会话供模型分析。Python保护限制针对已审查路径，不替代原生代码的完整操作系统隔离。

底层读取器来源、哈希及许可见 [第三方说明](THIRD_PARTY_NOTICES.md)。模型与依赖仅在安装时下载，不随本仓库分发。用户需自行确认所处理账号和记录的访问权限。
