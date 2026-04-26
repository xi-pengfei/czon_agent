---
name: pledgebox-sync
description: 同步 PledgeBox 平台的未锁定订单数据到本地 MySQL 数据库。当用户说"同步订单"、"拉取 PledgeBox 数据"、"同步一下 PledgeBox"、"更新订单"时触发此技能。
---

# PledgeBox 订单同步技能

从 PledgeBox API 拉取所有活跃项目的未锁定订单，写入本地 MySQL 数据库（7 张表）。

## 执行方式

直接运行同步脚本：

    bash: python skills/pledgebox-sync/scripts/sync.py

脚本会自动：
1. 从 `pb_projects` 表读取所有 `is_active='是'` 的项目
2. 对每个项目循环翻页拉取 API 数据（直到空页为止）
3. 筛选条件：`is_completed=1`，`order_status=unlock`
4. 去重写入 7 张数据表（已存在的订单自动跳过）
5. 输出同步结果摘要

## 返回示例

```
[同步完成]
处理项目数：2
新增订单数：47
跳过重复数：12
新增产品行：89
新增加购行：23
耗时：8.3 秒
```

## 触发示例

- "帮我同步一下 PledgeBox 最新订单"
- "拉一下 PledgeBox 的数据"
- "更新订单到数据库"
- "sync pledgebox"

## 依赖配置

`.env` 文件中需包含：
- `PB_API_TOKEN` — PledgeBox API Token
- `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` — MySQL 连接信息

## 错误处理

- API 请求失败：打印错误，跳过当前页，继续下一项目
- 数据库连接失败：立即终止并输出错误信息
- 单条订单写入失败：跳过该条，继续处理其余订单
