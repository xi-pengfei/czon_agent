---
name: dianxiaomi-export
description: 把 v_dianxiaomi 视图中的未锁定订单导出为店小蜜 Excel 表，自动用 AI 校正邮编/城市/省州不匹配的地址、空邮编填 000000、从买家备注里提取 IOSS 税号回填到卖家税号列，导出成功后把对应 pb_orders 的 order_status 改为 Locked。当用户说"导出店小蜜"、"导单"、"出店小蜜表"、"生成店小蜜导入文件"时触发。
---

# 店小蜜导单技能

读 MySQL 视图 `v_dianxiaomi`（已经过滤 `pb_orders.order_status='Unlock'`），落成一张可直接导入店小蜜的 Excel，并把这批订单在 `pb_orders` 中的状态改为 `Locked`。

## 执行方式

一条命令跑完全程：

    bash: python skills/dianxiaomi-export/scripts/export.py

可选参数：

    --dry-run        # 只导出 Excel，不更新 order_status（用于核验）
    --no-ai          # 跳过 AI 地址校验（仅做空邮编 / 税号正则规则）
    --limit N        # 仅处理前 N 条（调试用）

## 处理流程（事务内执行）

1. **快照**：`SELECT id FROM pb_orders WHERE order_status='Unlock'` 取到本次要锁定的 id 集合
2. **导出**：`SELECT * FROM v_dianxiaomi`，结果落入内存
3. **规则清洗**（按行）：
   - `*邮编` 为空 → 填 `000000`
   - `*邮编` 非空 → 加入 AI 批次（一次发 20 行，让模型返回修正后的城市/省州）
   - `买家备注` 用正则识别 IOSS（`IM\d{10}`）→ 写入 `卖家税号（IOSS）`；正则未命中但备注含"税号/VAT/IOSS/EORI"等关键词时，再走 AI 兜底一次
4. **写盘**：输出 `workspace/dianxiaomi_<时间戳>.xlsx`
5. **锁单**：`UPDATE pb_orders SET order_status='Locked' WHERE id IN (...)`，COMMIT
6. **失败回滚**：导出或写盘任一环节抛错 → 整事务回滚，状态保持 `Unlock`

## 返回示例

    ====================================================
      [店小蜜导出完成]
    ====================================================
      导出订单数：87
      AI 校正地址：12 行
      空邮编兜底：5 行
      回填 IOSS 税号：3 行
      锁定订单数：87
      输出文件：workspace/dianxiaomi_20260430_153012.xlsx
      耗时：14.2 秒

    ────────────────────────────────────────────────────
      修改明细（Excel 中已用黄色背景标记）
    ────────────────────────────────────────────────────

    ● 空邮编 → 000000（5 行）
        AB1234-K-000123 (John Smith, US)
        AB1234-K-000125 (Maria Lopez, MX)
        ...

    ● 回填 IOSS 税号（3 行）
        AB1234-K-000130 (Hans Müller, DE)  →  IM1234567890  [正则]
        CD5678-I-000045 (Luca Rossi, IT)   →  IM9876543210  [AI]
        ...

    ● AI 校正地址（12 行）
        AB1234-K-000130 (Hans Müller, DE)  (*城市 'Berlin' → 'München'; *省/州 'BE' → 'BY')
        ...

    ────────────────────────────────────────────────────

    ● 锁定订单（87 单）
        AB1234-K-000123 (John Smith, US)
        AB1234-K-000124 (Sarah Lee, GB)
        ...
    ====================================================

修改过的单元格在 Excel 中用 **黄色背景** 高亮，方便人工复核。

## 触发示例

- "导一下店小蜜"
- "出店小蜜表"
- "生成店小蜜导入文件"
- "把这批订单导出锁单"

## 依赖配置

`.env` 中需包含：

- `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` — MySQL 连接
- `MOONSHOT_API_KEY` 或 `DASHSCOPE_API_KEY` 或 `DEEPSEEK_API_KEY` — 与 `config.yaml` 的 `active_provider` 对应

依赖包：`pymysql`、`openpyxl`、`python-dotenv`、`pyyaml`、`openai`（已在项目内）

## 错误处理

- 数据库连接失败：立即终止，不创建 Excel
- 视图返回 0 行：跳过 AI/锁单步骤，输出"无待导订单"
- 单行 AI 校验失败：保留原值并记录日志，不影响其他行
- 写 Excel 失败：回滚事务，订单状态保持 `Unlock`
- 锁单 UPDATE 影响行数 ≠ 预期：回滚事务并报错（防止部分锁定）

## 安全约束

- 不会在 Excel 中写入除清洗规则之外的任何 AI 推断内容
- AI 仅参与字段值修正，不参与 SQL 生成
- 视图列名以 `*` 开头的为店小蜜必填字段，脚本不会改变列顺序与列头
