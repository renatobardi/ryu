import React from 'react';

export function Select({ size = 'md', tone = 'raised', full, children, style, ...rest }) {
  const [focus, setFocus] = React.useState(false);
  return (
    <select
      onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
      style={{
        width: full ? '100%' : undefined, boxSizing: 'border-box',
        background: tone === 'sunken' ? 'var(--surface-input-alt)' : 'var(--surface-input)',
        border: '1px solid ' + (focus ? 'var(--border-focus)' : tone === 'sunken' ? 'var(--border-default)' : 'var(--border-strong)'),
        borderRadius: 'var(--radius-md)', padding: size === 'sm' ? '4px 8px' : '6px 8px',
        fontSize: size === 'sm' ? 'var(--text-xs)' : 'var(--text-sm)', fontFamily: 'var(--font-sans)',
        color: 'var(--text-secondary)', outline: 'none', cursor: 'pointer',
        ...style,
      }}
      {...rest}
    >{children}</select>
  );
}
