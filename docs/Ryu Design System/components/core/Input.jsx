import React from 'react';

export function Input({ size = 'md', tone = 'raised', full = true, style, ...rest }) {
  const [focus, setFocus] = React.useState(false);
  const pad = size === 'sm' ? '6px 10px' : size === 'lg' ? '8px 12px' : '6px 12px';
  const fs = size === 'sm' ? 'var(--text-xs)' : 'var(--text-sm)';
  return (
    <input
      onFocus={(e) => { setFocus(true); rest.onFocus && rest.onFocus(e); }}
      onBlur={(e) => { setFocus(false); rest.onBlur && rest.onBlur(e); }}
      style={{
        width: full ? '100%' : undefined, boxSizing: 'border-box',
        background: tone === 'sunken' ? 'var(--surface-input-alt)' : 'var(--surface-input)',
        border: '1px solid ' + (focus ? 'var(--border-focus)' : tone === 'sunken' ? 'var(--border-default)' : 'var(--border-strong)'),
        borderRadius: 'var(--radius-md)', padding: pad, fontSize: fs, fontFamily: 'var(--font-sans)',
        color: 'var(--text-primary)', outline: 'none',
        transition: 'border-color var(--duration-fast) var(--ease-out)',
        ...style,
      }}
      {...rest}
    />
  );
}
