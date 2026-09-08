import { useMemo, useRef, useState, type ChangeEvent, type DragEvent, type KeyboardEvent } from "react";
import { ArrowUp, File, FolderOpen, LoaderCircle, Paperclip, Square, Upload, X, Zap } from "lucide-react";
import { uploadFile } from "../api";
import type { Attachment, LocalDirectory, Provider, Skill } from "../types";

type Uploading = { name: string; progress: number };
type Props = {
  providers: Provider[];
  provider: string;
  onProvider: (value: string) => void;
  skills: Skill[];
  attachments: Attachment[];
  onAttachments: (value: Attachment[]) => void;
  directory: LocalDirectory | null;
  onDirectory: (value: LocalDirectory | null) => void;
  running: boolean;
  onSend: (text: string, skill: Skill | null) => void;
  onStop: () => void;
  onNotice: (message: string) => void;
};

export function Composer(props: Props) {
  const [text, setText] = useState("");
  const [skill, setSkill] = useState<Skill | null>(null);
  const [uploading, setUploading] = useState<Uploading[]>([]);
  const [dragging, setDragging] = useState(false);
  const [attachmentMenu, setAttachmentMenu] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const directoryInput = useRef<HTMLInputElement>(null);
  const menu = useMemo(() => {
    if (!text.startsWith("/") || text.includes(" ") || text.includes("\n")) return [];
    const query = text.slice(1).toLowerCase();
    return props.skills.filter((item) => item.name.includes(query) || item.description.toLowerCase().includes(query));
  }, [text, props.skills]);

  async function addFiles(files: FileList | File[]) {
    for (const file of Array.from(files)) {
      if (file.size > 50 * 1024 * 1024) { props.onNotice(`${file.name} 超过 50 MB`); continue; }
      setUploading((items) => [...items, { name: file.name, progress: 0 }]);
      try {
        const result = await uploadFile(file, (progress) => setUploading((items) => items.map((item) => item.name === file.name ? { ...item, progress } : item))) as Attachment;
        props.onAttachments([...props.attachments, result]);
      } catch (error) {
        props.onNotice(error instanceof Error ? `${file.name}：${error.message}` : "上传失败");
      } finally {
        setUploading((items) => items.filter((item) => item.name !== file.name));
      }
    }
  }

  function selectDirectory(files: FileList) {
    const selected = Array.from(files);
    if (!selected.length) return;
    const limit = 200;
    const firstPath = selected[0].webkitRelativePath || selected[0].name;
    const name = firstPath.split("/")[0] || "本地文件夹";
    props.onDirectory({
      name,
      entries: selected.slice(0, limit).map((file) => ({
        relative_path: file.webkitRelativePath || file.name,
        size: file.size,
      })),
      total_files: selected.length,
      truncated: selected.length > limit,
    });
    if (selected.length > limit) props.onNotice(`文件夹包含 ${selected.length} 个文件，仅列出前 ${limit} 个`);
  }

  function send() {
    const value = text.trim();
    if (!value || props.running || !props.provider) return;
    props.onSend(value, skill);
    setText(""); setSkill(null);
  }

  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault(); send();
    }
  }

  function drop(event: DragEvent) {
    event.preventDefault(); setDragging(false); void addFiles(event.dataTransfer.files);
  }

  return (
    <footer className="composer-zone">
      <div className={`composer-shell ${dragging ? "is-dragging" : ""}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={drop}>
        {dragging && <div className="drop-hint"><File size={20} />松开即可添加文件</div>}
        {menu.length > 0 && <div className="skill-palette">{menu.map((item) => <button key={item.name} onClick={() => { setSkill(item); setText(""); }}><Zap size={15} /><span><strong>/{item.name}</strong><small>{item.description}</small></span></button>)}</div>}
        {(props.attachments.length > 0 || uploading.length > 0 || props.directory || skill) && <div className="composer-items">
          {skill && <span className="skill-chip"><Zap size={13} />/{skill.name}<button onClick={() => setSkill(null)}><X size={12} /></button></span>}
          {props.directory && <span className="file-chip directory-chip"><FolderOpen size={13} /><span>{props.directory.name} · {props.directory.total_files} 个文件</span><button title="移除文件夹清单" onClick={() => props.onDirectory(null)}><X size={12} /></button></span>}
          {props.attachments.map((file) => <span className="file-chip" key={file.path}><File size={13} /><span>{file.name}</span><button onClick={() => props.onAttachments(props.attachments.filter((item) => item.path !== file.path))}><X size={12} /></button></span>)}
          {uploading.map((file) => <span className="file-chip is-uploading" key={file.name}><LoaderCircle className="spin" size={13} /><span>{file.name}</span><small>{file.progress}%</small></span>)}
        </div>}
        <textarea value={text} onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setText(event.target.value)} onKeyDown={keyDown} placeholder="描述任务，输入 / 选择 Skill" rows={1} />
        <div className="composer-toolbar">
          <div className="composer-left">
            <div className="attachment-picker">
              <button className="icon-button" title="添加内容" aria-expanded={attachmentMenu} onClick={() => setAttachmentMenu(!attachmentMenu)}><Paperclip size={18} /></button>
              {attachmentMenu && <div className="attachment-menu">
                <button onClick={() => { setAttachmentMenu(false); fileInput.current?.click(); }}><Upload size={16} /><span><strong>上传文件</strong><small>文件内容发送到服务器</small></span></button>
                <button onClick={() => { setAttachmentMenu(false); directoryInput.current?.click(); }}><FolderOpen size={16} /><span><strong>查看文件夹</strong><small>只提供文件名和相对路径</small></span></button>
              </div>}
            </div>
            <input ref={fileInput} hidden type="file" multiple onChange={(event) => { if (event.target.files) void addFiles(event.target.files); event.target.value = ""; }} />
            <input ref={directoryInput} hidden type="file" multiple {...({ webkitdirectory: "", directory: "" } as Record<string, string>)} onChange={(event) => { if (event.target.files) selectDirectory(event.target.files); event.target.value = ""; }} />
            <select value={props.provider} onChange={(event) => props.onProvider(event.target.value)} aria-label="选择模型">
              {props.providers.map((item) => <option value={item.name} disabled={!item.configured} key={item.name}>{item.display_name} · {item.model}{item.configured ? "" : "（未配置）"}</option>)}
            </select>
          </div>
          <button className={`send-button ${props.running ? "is-stop" : ""}`} title={props.running ? "停止任务" : "发送"} disabled={!props.running && (!text.trim() || !props.provider)} onClick={props.running ? props.onStop : send}>{props.running ? <Square size={14} fill="currentColor" /> : <ArrowUp size={18} />}</button>
        </div>
      </div>
      <div className="composer-footnote">AI 可能会出错，请核对重要结果</div>
    </footer>
  );
}
