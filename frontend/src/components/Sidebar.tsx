import { t } from "../i18n";
import { useEffect, useId, useRef, useState } from "react";
import { AccountAvatar } from "./AccountAvatar";
import { ChevronDown, ExternalLink, LogOut, MessageSquare, PanelLeftClose, Plus, Settings, Trash2 } from "lucide-react";
import { formatTime } from "../api";
import type { Identity, Session } from "../types";
import { Brand } from "./Brand";

type Props = {
  identity: Identity;
  sessions: Session[];
  runningIds?: Set<string>;
  activeId: string;
  open: boolean;
  onClose: () => void;
  onNew: () => void;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  onLogout: () => void;
};

export function Sidebar(props: Props) {
  const [expanded, setExpanded] = useState(false);
  const historyId = useId();
  const panel = useRef<HTMLElement>(null);
  const [previewCount, setPreviewCount] = useState(5);
  useEffect(() => {
    if (!panel.current) return;
    const observer = new ResizeObserver(([entry]) => setPreviewCount(Math.max(1, Math.min(5, Math.floor((entry.contentRect.height - 300) / 49)))));
    observer.observe(panel.current);
    return () => observer.disconnect();
  }, []);
  const showAll = expanded && props.sessions.length > previewCount;
  const visibleSessions = showAll ? props.sessions : props.sessions.slice(0, previewCount);
  return (
    <>
      {props.open && <button className="sidebar-backdrop" aria-label={t("关闭导航")} onClick={props.onClose} />}
      <aside ref={panel} className={`sidebar ${props.open ? "is-open" : ""}`} inert={!props.open} onKeyDown={event => { if (event.key === "Escape") props.onClose(); }}>
        <div className="sidebar-brand"><Brand /><button className="icon-button sidebar-close" title={t("收起侧栏")} onClick={props.onClose}><PanelLeftClose size={17} /></button></div>
        <button className="new-task-card" onClick={props.onNew} aria-label={t("新任务")}><Plus size={17} /><span>{t("新任务")}</span></button>
        <div className="section-caption">{t("最近任务")}</div>
        <div id={historyId} className={`session-list ${showAll ? "is-expanded" : "is-collapsed"}`} tabIndex={showAll ? 0 : undefined} aria-label={t("最近任务列表")}>
          {props.sessions.length === 0 && <div className="session-empty">{t("还没有历史会话")}</div>}
          {visibleSessions.map((session) => (
            <div className={`session-row ${session.id === props.activeId ? "is-active" : ""}`} key={session.id}>
              <button className="session-main" onClick={() => props.onOpen(session.id)}>
                <MessageSquare size={15} />
                <span><strong>{session.title}</strong><small>{props.runningIds?.has(session.id) ? t("执行中 / 排队中") : formatTime(session.updated_at)}</small></span>
              </button>
              <button className="session-delete" title={t("删除会话")} onClick={() => props.onDelete(session.id)}><Trash2 size={14} /></button>
            </div>
          ))}
        </div>
        {props.sessions.length > previewCount && <button className="session-more" aria-controls={historyId} aria-expanded={showAll} onClick={() => setExpanded(value => !value)}>{showAll ? t("收起") : t("更多")}<ChevronDown size={14} /></button>}
        <div className="sidebar-footer">
          <div className="account"><span className="account-avatar"><AccountAvatar /></span><span><strong>{props.identity.username}</strong><small>{props.identity.role}</small></span></div>
          <div className="footer-actions">
            {(props.identity.is_admin || props.identity.manage_skills) && <a className="icon-button" href={props.identity.is_admin ? "/admin/users" : "/admin/skills"} title={props.identity.is_admin ? t("系统管理") : t("技能管理")}><Settings size={17} /></a>}
            <a className="icon-button" href="http://czon.cn" target="_blank" rel="noreferrer noopener" title={t("访问官网")}><ExternalLink size={17} /></a>
            <button className="icon-button" title={t("退出登录")} onClick={props.onLogout}><LogOut size={17} /></button>
          </div>
        </div>
      </aside>
    </>
  );
}
