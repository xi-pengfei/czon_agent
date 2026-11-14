// Applied after sanitization. Stable two-character spans fade only when newly mounted.
// Code blocks stay untouched; no raw HTML or model-provided attributes are introduced.
type Node = { type: string; tagName?: string; value?: string; properties?: Record<string, unknown>; children?: Node[] };
export function streamFade() {
  return (tree: Node) => {
    let budget = 6000;
    const walk = (node: Node) => {
      if (!node.children || node.tagName === 'code' || node.tagName === 'pre') return;
      node.children = node.children.flatMap(child => {
        if (child.type !== 'text' || !child.value || budget <= 0) { walk(child); return [child]; }
        const chars = Array.from(child.value);
        const parts: Node[] = [];
        for (let i = 0; i < chars.length; i += 2) {
          const value = chars.slice(i, i + 2).join('');
          parts.push(budget-- > 0 ? { type: 'element', tagName: 'span', properties: { className: ['stream-fragment'] }, children: [{ type: 'text', value }] } : { type: 'text', value });
        }
        return parts;
      });
    };
    walk(tree);
  };
}
