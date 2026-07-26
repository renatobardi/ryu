import React from 'react';
import { StatusDot } from '../data/StatusDot.jsx';

export function StatCard({ value, label, status, accent, hoverable, style }) {
  const [hover, setHover] = React.useState(false);
  return (
    <div onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        background: 'var(--surface-card)', border: '1px solid ' + (hoverable && hover ? 'var(--border-hover)' : 'var(--border-default)'),
        borderRadius: 'var(--radius-lg)', padding: 16, fontFamily: 'var(--font-sans)',
        transition: 'border-color var(--duration-fast) var(--ease-out)', ...style,
      }}>
      {label && !status && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-subtle)', marginBottom: 4 }}>{label}</div>}
      <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 'var(--weight-semibold)', color: accent ? 'var(--emerald-400)' : 'var(--text-primary)', lineHeight: 1.2 }}>{value}</div>
      {status && (
        <div style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 6, fontSize: 'var(--text-xs)' }}>
          <StatusDot status={status} /><span style={{ color: 'var(--text-muted)' }}>{label}</span>
        </div>
      )}
    </div>
  );
}
