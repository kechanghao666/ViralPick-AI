# ViralPick AI 权限模型

当前版本采用角色到权限的集中映射，后端以 `backend/permissions.py` 为唯一权限矩阵来源。

## 角色

- `owner`：工作空间所有者，拥有全部权限。
- `admin`：管理员，可管理团队、数据、报告、评分模型、审计和运维。
- `analyst`：分析师，可查看分析数据、导入数据、生成报告和管理报告分享。
- `viewer`：只读成员，可查看分析看板、商品数据、报告和评分模型。

## 核心权限

| 权限 | 含义 |
| --- | --- |
| `analytics.read` | 查看分析看板 |
| `products.read` | 查看商品数据 |
| `reports.view` | 查看报告 |
| `reports.export` | 导出报告 |
| `reports.generate` | 生成运营报告 |
| `reports.share` | 创建、查看和撤销报告分享链接 |
| `reports.schedule` | 创建、更新、执行和归档定时运营报告 |
| `imports.manage` | 下载模板、上传 CSV、查看导入任务和错误报告 |
| `scoring.view` | 查看评分模型历史 |
| `scoring.manage` | 创建并激活评分模型版本 |
| `brand.view` | 查看工作区品牌设置 |
| `brand.manage` | 管理工作区品牌设置 |
| `team.view` | 查看团队成员 |
| `team.manage` | 创建和更新团队成员 |
| `audit.view` | 查看审计日志 |
| `ops.view` | 查看运维状态、备份列表、监控告警和后台自动化运行记录 |
| `ops.manage` | 创建和校验数据库备份，执行一次后台自动化 |
| `alerts.manage` | 手动发送监控告警 |

## 接口

```http
GET /api/auth/permissions
Authorization: Bearer <token>
```

返回当前用户角色、权限列表、能力标签和完整角色矩阵。接口不返回密码、令牌或任何 Secret。

## 实施原则

- 路由层使用 `require_permission()` 检查接口级权限。
- 服务层保留业务细则，例如 owner 不能停用自己、admin 不能给成员提权为 owner/admin。
- 前端只根据 `/api/auth/permissions` 和 `/api/auth/me` 返回的权限控制按钮可用性，不再直接硬编码角色判断。
- 未登录 demo 模式下，报告生成、报告查看和报告导出仍兼容 `VIRALPICK_AUTH_REQUIRED=0`；一旦用户登录，则严格按其权限执行。
- 定时报告属于写入型自动化能力，只有具备 `reports.schedule` 的角色可以创建计划、立即执行、执行到期任务、暂停或归档任务，并处理报告交付的手动重试和自动重试队列。
