import React from 'react';
import { Input } from '../core/Input.jsx';
import { Button } from '../core/Button.jsx';
import { Icon } from '../core/Icon.jsx';

export function Sidebar({ user, onSearch, children, onProfileClick, style }) {
  const initials = user ? (user.nickname || user.name || '?').trim().split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase() : '';
  return (
    <aside style={{
      width: 'var(--sidebar-width)', flexShrink: 0, display: 'flex', flexDirection: 'column',
      borderRight: '1px solid var(--border-soft)', background: 'var(--surface-chrome)', ...style,
    }}>
      <div style={{ padding: '18px 16px', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 29, lineHeight: 1, color: 'var(--text-primary)', flexShrink: 0 }}>龍</span>
        <div>
          <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: '-0.03em', color: 'var(--text-primary)', lineHeight: 1 }}>Ryu</div>
          <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-subtle)' }}>Agentic issue tracking</div>
        </div>
      </div>
      <div style={{ padding: '12px 8px 0', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <Input size="sm" placeholder="Search  ⌘K" onChange={onSearch} />
        <Button full size="sm" style={{ gap: 6 }}><Icon name="plus" size={14} /> New Issue</Button>
      </div>
      <nav style={{ flex: 1, overflowY: 'auto', padding: '12px 8px', display: 'flex', flexDirection: 'column', gap: 2 }}>{children}</nav>
      {user && (
        <button type="button" onClick={onProfileClick} style={{
          margin: 8, padding: '8px', display: 'flex', alignItems: 'center', gap: 8,
          background: 'transparent', border: 'none', borderRadius: 'var(--radius-md)', cursor: 'pointer', textAlign: 'left',
          transition: 'background var(--duration-fast) var(--ease-out)',
        }}
          onMouseEnter={(e) => e.currentTarget.style.background = 'var(--surface-hover)'}
          onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
        >
          {user.avatar ? (
            <img src={user.avatar} alt="" style={{ width: 28, height: 28, borderRadius: 'var(--radius-full)', objectFit: 'cover', flexShrink: 0 }} />
          ) : (
            <div style={{ width: 28, height: 28, borderRadius: 'var(--radius-full)', background: 'var(--surface-active)', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 'var(--text-2xs)', fontWeight: 'var(--weight-semibold)', flexShrink: 0 }}>{initials}</div>
          )}
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user.nickname || user.name}</span>
        </button>
      )}
    </aside>
  );
}

export function SidebarSection({ children }) {
  return <div style={{ padding: '12px 12px 4px', fontSize: 'var(--text-2xs)', textTransform: 'uppercase', letterSpacing: 'var(--tracking-wider)', color: 'var(--text-faint)' }}>{children}</div>;
}
