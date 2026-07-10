# ViralPick AI 部署说明

本文档说明如何以产品化方式运行 ViralPick AI。

## 本地生产模式

初始化数据库：

```bash
python scripts/init_database.py --force
```

已有数据库升级时执行迁移，不要用 `--force` 重建：

```bash
python scripts/migrate_database.py
```

启动本地服务：

```bash
python backend/app.py
```

开发环境默认由 Flask 同时托管前端和 API。访问：

```text
http://127.0.0.1:5000
```

如果设置 `VIRALPICK_SERVE_FRONTEND=0`，可改用独立前端静态服务：

```bash
cd frontend
python -m http.server 8080 --bind 127.0.0.1
```

## 单容器模式

Docker 镜像内会初始化 SQLite 数据库，并由 Gunicorn 同时服务 API 和前端静态文件。

```bash
docker build -t viralpick-ai:latest .
docker run --rm -p 5000:5000 viralpick-ai:latest
```

访问：

```text
http://127.0.0.1:5000
```

## Docker Compose

```bash
docker compose up --build
```

## 健康检查

存活检查：

```http
GET /api/health
```

就绪检查：

```http
GET /api/ready
```

`/api/ready` 会检查 SQLite 数据库是否存在，并确认商品表有数据。生产部署应使用 `/api/ready` 作为容器健康检查。
如果数据库存在待执行迁移，`/api/ready` 会返回 `503`，此时应先运行 `python scripts/migrate_database.py`。

## Smoke Test

```bash
python scripts/smoke_test.py --base-url http://127.0.0.1:5000 --check-frontend
```

检查内容：

- `/api/health`
- `/api/ready`
- `/api/llm/status`
- `/api/overview`
- `/api/products`
- `/api/forecast/sales`
- `/api/auth/login`
- `/api/auth/me`
- `/api/team/members`
- `/api/audit/logs`
- `/api/scoring/models`
- `/api/ops/status`
- `/api/ops/monitoring`
- `/api/ops/alerts/status`
- `/api/ops/alerts/dispatch`
- `/api/ops/backups`
- `/api/ops/backups/<filename>/verify`
- `/api/ops/automation/runs`
- `/api/ops/automation/run-once`
- `/api/imports`
- `/api/imports/templates/<dataset_type>`
- `/api/imports/<job_id>/errors`
- `/api/reports/generate`
- `/api/reports/<id>/shares`
- `/api/reports/shared/<token>`
- `/api/reports/<id>/export`
- 前端根文档

## 数据库迁移

迁移状态记录在 `schema_migrations` 表。升级已有数据库时使用：

```bash
python scripts/migrate_database.py --dry-run
python scripts/migrate_database.py
```

完整说明见 [database_migrations.md](database_migrations.md)。

## 后台自动化

定时报告任务和交付重试可以由运维中心按钮触发，也可以由 CLI worker 执行。单次执行：

```bash
python scripts/run_automation_worker.py --once --json
```

单机轮询：

```bash
python scripts/run_automation_worker.py --interval-seconds 300
```

worker 启动前会检查数据库文件和待执行迁移；如果 `/api/ready` 会因为 pending migration 失败，worker 也应先停止并执行 `python scripts/migrate_database.py`。商业化多实例部署建议替换为 Celery、RQ、云任务队列或平台级调度器，并补充并发锁、退避策略、死信队列和外部监控。

## 备份与恢复

创建备份：

```bash
curl -X POST http://127.0.0.1:5000/api/ops/backups -H "Authorization: Bearer <token>"
```

校验备份：

```bash
python scripts/restore_database.py --backup data/backups/viralpick-xxx.db --dry-run
```

恢复备份：

```bash
python scripts/restore_database.py --backup data/backups/viralpick-xxx.db --yes
```

恢复脚本会校验 SHA-256、执行 SQLite integrity check、在替换目标库前创建 `pre-restore-*.db` 备份，并在恢复后应用 pending schema migration。恢复前应停止写入流量或进入维护窗口；不要在多实例同时写入时直接替换 SQLite 文件。

