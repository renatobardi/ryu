import React from 'react';
import { CountBadge } from '../data/CountBadge.jsx';

export function TopBar({ connection = 'connected', inboxCount = 0, children, style }) {
  const color = connection === 'connected' ? 'var(--emerald-500)' : connection === 'disconnected' ? 'var(--red-500)' : 'var(--text-faint)';
  return (
    <header style={{
      height: 'var(--topbar-height)', flexShrink: 0, display: 'flex', alignItems: 'center',
      justifyContent: 'flex-end', gap: 16, padding: '0 20px',
      borderBottom: '1px solid var(--border-soft)', background: 'var(--surface-chrome)', ...style,
    }}>
      {children}
      <span title="conexão realtime" style={{ fontSize: 'var(--text-2xs)', color }}>●</span>
      <a href="#" style={{ position: 'relative', fontSize: 'var(--text-sm)', color: 'var(--text-muted)', textDecoration: 'none' }}>
        Inbox
        {inboxCount > 0 && <span style={{ position: 'absolute', top: -8, right: -16 }}><CountBadge count={inboxCount} /></span>}
      </a>
    </header>
  );
}
