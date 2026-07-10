# ViralPick AI 数据库迁移说明

本文档说明如何在不重建业务数据的情况下升级 SQLite schema。

## 适用场景

- 本地演示库首次创建：继续使用 `python scripts/init_database.py --force`。
- 已有数据库升级：使用 `python scripts/migrate_database.py`，不要直接 `--force` 重建。
- 容器镜像构建：初始化演示库后会执行一次迁移检查，确保镜像内 schema 与代码一致。

## 常用命令

查看待执行迁移：

```bash
python scripts/migrate_database.py --dry-run
```

执行迁移：

```bash
python scripts/migrate_database.py
```

指定数据库：

```bash
python scripts/migrate_database.py --db-path data/database/viralpick.db
```

输出 JSON：

```bash
python scripts/migrate_database.py --json
```

## 运行机制

- 迁移状态记录在 `schema_migrations` 表。
- 每条迁移包含 `version`、`name`、`checksum` 和 `applied_at`。
- 迁移脚本会跳过已执行版本，重复执行是安全的。
- 如果已执行迁移的 checksum 与代码不一致，脚本会拒绝继续执行。已发布迁移不要修改，应新增下一条迁移。
- `/api/ready` 会检查是否存在待执行迁移；有 pending migration 时返回 `503`，避免旧 schema 服务继续对外。

## 当前迁移

- `20260629_001 auth_lockout_fields`：为 `users` 表增加登录失败锁定字段和密码变更时间字段。
- `20260630_001 brand_settings_table`：增加工作区品牌设置表，并为已有工作空间补默认公开报告品牌模板。
- `20260630_002 report_share_access_logs`：增加公开报告分享访问日志表，记录脱敏访客哈希、访问时间、User-Agent 和来源。
- `20260630_003 team_invitations`：增加团队邀请表，用一次性 token 哈希支持成员自设密码入驻。
- `20260630_004 report_schedules`：增加定时运营报告任务表，保存周期、下次执行时间、最近报告和运行错误。
- `20260630_005 report_delivery_outbox`：为定时报告增加收件人字段和交付记录表，追踪邮件发送、跳过或失败状态。
- `20260630_006 report_delivery_retries`：为交付记录增加 `retry_of_delivery_id` 字段，用于关联手动重试记录和原始交付记录。
- `20260701_001 report_delivery_retry_jobs`：增加定时报告交付自动重试队列表，用于保存可恢复失败的重试计划、尝试次数、下次尝试时间和最终状态。
- `20260701_002 automation_runs`：增加后台自动化运行记录表，用于保存 worker 或运维中心按钮执行到期报告任务和交付重试的结果摘要。
- `20260701_003 domestic_ecommerce_fields`：为 `products` 和 `competitors` 增加国内电商展示字段，包括平台、品牌、店铺、商品图、卖点和来源说明，支撑商品雷达与竞品详情展示。

## 生产建议

- 在部署新版本应用前，先备份数据库，再执行迁移。
- 多实例部署时，应先停止写入流量或进入维护窗口，再执行迁移。
- SQLite 适合演示和小规模单实例部署；商业化多租户部署仍建议迁移到 PostgreSQL 或 MySQL，并引入 Alembic 等成熟迁移工具。
