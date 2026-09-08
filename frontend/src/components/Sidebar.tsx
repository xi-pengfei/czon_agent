import { ExternalLink, LogOut, MessageSquare, PanelLeftClose, Plus, Settings, Trash2 } from "lucide-react";
import { formatTime } from "../api";
import type { Identity, Session } from "../types";
import { Brand } from "./Brand";

type Props = {
  identity: Identity;
  sessions: Session[];
  activeId: string;
  open: boolean;
  onClose: () => void;
  onNew: () => void;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  onLogout: () => void;
};

export function Sidebar(props: Props) {
  return (
    <>
      {props.open && <button className="sidebar-backdrop" aria-label="关闭导航" onClick={props.onClose} />}
      <aside className={`sidebar ${props.open ? "is-open" : ""}`}>
        <div className="sidebar-brand"><Brand /><button className="icon-button sidebar-close" title="收起侧栏" onClick={props.onClose}><PanelLeftClose size={17} /></button></div>
        <button className="new-chat" onClick={props.onNew}><Plus size={17} /><span>新对话</span></button>
        <div className="section-caption">最近对话</div>
        <div className="session-list">
          {props.sessions.length === 0 && <div className="session-empty">还没有历史会话</div>}
          {props.sessions.map((session) => (
            <div className={`session-row ${session.id === props.activeId ? "is-active" : ""}`} key={session.id}>
              <button className="session-main" onClick={() => props.onOpen(session.id)}>
                <MessageSquare size={15} />
                <span><strong>{session.title}</strong><small>{formatTime(session.updated_at)}</small></span>
              </button>
              <button className="session-delete" title="删除会话" onClick={() => props.onDelete(session.id)}><Trash2 size={14} /></button>
            </div>
          ))}
        </div>
        <div className="sidebar-footer">
          <div className="account"><span className="account-avatar">{props.identity.username.slice(0, 1).toUpperCase()}</span><span><strong>{props.identity.username}</strong><small>{props.identity.role}</small></span></div>
          <div className="footer-actions">
            {props.identity.is_admin && <a className="icon-button" href="/admin/users" title="系统管理"><Settings size={17} /></a>}
            <a className="icon-button" href="http://czon.cn" target="_blank" rel="noreferrer noopener" title="访问官网"><ExternalLink size={17} /></a>
            <button className="icon-button" title="退出登录" onClick={props.onLogout}><LogOut size={17} /></button>
          </div>
        </div>
      </aside>
    </>
  );
}
