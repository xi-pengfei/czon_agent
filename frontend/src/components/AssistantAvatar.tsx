import { useEffect, useState } from "react";
export type AssistantMood = 'idle' | 'working' | 'focused' | 'resting' | 'listening' | 'speaking' | 'done' | 'attention';

// One consistent portrait; expressions reflect observable UI/task state, not inferred emotions.
const expressions: Record<AssistantMood, string> = {
  idle: '0% 0%', listening: '0% 0%', working: '50% 0%', focused: '100% 0%',
  done: '0% 100%', attention: '50% 100%', speaking: '0% 0%', resting: '100% 100%',
};
export function AssistantAvatar({ state = 'idle', animated = true, ambient = false }: { state?: AssistantMood; animated?: boolean; ambient?: boolean }) {
  const [frame, setFrame] = useState<AssistantMood>(state);
  useEffect(() => {
    setFrame(state);
    if (!animated || (!ambient && !["working", "focused", "listening"].includes(state))) return;
    const preference = matchMedia("(prefers-reduced-motion: reduce)");
    let timer: ReturnType<typeof setTimeout>;
    let index = 0;
    const sequence: Array<[AssistantMood, number]> = ambient
      ? [['idle', 2000], ['done', 2200], ['idle', 1600], ['working', 2100], ['focused', 1800], ['idle', 2000]]
      : [['working', 2100], ['idle', 1500], ['focused', 1800], ['working', 2200], ['resting', 650]];
    const next = () => {
      if (preference.matches) return;
      const [expression, duration] = sequence[index++ % sequence.length];
      setFrame(expression); timer = setTimeout(next, duration);
    };
    const changed = () => { clearTimeout(timer); setFrame(state); if (!preference.matches) next(); };
    preference.addEventListener('change', changed); next();
    return () => { clearTimeout(timer); preference.removeEventListener('change', changed); };
  }, [state, animated, ambient]);
  const processing = ["working", "focused", "listening"].includes(state);
  const expression = animated && (processing || ambient) ? frame : state;
  return <span className={`assistant-avatar portrait-avatar mood-${state}`} aria-hidden="true">{(['idle', 'working', 'focused', 'done', 'attention', 'resting'] as AssistantMood[]).map(mood => <span key={mood} className="portrait-frame" style={{ backgroundPosition: expressions[mood], opacity: expressions[mood] === expressions[expression] ? 1 : 0 }} />)}</span>;
}

// Conservative display cues only; they never change task status or business outcomes.
export function replyExpression(text: string): AssistantMood {
  if (/无法完成|未能|执行失败|处理失败|需要你确认|尚未完成|暂不可用|未成功/.test(text)) return "attention";
  if (/已完成|核对完成|导出完成|已生成|已保存|处理成功/.test(text)) return "done";
  return "idle";
}
