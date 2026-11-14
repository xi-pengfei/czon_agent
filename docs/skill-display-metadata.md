# 技能中文展示字段变更说明

## 来源与范围

2026-11-14：为技能选择面板增加中文名称及短说明。中文文案由助手人工整理，不是原作者官方译文，不是运行时翻译，也不是用户原先维护的文本。上一次实施直接写入了 18 个已安装技能的 SKILL.md YAML metadata。

每个技能保留原有 name、description、业务正文及脚本；enterprise-skill-creator 另外增加了一条新技能应包含这两个字段的编写指导。未新增必填校验：旧技能仍可加载。

## 字段与兼容

```yaml
name: invoice-ocr
description: 原有描述，保持不变
metadata:
  display_name: 发票识别
  display_description: 提取发票信息，整理票据明细
```

- `name`：英文执行标识，不翻译，不重命名。
- `description`：原有技能目录描述，继续用于模型识别技能。
- `metadata.display_name`：界面展示名称，可选。
- `metadata.display_description`：界面简短用途说明，可选。
- `main.py` 的 `skill_catalog_provider` 向 WebUI 返回展示字段，缺省回退原 name/description。
- `frontend/src/types.ts` 增加可选类型，Composer 用它们展示和搜索；提交任务仍传递原英文标识。
- 后续新建技能按创建助手的新增指导填写两个中文字段；它们不是新的业务规则或执行指令。

## 已添加字段的文件

| 文件 | 中文名称 | 中文说明 |
|---|---|---|
| `skills/aikepai-kingdee-inbound-export/SKILL.md` | 艾克派采购入库导出 | 将金蝶已审核采购入库单导出到店小秘模板 |
| `skills/aikepai-kingdee-material-export/SKILL.md` | 艾克派新增物料导出 | 将金蝶新增物料整理为店小秘商品导入表 |
| `skills/consumable-inventory/SKILL.md` | 耗材盘点与采购建议 | 整理耗材库存，生成采购建议 |
| `skills/dingtalk-kingdee-voucher-sync/SKILL.md` | 钉钉审批与金蝶凭证 | 查询审批单据，核对并处理金蝶凭证同步 |
| `skills/enterprise-skill-creator/SKILL.md` | 企业技能创建助手 | 创建、修改企业技能，生成可验证的技能草稿 |
| `skills/huanyu-overdue-watch/SKILL.md` | 回款风险工作台 | 查看逾期回款，整理风险与跟进事项 |
| `skills/invoice-ocr/SKILL.md` | 发票识别 | 提取发票信息，整理票据明细 |
| `skills/kingdee-profit-report/SKILL.md` | 金蝶客户利润报表 | 查询客户业务数据，整理利润报表 |
| `skills/kingdee-voice-query/SKILL.md` | 金蝶商品概况查询 | 查询商品库存及相关业务概况 |
| `skills/kingdee-xingchen/SKILL.md` | 金蝶云星辰业务助手 | 查询和处理金蝶云星辰业务 |
| `skills/kingdee-xingchen-sale-order-sync/SKILL.md` | 金蝶销售订单同步 | 同步销售订单到金蝶云星辰 |
| `skills/office-io/SKILL.md` | Office 文档处理 | 读取和生成办公文档、表格与演示文件 |
| `skills/patient-consultation/SKILL.md` | 医患沟通辅助 | 辅助整理患者咨询与沟通内容 |
| `skills/patient-recall/SKILL.md` | 患者智能召回 | 整理需要复诊或回访的患者名单 |
| `skills/pledgebox-dianxiaomi-export/SKILL.md` | PledgeBox 订单导出店小秘 | 整理众筹订单，生成店小秘导入表格 |
| `skills/pledgebox-kingdee-sale-outbound-sync/SKILL.md` | 店小秘销售出库同步 | 将店小秘订单同步为金蝶销售出库单 |
| `skills/post-treatment-followup/SKILL.md` | 诊后随访 | 安排诊后随访，整理患者反馈 |
| `skills/seventeen-track-logistics/SKILL.md` | 物流承运商匹配 | 识别物流单号对应的尾程承运商 |

## 本次面板修饰

只修改 Composer.tsx、styles.css 并重新构建 webui 静态文件：移除列表闪电图标，缩小面板，降低字体字重，搜索框去边线并保留底部焦点提示。本次未再修改技能文件、中文文案或业务执行逻辑。