import React from 'react';

export function CountBadge({ count = 0, tone = 'accent', hideZero = true, style }) {
  if (hideZero && !count) return null;
  return (
    <span style={{
      display: 'inline-block', minWidth: 18, textAlign: 'center',
      fontSize: 'var(--text-2xs)', fontWeight: 'var(--weight-semibold)', fontFamily: 'var(--font-sans)',
      borderRadius: 'var(--radius-full)', padding: '2px 6px',
      background: tone === 'accent' ? 'var(--accent)' : 'var(--zinc-800)',
      color: tone === 'accent' ? 'var(--text-on-accent)' : 'var(--text-muted)', ...style,
    }}>{count}</span>
  );
}
