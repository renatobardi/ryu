import React from 'react';

const TONES = {
  panel: 'var(--surface-card)',
  raised: 'var(--surface-raised)',
  muted: 'var(--surface-column)',
  bare: 'transparent',
};

export function Card({ tone = 'panel', dashed, hoverable, pad = 16, children, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  return (
    <div
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        background: TONES[tone] || TONES.panel,
        border: '1px ' + (dashed ? 'dashed ' : 'solid ') + (hoverable && hover ? 'var(--border-hover)' : 'var(--border-default)'),
        borderRadius: 'var(--radius-lg)', padding: pad, boxSizing: 'border-box',
        boxShadow: tone === 'bare' ? undefined : 'var(--card-shadow)',
        transition: 'border-color var(--duration-fast) var(--ease-out)',
        ...style,
      }}
      {...rest}
    >{children}</div>
  );
}
