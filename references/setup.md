# 安装与连接

先检查是否已经有可用的wechat-readonly连接。已连接时复用服务；不为查询更改配置。只在用户要求安装或修复时执行本页。

## 安装skill与运行时的区别

skill是本仓库根目录的SKILL.md及相关文件。可以把仓库复制到 `~/.codex/skills/wechat-readonly-voice`，保持目录名不变。MCP是独立的本机数据库读取服务，只有安装skill不会自动获得聊天访问权限。

运行时需要Windows 64位、Python3.12及当前登录的个人微信。验证环境为微信4.1.13.65。未来版本可能改变数据库布局，先用单会话窄范围查询验证。不要导入上游wechatauto包初始化、GUI、发送或媒体模块。

## 设置新运行时

运行 `python -B scripts/setup_runtime.py --install-dir C:/Tools/wechat-readonly --dry-run` 检查安装计划，再去掉dry-run执行。使用可写的新目录；脚本拒绝覆盖已有目录。依赖装入lib与asr_lib，模型装入asr_model。模型下载固定revision并校验全部4个文件的SHA256；这一阶段联网下载软件，查询阶段不联网。

如果下载或安装失败，保留失败目录供检查，修复后选择新的安装目录；不要删除用户既有运行时或更改其配置。完整目录应始终留在本机，不上传GitHub。

## 明确账号

根据用户选择的微信数据位置确定xwechat_files目录和账号子目录，确认其中有db_storage。多个账号时让用户选择，不按“最近修改”自动更换账号。

```powershell
python -B scripts/configure_account.py --runtime C:/Tools/wechat-readonly --db-dir C:/path/to/xwechat_files --account YOUR_LOCAL_ACCOUNT_DIRECTORY
```

private_config.json只在本机生成，只有账号路径，不包含密钥。脚本拒绝覆盖已有配置，不读取聊天。运行时必须位于本地私有目录；发布包、Git提交、云同步与诊断日志不应包含此文件、数据库、音频、密钥、scratch或完整聊天原文。

## 连接Codex

可以在Codex设置中添加stdio MCP：command为实际64位Python3.12路径，args为 `-B` 与运行时server.py的绝对路径，startup_timeout_sec设20、tool_timeout_sec设150。仅启用wechat_status、list_recent_chats、find_chats、query_messages。

以下配置仅为例子；不要覆盖用户整个配置文件。若需要直接改Codex配置，先检查现有wechat-readonly条目并备份目标配置，再只修改这一服务。

```toml
[mcp_servers.wechat-readonly]
command = 'C:\Path\To\Python312\python.exe'
args = ['-B', 'C:\Tools\wechat-readonly\server.py']
startup_timeout_sec = 20
tool_timeout_sec = 150
enabled_tools = ['wechat_status', 'list_recent_chats', 'find_chats', 'query_messages']
```

保持微信登录，重新连接MCP。先wechat_status，再取少量会话并查询已授权会话。不要把ready=true当成已经验证数据库读取。查询结果应保留来源和消息ID，并确认临时副本已清理。

## 测试

运行时装好后，使用 `python -B scripts/test_runtime.py --runtime C:/Tools/wechat-readonly`。该命令只运行22项合成数据测试，不读取真实微信。若在仓库目录测试，可用 `--dependency-dir` 指向已安装运行时的lib；无需再次下载模型。

本机语音识别需要本地音频；audio_not_local时不要自动操作微信播放或下载。Python读进程只能写本次scratch，网络操作与写入原始数据库被禁止。不要为绕过报错解除Guard。
