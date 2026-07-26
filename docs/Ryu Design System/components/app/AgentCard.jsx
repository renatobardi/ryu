import React from 'react';
import { StatusPill } from '../data/StatusPill.jsx';
import { Icon } from '../core/Icon.jsx';

export function AgentCard({ name, handle, runtime, status = 'idle', description, compact, style }) {
  return (
    <div style={{
      background: compact ? 'var(--surface-card)' : 'var(--surface-column)',
      border: '1px solid var(--border-default)', borderRadius: 'var(--radius-lg)', padding: 16,
      display: 'flex', alignItems: compact ? 'center' : 'flex-start', gap: 12, fontFamily: 'var(--font-sans)', ...style,
    }}>
      {compact && (
        <div style={{ width: 36, height: 36, borderRadius: 'var(--radius-lg)', background: 'var(--surface-hover)', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}><Icon name="bot" size={18} /></div>
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <span style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--weight-medium)', color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{name}</span>
          {compact && <StatusPill kind="agent" status={status} />}
        </div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-subtle)', marginTop: 2 }}>@{handle} · {runtime}</div>
        {description && !compact && <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-muted)', marginTop: 4 }}>{description}</div>}
      </div>
      {!compact && <StatusPill kind="agent" status={status} />}
    </div>
  );
}
