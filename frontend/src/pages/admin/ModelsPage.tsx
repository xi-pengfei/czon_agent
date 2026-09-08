import { useEffect, useState, type FormEvent } from "react";
import { Bot, CheckCircle2, CircleMinus, KeyRound, Pencil, Plus, RefreshCw, Wifi, XCircle } from "lucide-react";
import { api } from "../../api";
import { Modal } from "../../components/Modal";
import type { ModelRecord } from "../../types";
import { EmptyTable, PageHeader } from "./AdminParts";

type ModelDraft = ModelRecord & { api_key?: string };
type ProbeCheck = { ok: boolean | null; latency_ms: number; detail: string };
type ProbeResult = { ok: boolean; latency_ms: number; models: string[]; checks: Record<"models" | "chat" | "streaming" | "tools", ProbeCheck> };

const presets = [
  { id: "kimi", label: "Moonshot / Kimi", base_url: "https://api.moonshot.cn/v1", vision: true, tools: true, streaming: true },
  { id: "qwen", label: "阿里云 / 通义千问", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", vision: true, tools: true, streaming: true },
  { id: "deepseek", label: "DeepSeek", base_url: "https://api.deepseek.com/v1", vision: false, tools: true, streaming: true },
  { id: "ollama", label: "Ollama（本机私有模型）", base_url: "http://127.0.0.1:11434/v1", vision: false, tools: true, streaming: true, defaultName: "ollama", displayName: "Ollama", apiKey: "ollama" },
];
const blank: ModelDraft = { name: "", display_name: "", base_url: "", model: "", supports_vision: false, supports_tools: true, supports_streaming: true, enabled: true, api_key: "" };

export function ModelsPage() {
  const [models, setModels] = useState<ModelRecord[]>([]);
  const [editing, setEditing] = useState<ModelDraft | null>(null);
  const [discovered, setDiscovered] = useState<string[]>([]);
  const [probing, setProbing] = useState(false);
  const [probeResult, setProbeResult] = useState<ProbeResult | null>(null);
  const [notice, setNotice] = useState("");
  const load = () => api<{ models: ModelRecord[] }>("/api/admin/models").then((data) => setModels(data.models));
  useEffect(() => { void load(); }, []);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!editing) return;
    const value = {
      name: editing.name,
      display_name: editing.display_name,
      base_url: editing.base_url,
      model: editing.model,
      api_key: editing.api_key || null,
      supports_vision: editing.supports_vision,
      supports_tools: editing.supports_tools,
      supports_streaming: editing.supports_streaming,
      enabled: editing.enabled,
    };
    try { await api(`/api/admin/models/${encodeURIComponent(value.name)}`, { method: "PUT", body: JSON.stringify(value) }); setEditing(null); setNotice("模型配置已保存"); await load(); }
    catch (error) { setNotice((error as Error).message); }
  }

  function choosePreset(id: string) {
    if (!editing || id === "custom") return;
    const preset = presets.find((item) => item.id === id)!;
    setEditing({
      ...editing,
      name: editing.name || ("defaultName" in preset ? preset.defaultName || "" : ""),
      display_name: editing.display_name || ("displayName" in preset ? preset.displayName || "" : ""),
      base_url: preset.base_url,
      api_key: editing.api_key || (!editing.api_key_configured && "apiKey" in preset ? preset.apiKey : ""),
      supports_vision: preset.vision,
      supports_tools: preset.tools,
      supports_streaming: preset.streaming,
    });
    setDiscovered([]); setProbeResult(null);
  }

  async function probe() {
    if (!editing) return;
    setProbing(true);
    try {
      const result = await api<ProbeResult>("/api/admin/models/probe", { method: "POST", body: JSON.stringify({ name: editing.name || null, base_url: editing.base_url, model: editing.model || null, api_key: editing.api_key || null }) });
      setDiscovered(result.models);
      setProbeResult(result);
      setNotice(editing.model ? (result.ok ? "模型能力测试全部通过" : "模型能力测试完成，请查看各项结果") : "已获取模型列表，请选择模型后再次测试");
    } catch (error) { setNotice((error as Error).message); }
    finally { setProbing(false); }
  }

  return <main className="admin-content">
    <PageHeader title="模型配置" description="管理 OpenAI 兼容模型与访问密钥" action={<button className="primary-button compact" onClick={() => setEditing(blank)}><Plus size={16} />添加模型</button>} />
    <div className="data-table"><table><thead><tr><th>模型</th><th>接口地址</th><th>视觉</th><th>API Key</th><th>状态</th><th>操作</th></tr></thead><tbody>{models.map((model) => <tr key={model.name}>
      <td><div className="model-cell"><span><Bot size={16} /></span><div><strong>{model.display_name}</strong><small>{model.model}</small></div></div></td>
      <td className="limited-cell">{model.base_url}</td><td>{[model.supports_vision && "视觉", model.supports_tools && "工具", model.supports_streaming && "流式"].filter(Boolean).join(" · ") || "文本"}</td>
      <td>{model.api_key_configured ? <span className="status success"><CheckCircle2 size={13} />已配置</span> : <span className="status warning"><KeyRound size={13} />未配置</span>}</td>
      <td>{model.enabled ? <span className="status success">启用</span> : <span className="status">停用</span>}</td>
      <td><button className="text-button" onClick={() => setEditing(model)}><Pencil size={14} />编辑</button></td>
    </tr>)}</tbody></table>{!models.length && <EmptyTable text="暂无模型配置" />}</div>
    {editing && <Modal title={editing.name ? `编辑 ${editing.display_name}` : "添加模型"} onClose={() => setEditing(null)}><form className="modal-form" onSubmit={save}>
      <label>接口类型<select value={presets.find((item) => item.base_url === editing.base_url)?.id || "custom"} onChange={(event) => choosePreset(event.target.value)}><option value="custom">自定义 OpenAI 兼容接口</option>{presets.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select></label>
      <div className="form-grid"><label>配置名称<input value={editing.name} onChange={(event) => setEditing({ ...editing, name: event.target.value })} readOnly={models.some((item) => item.name === editing.name)} placeholder="company_model" required /></label><label>显示名称<input value={editing.display_name} onChange={(event) => setEditing({ ...editing, display_name: event.target.value })} required /></label></div>
      <label>Base URL<input value={editing.base_url} onChange={(event) => { setEditing({ ...editing, base_url: event.target.value }); setDiscovered([]); setProbeResult(null); }} placeholder="https://api.example.com/v1" required /></label>
      <label>API Key<input value={editing.api_key || ""} onChange={(event) => setEditing({ ...editing, api_key: event.target.value })} type="password" autoComplete="new-password" placeholder={editing.api_key_configured ? "留空表示保留当前 Key" : "输入 API Key"} required={!editing.api_key_configured} /><small>密钥仅在提交时传给服务器，保存后不再显示</small></label>
      <div className="probe-row"><button type="button" className="secondary-button compact" disabled={probing || !editing.base_url} onClick={probe}>{probing ? <RefreshCw className="spin" size={14} /> : <Wifi size={14} />}测试连接与模型能力</button>{discovered.length > 0 && <span>已发现 {discovered.length} 个模型</span>}</div>
      <label>模型名称<input list="discovered-models" value={editing.model} onChange={(event) => { setEditing({ ...editing, model: event.target.value }); setProbeResult(null); }} placeholder={discovered.length ? "选择或搜索模型" : "填写模型 ID"} required /><datalist id="discovered-models">{discovered.map((name) => <option value={name} key={name} />)}</datalist></label>
      {probeResult && <div className="probe-results">
        <ProbeItem label="模型列表" value={probeResult.checks.models} />
        <ProbeItem label="普通对话" value={probeResult.checks.chat} />
        <ProbeItem label="流式输出" value={probeResult.checks.streaming} />
        <ProbeItem label="工具调用" value={probeResult.checks.tools} />
      </div>}
      <fieldset className="capability-field"><legend>模型能力</legend><label><input type="checkbox" checked={editing.supports_vision} onChange={(event) => setEditing({ ...editing, supports_vision: event.target.checked })} />视觉 / 多模态</label><label><input type="checkbox" checked={editing.supports_tools} onChange={(event) => setEditing({ ...editing, supports_tools: event.target.checked })} />工具调用</label><label><input type="checkbox" checked={editing.supports_streaming} onChange={(event) => setEditing({ ...editing, supports_streaming: event.target.checked })} />流式输出</label></fieldset>
      <label className="check-field"><input type="checkbox" checked={editing.enabled} onChange={(event) => setEditing({ ...editing, enabled: event.target.checked })} />启用模型</label>
      <div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setEditing(null)}>取消</button><button className="primary-button">保存配置</button></div>
    </form></Modal>}
    {notice && <button className="toast" onClick={() => setNotice("")}>{notice}</button>}
  </main>;
}

function ProbeItem({ label, value }: { label: string; value: ProbeCheck }) {
  const Icon = value.ok === true ? CheckCircle2 : value.ok === false ? XCircle : CircleMinus;
  return <div className={value.ok === true ? "is-pass" : value.ok === false ? "is-fail" : "is-skip"}><Icon size={15} /><span><strong>{label}</strong><small>{value.detail}{value.ok !== null ? ` · ${value.latency_ms} ms` : ""}</small></span></div>;
}
