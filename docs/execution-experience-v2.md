# 执行体验初版（2026-11-14）

## 参考项目实际链路

已读取 `/Users/pengfei/Documents/ChatGPT/和利时项目/ai_hollysys` 中以下实现；不是依据截图猜测内部推理。

1. `backend/src/portal.ts:255–355`：校验会话归属、同会话活动任务、拼接历史与附件，通过 ExecutionGuard 登记任务，返回 202。
2. `backend/src/portal-worker.ts:35–76`：领取 queued 任务，创建按用户/任务划分的工作目录，record() 写入 task_events。
3. `backend/src/portal-worker.ts:111–190`：CodeBuddy SDK query 开启 includePartialMessages；text_delta 变成 delta 事件；PreToolUse 和 tool_result 分别登记步骤。这里展示的是模型公开文本，不是隐含推理。
4. `backend/src/portal.ts:374–420`：归属校验后的 SSE 按 Last-Event-ID/after 读取数据库事件，带事件 ID；循环间隔 100ms。
5. `frontend/src/App.tsx:151–186`：EventSource 消费 delta 拼接 partial，工具事件单独追加；`ExecutionSteps.tsx` 展示最近步骤，`useLiveReply.ts` 平滑展示已收到文字。
6. `backend/src/portal-worker.ts:196–220` 与 `frontend/src/App.tsx:401–425`：成功后以最终回答归档，前端区分流式正文和最终结果。

参考项目并不能让一个不输出进度的长脚本持续生成真实业务进展。它的连续感来自公开文本增量、工具步骤和流式绘制三条信息的组合。

## 本项目改动

- `main.py`：仅 WebUI agent 注入公开过程说明要求，说明要查什么、已知证据、下一步；不公开内部推理、技能原文、命令或凭据。不改变小智的提示配置。
- `core/agent.py`：多轮公开文字之间添加段落分隔，避免上一阶段与下一阶段粘连；最终回复仍单独返回。reasoning_content 仍只保留给模型上下文，不传给公开 delta。
- `frontend/src/components/ToolTimeline.tsx`：默认显示最近三步及真实完成/异常状态；技术记录单独折叠。需要确认的操作仍展开参数和确认按钮。
- `frontend/src/components/WaitingHint.tsx`：没有新正文或步骤变化持续 15 秒才申请等待提示；有新证据立即撤掉旧提示。
- `core/narration.py`：等待提示缓存包含最近工具状态，避免同一时间窗口命中上一阶段的提示。
- `Composer.tsx` / `VoiceInput.tsx`：录音、转写、编辑、发送显式区分；麦克风 PCM 计算 RMS 波形。取消丢弃本次识别并恢复录音前草稿；停止只转写并可编辑；发送等待所有识别结果完成后只提交一次。任务停止与录音停止独立。当前会话上传的图片显示缩略图，离开或移除后释放 object URL。
- `AssistantAvatar.tsx`：女性表情图集；模型处理时抬眼、工具处理时垂眼、明确失败/确认时关切，明确完成文案时微笑，其他回复中性。进入处理状态有一次短暂闭眼，不做无限循环、外环或整体漂浮。回复表情只用保守文字线索，不参与业务判定。减少动态偏好下不做闭眼切换。

## 表情素材

使用内置 imagegen（非 API CLI），以原始 `webui/assistant-avatar.png` 为编辑参考，保留原图。
新素材：`frontend/public/assistant-expressions-v1.png`（构建后同步到 `webui/assistant-expressions-v1.png`）。

生成提示：

> Use case: identity-preserve. Create ONE production avatar expression sprite sheet, transparent background, exactly 3 columns x 2 rows equal square cells, no gaps, no text, no borders. Input image is the edit target; preserve the same adult woman's identity, dark brown bob haircut, warm brown eyes, soft feminine face contours, black boat-neck shirt, polished clean illustrated style. Each cell same frontal head-and-upper-shoulders crop, same scale and center, head fills 85% cell height, full hair visible. Change only facial expression. Row1 left: neutral attentive gentle face looking forward. Row1 middle: thoughtful gaze eyes subtly raised upwards, mouth closed. Row1 right: focused downward gaze, eyelids softly lowered, calm. Row2 left: warm happy smile with open eyes, restrained professional warmth. Row2 middle: concerned empathetic expression, eyebrows slightly raised at center, no tears or exaggerated sadness. Row2 right: softly closed eyes, peaceful concentration. Make facial features crisp and clear at small size, preserve original attractive soft silhouette. No halo, no decorative circles, no motion marks. Sheet aspect ratio 3:2 with precisely aligned equal cells suitable for CSS sprite background positioning.

## 验证与限制

- 前端类型检查、生产构建、18 项前端测试通过，包括取消时迟到的识别结果不得写回/发送、发送等待完整识别、停止后编辑不发送。
- 后端完整 114 项测试通过；随后新增缓存阶段切换测试，narration 模块 15 项测试通过。
- 浏览器使用独立测试账号、独立数据库、模拟业务文本，验证真实 SSE 和页面；320px/390px 无横向溢出，手机输入控件 44px。
- 表情/录音预览页的波形是静态演示值；生产组件的波形来自麦克风，尚未用实际 iPhone 验证本轮录音交互。
- ASR 仍是分段文件识别；此次没有把云接口变成实时 WebSocket ASR，也不能消除供应商网络延迟。
- 模型公开说明属于提示约束，实际文本频率取决于模型；等待无输出的脚本时不会制造虚假文字。最终归档仍以最终回答为主，技术步骤保留在运行记录。
- 已构建前端；后端新规则需要服务下次重启加载。没有为更新界面中断正在运行的正式服务。
