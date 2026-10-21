# 字段与边界

消息保留 `id`（分片文件与local_id）、`time`、`create_time`、`sender_id`、`type`、`content`、`content_truncated`。语音仍保持语音类型，不伪装成对方发送的文字。

| 字段或状态 | 含义 |
|---|---|
| transcript_source=wechat_local | 微信本机保存的文字 |
| transcript_source=local_whisper | 离线Whisper识别 |
| transcript_status=available | 有可读文字 |
| not_available | 未取得微信本机完成转写结果 |
| unreadable | 微信附加字段格式不支持或损坏 |
| audio_not_local | 没有找到该会话与服务端消息ID对应的本地音频 |
| audio_too_large / audio_too_long | 超过2MB或65秒 |
| asr_unavailable / asr_failed | 模型未安装或识别失败 |
| no_speech_detected | 没有得到可用语音文字 |
| transcript_model | 当前离线模型标识whisper-small-int8 |
| transcript_language | 模型检测的语言，短语音可能误判 |
| transcript_review_required | 自动识别结果需要对关键内容复核 |

微信4.x现用格式：语音消息 `local_type=34`；`packed_info_data` 为protobuf，外层字段5中的字段1为状态（2代表完成），字段2为UTF-8文字。解析器只读取这一路径，不从任意二进制字段猜文字。最多64KiB附加字段、128个字段，格式错误返回状态。

音频位于 `message/media_*.db` 的 `VoiceInfo.voice_data`，以 `Name2Id.user_name` 和 `VoiceInfo.svr_id` 双重匹配。不能只用local_id跨分片定位，否则可能读取另一条消息或另一会话。SQL只在临时只读解密副本执行。

每页最多扫描500条候选消息、返回100条，正文每条最多4000字符、每页64000字符。每页最多尝试3条缺少转写的语音，预算耗尽时不消费下一条的游标。过滤空页仍可能有后续页。

已有微信文字和Whisper文字都可能有识别错误；“取得文字”不等于人工核听准确。对于精确姓名、金额和采购数量，应结合可读上下文或用户核听确认。
