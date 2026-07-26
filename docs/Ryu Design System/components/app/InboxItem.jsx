import React from 'react';

const SEV = { action_required: 'var(--red-500)', attention: 'var(--amber-400)', info: 'var(--zinc-500)' };
const SEV_LABEL = { action_required: 'Ação necessária', attention: 'Atenção', info: 'Info' };

export function InboxItem({ severity = 'info', title, body, time, read, children, style }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: 12, padding: '16px 24px',
      background: read ? 'transparent' : 'var(--surface-column)',
      borderBottom: '1px solid var(--border-default)', ...style,
    }}>
      <span style={{ marginTop: 4, width: 8, height: 8, borderRadius: 'var(--radius-full)', background: SEV[severity], flexShrink: 0 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 'var(--text-sm)', fontFamily: 'var(--font-sans)', color: read ? 'var(--text-muted)' : 'var(--text-primary)', fontWeight: read ? 'var(--weight-normal)' : 'var(--weight-medium)' }}>{title}</span>
          <span style={{ fontSize: 'var(--text-2xs)', textTransform: 'uppercase', letterSpacing: 'var(--tracking-wide)', color: 'var(--text-subtle)' }}>{SEV_LABEL[severity]}</span>
        </div>
        {body && <p style={{ margin: '2px 0 0', fontSize: 'var(--text-xs)', color: 'var(--text-subtle)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{body}</p>}
        {time && <p style={{ margin: '4px 0 0', fontSize: 'var(--text-11)', color: 'var(--text-faint)' }}>{time}</p>}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>{children}</div>
    </div>
  );
}
