import { t } from "../i18n";
import { type Dispatch, type SetStateAction, useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent, type KeyboardEvent } from "react";
import { ArrowUp, ChevronDown, File, FolderOpen, LoaderCircle, Plus, Square, Upload, X, Zap } from "lucide-react";
import { VoiceInput } from "./VoiceInput";
import { uploadFile } from "../api";
import type { Attachment, LocalDirectory, Provider, Skill } from "../types";

type Uploading = { name: string; progress: number };
type Props = {
  providers: Provider[];
  provider: string;
  onProvider: (value: string) => void;
  skills: Skill[];
  attachments: Attachment[];
  onAttachments: Dispatch<SetStateAction<Attachment[]>>;
  directory: LocalDirectory | null;
  onDirectory: (value: LocalDirectory | null) => void;
  running: boolean;
  onSend: (text: string, skill: Skill | null) => Promise<boolean>;
  onStop: () => void;
  onNotice: (message: string) => void;
};

export function Composer(props: Props) {
  const previews = useRef<Record<string, string>>({});
  useEffect(() => () => { Object.values(previews.current).forEach(url => URL.revokeObjectURL(url)); }, []);
  useEffect(() => {
    for (const [path, url] of Object.entries(previews.current)) {
      if (!props.attachments.some(file => file.path === path)) { URL.revokeObjectURL(url); delete previews.current[path]; }
    }
  }, [props.attachments]);
  const [sending, setSending] = useState(false);
  const [text, setText] = useState("");
  const [skill, setSkill] = useState<Skill | null>(null);
  const [uploading, setUploading] = useState<Uploading[]>([]);
  const [dragging, setDragging] = useState(false);
  const [attachmentMenu, setAttachmentMenu] = useState(false);
  const [skillPicker, setSkillPicker] = useState(false);
  const [skillQuery, setSkillQuery] = useState("");
  const [slashDismissed, setSlashDismissed] = useState(false);
  const popupRoot = useRef<HTMLDivElement>(null);
  const addButton = useRef<HTMLButtonElement>(null);
  const slashOpen = !slashDismissed && text.startsWith("/") && !/[ \n]/.test(text);
  useEffect(() => {
    if (!attachmentMenu && !skillPicker && !slashOpen) return;
    const dismiss = () => { setAttachmentMenu(false); setSkillPicker(false); setSlashDismissed(true); };
    const outside = (event: Event) => {
      const target = event.target as Node;
      if (!popupRoot.current?.contains(target) && target !== textarea.current) dismiss();
      else if (target === textarea.current) { setAttachmentMenu(false); setSkillPicker(false); }
    };
    const escape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); dismiss(); addButton.current?.focus(); }
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("focusin", outside);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("focusin", outside); document.removeEventListener("keydown", escape); };
  }, [attachmentMenu, skillPicker, slashOpen]);
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState("");
  const beforeVoice = useRef("");
  const textarea = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const element = textarea.current;
    if (element) { element.style.height = "auto"; element.style.height = `${Math.min(element.scrollHeight, 160)}px`; }
  }, [text, voiceBusy]);
  const fileInput = useRef<HTMLInputElement>(null);
  const directoryInput = useRef<HTMLInputElement>(null);
  const menu = useMemo(() => {
    const query = (skillPicker ? skillQuery : text.slice(1)).toLowerCase();
    return props.skills.filter(item => [item.name, item.description, item.display_name, item.display_description].some(value => value?.toLowerCase().includes(query)));
  }, [text, skillQuery, skillPicker, props.skills]);
  function chooseSkill(item: Skill) {
    setSkill(item); if (slashOpen) setText("");
    setSkillPicker(false); setAttachmentMenu(false); setSlashDismissed(true);
    textarea.current?.focus();
  }

  async function addFiles(files: FileList | File[]) {
    for (const file of Array.from(files)) {
      if (file.size > 50 * 1024 * 1024) { props.onNotice(t("{{value0}} 超过 50 MB", { value0: file.name })); continue; }
      setUploading((items) => [...items, { name: file.name, progress: 0 }]);
      try {
        const result = await uploadFile(file, (progress) => setUploading((items) => items.map((item) => item.name === file.name ? { ...item, progress } : item))) as Attachment;
        if (file.type.startsWith("image/")) previews.current[result.path] = URL.createObjectURL(file);
        props.onAttachments(items => [...items, result]);
      } catch (error) {
        props.onNotice(error instanceof Error ? `${file.name}：${error.message}` : t("上传失败"));
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
    if (selected.length > limit) props.onNotice(t("文件夹包含 {{value0}} 个文件，仅列出前 {{value1}} 个", { value0: selected.length, value1: limit }));
  }

  async function send(voiceText?: string) {
    const value = (voiceText ?? text).trim();
    if (!value || sending || (voiceBusy && voiceText === undefined) || uploading.length || !props.provider) return;
    setSending(true);
    try { if (await props.onSend(value, skill)) { setText(""); setSkill(null); } } finally { setSending(false); }
  }

  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && !window.matchMedia("(pointer: coarse)").matches) {
      event.preventDefault(); send();
    }
  }

  function drop(event: DragEvent) {
    event.preventDefault(); setDragging(false); void addFiles(event.dataTransfer.files);
  }

  return (
    <footer className="composer-zone">
      <div className={`composer-shell ${voiceBusy ? "is-voice-active" : ""} ${dragging ? "is-dragging" : ""}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={drop}>
        {dragging && <div className="drop-hint"><File size={20} />{t("松开即可添加文件")}</div>}

        {(props.attachments.length > 0 || uploading.length > 0 || props.directory || skill) && <div className="composer-items">
          {skill && <span className="skill-chip"><Zap size={13} />{skill.display_name || skill.name}<button aria-label={t("移除技能")} onClick={() => setSkill(null)}><X size={12} /></button></span>}
          {props.directory && <span className="file-chip directory-chip"><FolderOpen size={13} /><span>{props.directory.name} · {props.directory.total_files}  {t("个文件")}</span><button title={t("移除文件夹清单")} onClick={() => props.onDirectory(null)}><X size={12} /></button></span>}
          {props.attachments.map((file) => <span className={`file-chip ${previews.current[file.path] ? "image-chip" : ""}`} key={file.path}>{previews.current[file.path] ? <img src={previews.current[file.path]} alt={file.name} /> : <File size={13} />}<span>{file.name}</span><button aria-label={t("移除附件 {{value0}}", { value0: file.name })} onClick={() => props.onAttachments(props.attachments.filter((item) => item.path !== file.path))}><X size={12} /></button></span>)}
          {uploading.map((file) => <span className="file-chip is-uploading" key={file.name}><LoaderCircle className="spin" size={13} /><span>{file.name}</span><small>{file.progress}%</small></span>)}
        </div>}
        <textarea hidden={voiceBusy} ref={textarea} aria-label={t("任务内容")} value={text} onChange={(event: ChangeEvent<HTMLTextAreaElement>) => { setText(event.target.value); setSlashDismissed(false); }} onKeyDown={keyDown} placeholder={t("输入任务，输入 / 选择技能")} rows={1} />
        {voiceBusy && text && <div className="voice-draft">{text}</div>}
        {voiceStatus && /响应较慢|回應較慢|未识别|未識別|未辨識|失败|失敗|错误|錯誤|Recognition is taking longer|No speech detected|failed|error/i.test(voiceStatus) && <div className="voice-status" role="status">{voiceStatus}</div>}
        <div className="composer-toolbar">
          <div className="composer-left">
            <div className="attachment-picker" ref={popupRoot}>
              <button ref={addButton} className="icon-button add-content" title={t("添加内容")} aria-label={t("添加文件或选择技能")} aria-expanded={attachmentMenu || skillPicker || slashOpen} onClick={() => { setAttachmentMenu(!attachmentMenu && !skillPicker); setSkillPicker(false); setSlashDismissed(true); }}><Plus size={23} /></button>
              {(skillPicker || slashOpen) && <div className="skill-palette" role="region" aria-label={t("选择技能")}>
                <div className="skill-picker-heading"><strong>{t("选择技能")}</strong><button aria-label={t("关闭技能选择")} onClick={() => { setSkillPicker(false); setSlashDismissed(true); addButton.current?.focus(); }}><X size={16} /></button></div>
                {skillPicker && <input className="skill-search" aria-label={t("搜索技能")} placeholder={t("搜索技能名称或用途")} value={skillQuery} onChange={event => setSkillQuery(event.target.value)} />}
                <div className="skill-results">{menu.map(item => <button key={item.name} onClick={() => chooseSkill(item)}><span><strong>{item.display_name || item.name}</strong><small>{item.display_description || item.description}</small></span></button>)}{!menu.length && <p>{t("没有找到匹配的技能")}</p>}</div>
              </div>}
              {attachmentMenu && <div className="attachment-menu" role="region" aria-label={t("添加内容")}>
                <button className="skill-menu-entry" onClick={() => { setAttachmentMenu(false); setSkillPicker(true); setSkillQuery(""); }}><img className="skill-entry-avatar" src="/static/assistant-avatar.png" alt="" width={28} height={28} /><span><strong>{t("选择技能")}</strong><small>{t("搜索企业技能，按用途选择")}</small></span></button>
                <button onClick={() => { setAttachmentMenu(false); fileInput.current?.click(); }}><Upload size={16} /><span><strong>{t("上传文件")}</strong><small>{t("文件内容发送到服务器")}</small></span></button>
                <button onClick={() => { setAttachmentMenu(false); directoryInput.current?.click(); }}><FolderOpen size={16} /><span><strong>{t("查看文件夹")}</strong><small>{t("只提供文件名和相对路径")}</small></span></button>
              </div>}
            </div>
            <input ref={fileInput} hidden type="file" multiple onChange={(event) => { if (event.target.files) void addFiles(event.target.files); event.target.value = ""; }} />
            <input ref={directoryInput} hidden type="file" multiple {...({ webkitdirectory: "", directory: "" } as Record<string, string>)} onChange={(event) => { if (event.target.files) selectDirectory(event.target.files); event.target.value = ""; }} />
            <span className="model-picker"><select value={props.provider} onChange={(event) => props.onProvider(event.target.value)} aria-label={t("选择模型")}>
              {props.providers.map((item) => <option value={item.name} disabled={!item.configured} key={item.name}>{item.display_name}{item.configured ? "" : t("（未配置）")}</option>)}
            </select><ChevronDown size={15} aria-hidden="true" /></span>
          </div>
          <div className="composer-send-actions">
            {props.running && !voiceBusy && <button className="icon-button" title={t("停止当前任务")} aria-label={t("停止当前任务")} onClick={props.onStop}><Square size={16} /></button>}
            <VoiceInput disabled={sending} onText={value => setText(previous => previous ? `${previous}${/[\s，。！？,.!?]$/.test(previous) ? "" : " "}${value}` : value)} onNotice={props.onNotice} onBusy={busy => { if (busy) beforeVoice.current = text; setVoiceBusy(busy); }} onStatus={setVoiceStatus}
              onCancel={() => setText(beforeVoice.current)}
              onSubmit={transcript => void send([beforeVoice.current, transcript].filter(Boolean).join(" "))} />
            <button className="send-button" hidden={voiceBusy} title={props.running ? t("排队发送") : t("发送")} aria-label={props.running ? t("排队发送") : t("发送")} disabled={sending || voiceBusy || uploading.length > 0 || !text.trim() || !props.provider} onClick={() => void send()}><ArrowUp size={18} /></button>
          </div>
        </div>
      </div>
      <div className="composer-footnote">{t("点击麦克风说话 · AI 可能会出错，请核对重要结果")}</div>
    </footer>
  );
}
