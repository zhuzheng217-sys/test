# 企业微信天气推送（基于 Open-Meteo）

功能
- 使用 Open-Meteo 免费 API 获取天气（无需 API Key）。
- 每天按计划向企业微信推送天气：早上 06:00 推送当天要点；晚上 20:00 推送第二天详细预报。
- 包含未来 N 天（默认 5 天）预览。
- 简单的“恶劣天气”检测逻辑（雷暴、大雨、大风）并在消息中突出提醒。
- 可在本地运行或使用 GitHub Actions 定时运行（免费）。

添加 Secrets（必须）
在仓库 Settings → Secrets and variables → Actions 中添加以下 Secrets（键名必须一致）：
- WECOM_CORP_ID: 你的企业微信 CorpID（例如：wwb6c4855a66e4d4f7）
- WECOM_CORP_SECRET: 应用 Secret（请在企业微信后台重置并使用新的 Secret；**不要**将其公开）
- WECOM_AGENT_ID: 应用 AgentId（例如：1000002）
- WECOM_TO_USER: 接收者（默认 "@all" 或 企业微信用户名，逗号分隔）
- CITY: 城市名（例如 "Xuancheng, China"）
- PREVIEW_DAYS / FORECAST_DAYS / SEVERE_RAIN_MM / SEVERE_WIND_MS / MODE（可选）

手动触发测试
1. 提交上述文件与 Secrets 后，进入仓库 Actions → 选择 “WeCom Daily Weather Push” → 点击 “Run workflow”。
2. 选择分支（例如 main）并 Run。
3. 打开该运行，查看每个 step 的日志输出。脚本的 stdout/stderr 会在最后一步显示。

本地临时测试（仅用于调试）
在本地 shell 临时设置环境变量（不要把 Secret 提交到仓库）：
WECOM_CORP_ID=wwb6c4855a66e4d4f7 \
WECOM_CORP_SECRET=你的新Secret \
WECOM_AGENT_ID=1000002 \
WECOM_TO_USER="@all" \
CITY="Xuancheng, China" \
python weather_wecom.py

调试要点（常见错误）
- 获取 access_token 失败：会在日志中看到企业微信返回的 errcode/errmsg，请确认 CorpID 与 Secret 是否对应且 Secret 未过期。
- 发送消息失败（errcode != 0）：检查 AgentId 是否正确且应用对目标成员有发送权限。
- 城市定位失败：尝试写成 "Xuancheng, China" 或更精确位置。
- 如果 Actions 中网络请求被阻断或超时，可考虑重试或查看网络错误栈。
