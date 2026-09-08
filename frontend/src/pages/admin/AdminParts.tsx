import { useState, type ReactNode } from "react";
import { Search } from "lucide-react";

export function PageHeader({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <header className="page-header"><div><h1>{title}</h1><p>{description}</p></div>{action}</header>;
}

export function SearchBox({ value, onChange, placeholder = "搜索" }: { value: string; onChange: (value: string) => void; placeholder?: string }) {
  return <label className="search-box"><Search size={15} /><input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} /></label>;
}

export function EmptyTable({ text }: { text: string }) { return <div className="empty-table">{text}</div>; }

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (value: boolean) => void; label: string }) {
  return <label className="toggle"><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} /><span /><em>{label}</em></label>;
}

export function MultiSelect({ label, options, value, onChange }: {
  label: string;
  options: Array<{ value: string; label: string }>;
  value: "*" | string[];
  onChange: (value: "*" | string[]) => void;
}) {
  const [query, setQuery] = useState("");
  const selected = value === "*" ? options.map((item) => item.value) : value;
  const visible = options.filter((item) => `${item.label} ${item.value}`.toLowerCase().includes(query.toLowerCase()));
  const toggle = (item: string) => {
    const next = selected.includes(item) ? selected.filter((value) => value !== item) : [...selected, item];
    onChange(next.length === options.length ? "*" : next);
  };
  return <label className="multi-field">{label}<details className="multi-select">
    <summary>{value === "*" ? "全部" : selected.length ? `已选择 ${selected.length} 项` : "请选择"}</summary>
    <div className="multi-menu">
      <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索" />
      <label><input type="checkbox" checked={value === "*"} onChange={(event) => onChange(event.target.checked ? "*" : [])} />全部</label>
      {visible.map((item) => <label key={item.value}><input type="checkbox" checked={selected.includes(item.value)} onChange={() => toggle(item.value)} /><span>{item.label}</span></label>)}
    </div>
  </details></label>;
}

export function formatList(value: "*" | string[]) { return value === "*" ? "全部" : value.join(", "); }
