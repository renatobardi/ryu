import React from 'react';

export function BoardColumn({ title, count = 0, children, style }) {
  return (
    <div style={{
      width: 'var(--board-column-width)', flexShrink: 0, display: 'flex', flexDirection: 'column',
      background: 'var(--surface-column)', borderRadius: 'var(--radius-lg)', border: '1px solid var(--border-default)', ...style,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', borderBottom: '1px solid var(--border-default)' }}>
        <span style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--weight-medium)', color: 'var(--text-secondary)', fontFamily: 'var(--font-sans)' }}>{title}</span>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-subtle)' }}>{count}</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: 8, minHeight: 80, flex: 1 }}>{children}</div>
    </div>
  );
}
