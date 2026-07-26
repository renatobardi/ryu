import React from 'react';

export function Textarea({ tone = 'raised', mono, rows = 3, style, ...rest }) {
  const [focus, setFocus] = React.useState(false);
  return (
    <textarea
      rows={rows}
      onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
      style={{
        width: '100%', boxSizing: 'border-box', resize: 'vertical',
        background: tone === 'sunken' ? 'var(--surface-input-alt)' : 'var(--surface-input)',
        border: '1px solid ' + (focus ? 'var(--border-focus)' : tone === 'sunken' ? 'var(--border-default)' : 'var(--border-strong)'),
        borderRadius: 'var(--radius-md)', padding: '8px 12px', fontSize: 'var(--text-sm)',
        fontFamily: mono ? 'var(--font-mono)' : 'var(--font-sans)',
        color: 'var(--text-primary)', outline: 'none', lineHeight: 'var(--leading-normal)',
        ...style,
      }}
      {...rest}
    />
  );
}
