import {
  BookOpen,
  Brain,
  ChevronLeft,
  ChevronRight,
  Database,
  Folder,
  Library,
  LogOut,
  MessageSquarePlus,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  Pin,
  Search,
  Settings,
  Sparkles,
  Trash2
} from "lucide-react";
import { useMemo, useRef, useState } from "react";
import type { Conversation, UserProfile } from "../types";

export type WorkspaceView =
  | "chat"
  | "projects"
  | "files"
  | "plugins"
  | "memories"
  | "knowledge"
  | "skills"
  | "settings";

interface SidebarProps {
  conversations: Conversation[];
  activeId: number | null;
  user: UserProfile;
  collapsed: boolean;
  mobileOpen: boolean;
  search: string;
  activeView: WorkspaceView;
  onSearch: (value: string) => void;
  onNew: () => void;
  onSelect: (id: number) => void;
  onToggleCollapsed: () => void;
  onCloseMobile: () => void;
  onPin: (conversation: Conversation) => void;
  onRename: (conversation: Conversation) => void;
  onDelete: (conversation: Conversation) => void;
  onLogout: () => void;
  onNavigate: (view: WorkspaceView) => void;
}

export function Sidebar(props: SidebarProps) {
  const [menuId, setMenuId] = useState<number | null>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const ordered = useMemo(
    () => [...props.conversations].sort((a, b) => Number(b.pinned) - Number(a.pinned)),
    [props.conversations]
  );

  return (
    <>
      {props.mobileOpen && <button className="sidebar-scrim" aria-label="关闭导航" onClick={props.onCloseMobile} />}
      <aside className={`sidebar ${props.collapsed ? "collapsed" : ""} ${props.mobileOpen ? "mobile-open" : ""}`}>
        <div className="brand-row">
          <button className="brand" onClick={props.onNew} aria-label="返回 OphAgent 新对话">
            <img src="/static/icons/system_logo.png" alt="OphAgent" />
            {!props.collapsed && <span><strong>OphAgent</strong><small>眼科诊疗增强助手</small></span>}
          </button>
          {!props.collapsed && (
            <button className="icon-button desktop-collapse" onClick={props.onToggleCollapsed} aria-label="折叠侧栏">
              <PanelLeftClose size={18} />
            </button>
          )}
          <button className="icon-button mobile-close" onClick={props.onCloseMobile} aria-label="关闭导航">
            <ChevronLeft size={20} />
          </button>
        </div>

        {props.collapsed ? (
          <>
            <button className="sidebar-icon-action" onClick={props.onToggleCollapsed} aria-label="展开侧栏"><PanelLeftOpen size={19} /></button>
            <button className="sidebar-icon-action" onClick={props.onNew} aria-label="新对话"><MessageSquarePlus size={19} /></button>
            <button className="sidebar-icon-action" onClick={() => {
              props.onToggleCollapsed();
              window.setTimeout(() => searchInput.current?.focus());
            }} aria-label="搜索"><Search size={19} /></button>
            <button className="sidebar-icon-action" onClick={() => props.onNavigate("files")} aria-label="文件库"><Library size={19} /></button>
            <button className="sidebar-icon-action" onClick={() => props.onNavigate("settings")} aria-label="设置"><Settings size={19} /></button>
            <div className="collapsed-spacer" />
          </>
        ) : (
          <>
            <button className="new-conversation" onClick={props.onNew}><MessageSquarePlus size={18} />新对话</button>
            <label className="sidebar-search">
              <Search size={16} />
              <span className="sr-only">搜索对话</span>
              <input ref={searchInput} value={props.search} onChange={(event) => props.onSearch(event.target.value)} placeholder="搜索" />
            </label>
            <section className="recent-section">
              <div className="section-label"><span>最近</span></div>
              <div className="conversation-list">
                {ordered.map((conversation) => (
                  <div className={`conversation-row ${props.activeId === conversation.id ? "active" : ""}`} key={conversation.id}>
                    <button className="conversation-select" onClick={() => props.onSelect(conversation.id)}>
                      {conversation.pinned && <Pin size={12} />}
                      <span>{conversation.title}</span>
                    </button>
                    <button
                      className="row-menu-button"
                      aria-label={`${conversation.title}的更多操作`}
                      aria-expanded={menuId === conversation.id}
                      onClick={() => setMenuId((value) => value === conversation.id ? null : conversation.id)}
                    >
                      <MoreHorizontal size={16} />
                    </button>
                    {menuId === conversation.id && (
                      <div className="row-menu">
                        <button onClick={() => { props.onPin(conversation); setMenuId(null); }}><Pin size={14} />{conversation.pinned ? "取消置顶" : "置顶"}</button>
                        <button onClick={() => { props.onRename(conversation); setMenuId(null); }}><ChevronRight size={14} />重命名</button>
                        <button className="danger" onClick={() => { props.onDelete(conversation); setMenuId(null); }}><Trash2 size={14} />删除</button>
                      </div>
                    )}
                  </div>
                ))}
                {!ordered.length && <p className="sidebar-empty">还没有对话</p>}
              </div>
            </section>
            <nav className="resource-nav" aria-label="工作区">
              <button className={props.activeView === "projects" ? "active" : ""} onClick={() => props.onNavigate("projects")}><Folder size={17} /><span>项目</span></button>
              <button className={props.activeView === "files" ? "active" : ""} onClick={() => props.onNavigate("files")}><Library size={17} /><span>文件库</span></button>
              <button className={props.activeView === "plugins" ? "active" : ""} onClick={() => props.onNavigate("plugins")}><BookOpen size={17} /><span>插件</span></button>
              <button className={props.activeView === "memories" ? "active" : ""} onClick={() => props.onNavigate("memories")}><Brain size={17} /><span>记忆</span></button>
              <button className={props.activeView === "knowledge" ? "active" : ""} onClick={() => props.onNavigate("knowledge")}><Database size={17} /><span>知识库</span></button>
              <button className={props.activeView === "skills" ? "active" : ""} onClick={() => props.onNavigate("skills")}><Sparkles size={17} /><span>技能</span></button>
              <button className={props.activeView === "settings" ? "active" : ""} onClick={() => props.onNavigate("settings")}><Settings size={17} /><span>设置</span></button>
            </nav>
          </>
        )}

        <div className="account-row">
          <span className="avatar">{props.user.username.slice(0, 1).toUpperCase()}</span>
          {!props.collapsed && <span className="account-name"><strong>{props.user.username}</strong><small>完整功能账户</small></span>}
          {!props.collapsed && <button className="icon-button" onClick={props.onLogout} aria-label="退出登录"><LogOut size={17} /></button>}
        </div>
      </aside>
    </>
  );
}
