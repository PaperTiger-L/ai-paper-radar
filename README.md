# AI Paper Radar · 智能论文雷达

根据每位订阅用户的**研究领域、当前研究问题、关注方法**，每周自动检索最近 7 天的顶会顶刊论文，
经 LLM 筛选、中文总结后，生成个性化 HTML 论文周报并定时发送到指定邮箱。

## 功能一览

| 模块 | 说明 |
|---|---|
| 管理员登录 | 复用 `index.html` 登录页（UI 原样保留），账号密码登录，后台管理 |
| 用户管理 | 增删改订阅用户：名称、邮箱、研究领域、研究问题、方法、关键词、关注会议/期刊、每周篇数、推送开关 |
| 论文智能检索 | OpenAlex + arXiv 双源，默认近 7 天，去重；LLM 生成检索词 → 相关性打分筛选 → 中文总结（标题/摘要/创新点/推荐理由） |
| 邮件周报 | 个性化 HTML 邮件：本周研究动态、本周推荐论文、本周研究启发；电脑/手机自适应 |
| LLM 配置 | OpenAI 兼容接口（OpenAI / DeepSeek / Qwen / Gemini / 自定义），可配 Base URL、Key、模型名，支持连通性测试 |
| 邮箱配置 | SMTP（SSL/TLS），支持测试邮件 |
| 定时任务 | 每周定时自动执行（可设星期/时间），支持手动触发、失败重试、防重复发送 |
| 日志 | 搜索 / LLM / 任务 / 邮件四类日志，可筛选查看与清理，**不记录任何密钥明文** |

## 技术栈

- 前端：React 18 + TypeScript + Vite + Tailwind CSS（构建产物由后端统一服务）
- 后端：Python 3.12 + FastAPI + SQLAlchemy + SQLite
- 定时：APScheduler（进程内，无需 Redis/Celery）
- 邮件：smtplib；LLM：OpenAI 兼容 HTTP 接口
- 部署：Docker Compose 单容器，SQLite 文件持久化

## 快速部署

```bash
git clone <你的仓库地址>
cd ai-paper-radar

cp .env.example .env
# 编辑 .env，务必修改 ADMIN_PASSWORD 为强密码（至少 8 位）

docker compose up -d --build
```

启动后访问：

- 登录页：`http://服务器IP:8000/`
- 管理后台：登录成功后自动跳转（或访问 `http://服务器IP:8000/admin/`）
- 默认管理员账号：`.env` 中的 `ADMIN_USERNAME` / `ADMIN_PASSWORD`
  （首次登录后请在右上角用户菜单中修改密码）

数据持久化：SQLite 文件保存在宿主机的 `./data/` 目录（compose 已挂载），
容器重建、重启都不会丢失数据与配置。

## 上手配置（首次使用，按顺序）

1. **LLM 配置**：后台「LLM 配置」页填写 Base URL、API Key、模型名 → 保存 → 点「测试连接」。
   未配置 LLM 时系统仍可运行：检索词用关键词拼接、相关性用关键词打分、中文摘要留空待补充，
   日志中会明确标注降级，不会伪造 AI 结果。
2. **邮箱配置**：后台「邮箱配置」页填写 SMTP 服务器、端口、账号、授权码、发件人 → 保存 → 发送测试邮件。
   常见：QQ/163 邮箱用授权码，端口 465 + SSL，或 587 + TLS。
3. **添加订阅用户**：后台「用户管理」→ 新增，重点填好「研究领域」「当前研究问题」「关注的研究方法」，
   系统据此理解需求、生成检索策略（不是简单关键词匹配）。
4. **定时任务**：后台「定时任务」页设置每周发送的星期与时间（默认周一 08:00），也可立即手动执行一次验证。

## 论文来源与真实性

- 数据源：OpenAlex（期刊/会议论文元数据）与 arXiv（最新预印本），均为公开免费 API，无需 Key。
- arXiv 论文会明确标注「预印本」，不会冒充顶会论文。
- LLM 只做筛选与总结，不编造论文；只能拿到摘要时就基于摘要分析，不虚构结论。
- 一周内高质量论文不足时如实少推荐，不凑数。

## 日志与排错

- 后台「日志管理」可按类别（search / llm / pipeline / email / scheduler / auth / system）与级别筛选。
- 定时任务「运行记录」中可查看每期周报的检索数、入选数、邮件发送状态，失败可一键重试发送。
- 容器日志：`docker compose logs -f`

## 安全说明

- `.env`（含管理员密码）已被 `.gitignore` 忽略，**不要提交到 GitHub**。
- LLM Key、SMTP 密码只存于本地 SQLite，API 返回时脱敏，日志中绝不明文记录。
- 生产环境建议在反向代理（Nginx/Caddy）后启用 HTTPS。

## 本地开发

```bash
# 后端
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload          # 访问 http://127.0.0.1:8000/

# 前端
cd frontend
npm install && npm run dev             # 开发调试
npm run build                          # 产物输出到 dist/，发布时复制到 backend/app/static/admin/
```

## 目录结构

```
ai-paper-radar/
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── routers/         # API 路由（auth/用户/配置/流水线/论文/日志…）
│   │   ├── services/        # 核心服务：llm.py / search.py / pipeline.py / emailer.py / scheduler.py
│   │   └── static/
│   │       ├── index.html   # 登录页（复用原设计，仅接入真实登录接口）
│   │       └── admin/       # 前端构建产物（Docker 构建时自动填入）
│   └── requirements.txt
├── frontend/                # React 管理后台源码
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```