## 环境变量

参考 `.env.example`。

关键变量：

- `VIRALPICK_ENV`：运行环境。
- `VIRALPICK_VERSION`：版本号。
- `VIRALPICK_LOG_LEVEL`：日志级别。
- `VIRALPICK_API_HOST`：本地 Flask runner 监听地址。
- `VIRALPICK_API_PORT`：端口。
- `VIRALPICK_DB_PATH`：SQLite 数据库路径。
- `VIRALPICK_BACKUP_DIR`：SQLite 手动备份目录，默认 `data/backups`。
- `VIRALPICK_BACKUP_RETENTION`：保留最近多少份本地备份，默认 `10`。
- `VIRALPICK_MAX_UPLOAD_MB`：CSV 上传文件大小上限，默认 10 MB。
- `VIRALPICK_CORS_ORIGINS`：允许跨域来源。生产环境建议配置明确域名，不使用 `*`。
- `VIRALPICK_SERVE_FRONTEND`：是否由 Flask/Gunicorn 同时托管前端。开发环境默认开启，生产环境默认关闭，可用 `.env` 显式设置。
- `VIRALPICK_AUTH_REQUIRED`：是否要求写入型接口登录。
- `VIRALPICK_AUTH_TOKEN_TTL_HOURS`：登录令牌有效期。
- `VIRALPICK_AUTH_MAX_FAILED_ATTEMPTS`：账号临时锁定前允许的连续失败登录次数，默认 5。
- `VIRALPICK_AUTH_LOCKOUT_MINUTES`：账号失败登录锁定分钟数，默认 15。
- `VIRALPICK_DEFAULT_ADMIN_EMAIL`：初始化数据库时创建的默认管理员邮箱。
- `VIRALPICK_DEFAULT_ADMIN_PASSWORD`：初始化数据库时创建的默认管理员密码。
- `VIRALPICK_RATE_LIMIT_ENABLED`：是否启用进程内 API 限流。生产环境默认启用。
- `VIRALPICK_RATE_LIMIT_WINDOW_SECONDS`：限流统计窗口秒数，默认 60。
- `VIRALPICK_RATE_LIMIT_DEFAULT_PER_WINDOW`：普通读取接口每窗口请求数。
- `VIRALPICK_RATE_LIMIT_AUTH_PER_WINDOW`：登录接口每窗口请求数。
- `VIRALPICK_RATE_LIMIT_WRITE_PER_WINDOW`：写入接口每窗口请求数。
- `VIRALPICK_ALERTS_ENABLED`：是否启用 Webhook 告警发送，默认关闭。
- `VIRALPICK_ALERT_WEBHOOK_URL`：告警接收端 URL。只能通过本地 `.env`、部署 Secret 或环境变量注入，不能提交到仓库。
- `VIRALPICK_ALERT_MIN_SEVERITY`：告警发送最小级别，支持 `info`、`warn`、`critical`，默认 `warn`。
- `VIRALPICK_ALERT_TIMEOUT_SECONDS`：Webhook 请求超时时间，默认 8 秒。
- `VIRALPICK_PUBLIC_BASE_URL`：公开访问域名，用于定时报告邮件中的只读分享链接。
- `VIRALPICK_REPORT_DELIVERY_ENABLED`：是否启用定时报告 SMTP 邮件发送，默认关闭。
- `VIRALPICK_REPORT_DELIVERY_AUTO_RETRY_ENABLED`：是否对 `smtp_error`、`export_error` 等可恢复失败写入自动重试队列，默认启用。
- `VIRALPICK_REPORT_DELIVERY_MAX_RETRY_ATTEMPTS`：每条交付失败最多自动重试次数，默认 `3`。
- `VIRALPICK_REPORT_DELIVERY_RETRY_BACKOFF_MINUTES`：自动重试退避分钟序列，默认 `5,30,120`。
- `VIRALPICK_SMTP_HOST` / `VIRALPICK_SMTP_PORT`：SMTP 服务地址和端口。
- `VIRALPICK_SMTP_USERNAME` / `VIRALPICK_SMTP_PASSWORD`：SMTP 账号凭据。只能通过本地 `.env`、部署 Secret 或环境变量注入。
- `VIRALPICK_SMTP_FROM_EMAIL`：报告邮件发件地址。
- `VIRALPICK_SMTP_USE_TLS` / `VIRALPICK_SMTP_USE_SSL`：SMTP 加密方式。
- `VIRALPICK_SMTP_TIMEOUT_SECONDS`：SMTP 请求超时时间。
- `VIRALPICK_LLM_ENABLED`：是否默认启用智能增强报告。
- `VIRALPICK_LLM_PROVIDER`：大模型服务商标识，默认 `spark-x`。
- `VIRALPICK_LLM_MODEL`：大模型名称，默认 `x2`。
- `VIRALPICK_LLM_ENDPOINT`：HTTP `chat/completions` 地址。
- `VIRALPICK_LLM_API_PASSWORD`：大模型 API 凭据。只能通过本地 `.env`、部署 Secret 或环境变量注入，不能提交到仓库。
- `VIRALPICK_LLM_CONFIG_FILE`：可选本地凭据配置位置。开发环境下存在 `../API.txt` 时可自动识别。
- `VIRALPICK_LLM_TIMEOUT_SECONDS`：大模型调用超时时间。

