import React from 'react';
import { Icon } from '../core/Icon.jsx';

export function ThemeToggle({ theme = 'light', onChange, style }) {
  const isDark = theme === 'dark';
  return (
    <button type="button" onClick={() => onChange && onChange(isDark ? 'light' : 'dark')}
      aria-label="Alternar tema"
      style={{
        width: 36, height: 36, borderRadius: 'var(--radius-md)', border: '1px solid var(--border-default)',
        background: 'var(--surface-input)', color: 'var(--text-muted)', cursor: 'pointer',
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        transition: 'background var(--duration-fast) var(--ease-out)', ...style,
      }}
    ><Icon name={isDark ? 'sun' : 'moon'} size={16} /></button>
  );
}
