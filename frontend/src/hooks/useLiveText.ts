import { useEffect, useRef, useState } from 'react';

// Reveal only received text, paced by elapsed frame time rather than network chunk size.
export function useLiveText(text: string, streaming: boolean, motion = true) {
  const reduced = typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const [visible, setVisible] = useState(streaming ? '' : text);
  const shown = useRef(streaming ? '' : text);
  const target = useRef(text); target.current = text;
  const hasStreamed = useRef(streaming);
  const immediateText = !motion || reduced ? text : undefined;
  useEffect(() => {
    hasStreamed.current ||= streaming;
    if (!motion || !hasStreamed.current || reduced) {
      shown.current = target.current; setVisible(target.current); return;
    }
    let frame = 0, last = 0, credit = 0;
    const draw = (now: number) => {
      const next = target.current;
      if (!next.startsWith(shown.current)) shown.current = next;
      const remaining = Array.from(next.slice(shown.current.length));
      credit += Math.min(50, last ? now - last : 16) / 1000 * Math.min(180, Math.max(36, remaining.length / 2));
      last = now;
      const count = Math.floor(credit);
      if (count) { shown.current += remaining.slice(0, count).join(''); credit -= count; }
      if (!remaining.length) credit = 0;
      setVisible(shown.current);
      if (streaming || shown.current !== target.current) frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [streaming, motion, reduced, immediateText]);
  return reduced || !motion || !text.startsWith(visible) || !hasStreamed.current ? text : visible;
}
