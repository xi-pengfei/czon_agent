# 导航与新任务入口（2026-11-14）

- 保留欢迎区、输入框及现有玻璃质感，本次不修改正文输出动画。
- 移除空闲时的“企业工作助手”，AI智能体标题与菜单图标水平对齐。运行与重连状态仍保留。
- 顶部新任务、大屏、声音按钮改为简洁线性图标，移除厚重凸起边框；声音开启仍有状态提示。
- 新对话入口改为“新任务”，使用彩色纸飞机/任务卡片小插画。
- 最近任务默认显示最多五条；矮屏按可用高度减少预览条数。点击更多后完整列表独立滚动，可收起，不删除任何历史。
- 左下角字母头像换为原创粉色圆形卡通小角色（SVG），与女性助手头像区分。

验证：前端构建及现有 20 项测试通过；浏览器验证默认 5 条、展开 12 条且可滚动、标题与菜单中心线一致、390px 手机布局无横向溢出。仅修改前端，刷新即可使用，无需重启后端。

插画使用内置 imagegen 生成，保存于 `frontend/public/new-task-art-v1.png`，构建副本为 `webui/new-task-art-v1.png`。

生成提示：
> Create a small premium playful 3D UI illustration for a 'new task' button in an enterprise AI assistant sidebar. One compact cluster: a bright sky-blue folded paper airplane rising diagonally above two small rounded task cards in vivid coral pink and warm orange, one subtle small golden four-point sparkle. Smooth clay-like material, clean soft bevels, crisp silhouette, tasteful vibrant colors, soft studio light. Isolated on genuinely transparent background, no words, no letters, no numerals, no logos, no sale banner. Composition centered, entire object visible, minimal empty margins, readable at 90 pixels. A polished cheerful object, not a busy scene.