## 生产注意事项

- SQLite 适合演示和轻量部署；多用户高并发场景建议迁移到 PostgreSQL 或 MySQL。
- 当前版本已具备基础登录、失败登录锁定、进程内限流、工作空间、团队邀请链接、团队成员、角色管理、集中式权限矩阵、令牌和审计中心；定时报告支持 SMTP 邮件交付配置和交付记录，但尚未实现 MFA、字段级/资源实例级授权和完整租户级数据隔离。
- 内置限流是单进程内存实现，适合单容器演示和基础防护；多实例生产部署必须在反向代理、API 网关或 Redis 级限流中配置等价策略。
- 当前版本支持 CSV 模板下载、导入校验、失败错误报告下载和部分业务表受控替换，但尚未提供失败重试和生产级数据源同步。
- 当前版本支持爆品评分模型权重配置和版本记录，但尚未提供按品类/店铺自动切换、效果回测和审批流。
- 当前版本支持 Word、PDF、HTML 和 Markdown 报告导出，PDF 由服务端生成；定时报告可生成邮件交付记录，支持失败或跳过记录的手动重试，并对可恢复失败提供自动重试队列入口；生产环境应保留报告模板审查、敏感信息复核、退信处理和外部投递监控流程。
- 当前版本支持带有效期和撤销能力的只读报告分享链接、品牌化分享页和脱敏访客访问明细，但尚未提供访问者身份校验和细粒度分享权限。
- 报告智能增强默认不主动发起外部模型请求；只有 `VIRALPICK_LLM_ENABLED=1` 或前端启用智能增强并生成报告时才调用。异常会自动回退规则模板，返回给前端的错误摘要会过滤凭据。
- 当前版本支持具备运维权限的用户查看规则化监控告警、手动触发 Webhook 告警通知、手动创建 SQLite 本地备份、校验备份，并通过 CLI worker 执行到期报告和交付重试、通过 CLI 执行受控恢复；但尚未提供外部 APM、自动告警调度、生产级分布式任务队列、自动备份调度、远端对象存储和备份加密。
- 当前版本提供 SQLite schema 迁移记录和 `/api/ready` pending migration 检查；多租户生产环境仍建议迁移到 PostgreSQL 或 MySQL 并使用成熟迁移工具。
- 当前版本支持 Spark X HTTP 大模型增强报告，但生产环境必须通过 Secret 管理凭据，并保留规则模板回退。
- 当前竞品和短视频互动数据为模拟扩展数据，应在 UI 和报告中持续标注边界。
