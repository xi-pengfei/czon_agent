/** Relative API paths prevent credentials being sent to links supplied by a model. */
export function serverOrigin(input: string, allowLocalHttp = false): string {
  const url = new URL(input.trim());
  const local = /^(localhost|127\.0\.0\.1|10\.(\d{1,3}\.){2}\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|[a-z0-9-]+\.local)$/.test(url.hostname);
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/' ||
      (url.protocol !== 'https:' && !(allowLocalHttp && local && url.protocol === 'http:'))) {
    throw new Error('请填写 HTTPS 服务地址；开发版本支持局域网 HTTP 地址');
  }
  return url.origin;
}
export function apiUrl(origin: string, path: string): string {
  if (!path.startsWith('/api/') || path.includes('\\')) throw new Error('无效的 API 地址');
  const url = new URL(path, origin);
  if (url.origin !== origin || !url.pathname.startsWith('/api/')) throw new Error('无效的 API 地址');
  return url.href;
}
export function sseParser(emit: (event: string, data: string) => void) {
  let buffer = '';
  return (text: string) => {
    buffer += text;
    let match: RegExpExecArray | null;
    while ((match = /\r?\n\r?\n/.exec(buffer))) {
      const block = buffer.slice(0, match.index);
      buffer = buffer.slice(match.index + match[0].length);
      let event = 'message'; const data: string[] = [];
      for (const line of block.split(/\r?\n/)) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
      }
      if (data.length) emit(event, data.join('\n'));
    }
    if (buffer.length > 2_000_000) throw new Error('事件数据过大');
  };
}
