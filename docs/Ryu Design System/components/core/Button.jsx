import React from 'react';

const VARIANTS = {
  primary: { background: 'var(--accent)', color: 'var(--text-on-accent)', border: '1px solid transparent' },
  secondary: { background: 'var(--zinc-800)', color: 'var(--text-body)', border: '1px solid transparent' },
  outline: { background: 'var(--surface-input)', color: 'var(--text-secondary)', border: '1px solid var(--border-strong)' },
  ghost: { background: 'transparent', color: 'var(--text-muted)', border: '1px solid transparent' },
  link: { background: 'transparent', color: 'var(--text-accent)', border: 'none', padding: 0 },
  danger: { background: 'transparent', color: 'var(--text-subtle)', border: 'none', padding: 0 },
};
const HOVER = {
  primary: 'var(--accent-hover)', secondary: 'var(--zinc-700)', outline: 'var(--zinc-800)',
  ghost: 'var(--surface-hover)', link: null, danger: null,
};
const HOVER_FG = { ghost: 'var(--text-body)', link: 'var(--violet-300)', danger: 'var(--red-400)', outline: 'var(--text-body)' };
const SIZES = {
  sm: { fontSize: 'var(--text-xs)', padding: '4px 12px' },
  md: { fontSize: 'var(--text-sm)', padding: '6px 16px' },
  lg: { fontSize: 'var(--text-sm)', padding: '8px 16px' },
};

export function Button({ variant = 'primary', size = 'md', disabled, full, children, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  const v = VARIANTS[variant] || VARIANTS.primary;
  const bare = variant === 'link' || variant === 'danger';
  return (
    <button
      type="button"
      disabled={disabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        font: 'var(--type-body)', fontWeight: 'var(--weight-medium)',
        borderRadius: 'var(--radius-md)', cursor: disabled ? 'not-allowed' : 'pointer',
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 'var(--space-1-5)',
        width: full ? '100%' : undefined, whiteSpace: 'nowrap',
        transition: 'background var(--duration-fast) var(--ease-out), color var(--duration-fast) var(--ease-out)',
        opacity: disabled ? 0.45 : 1,
        ...v, ...(bare ? { fontSize: 'var(--text-xs)' } : SIZES[size]),
        ...(hover && !disabled && HOVER[variant] ? { background: HOVER[variant] } : null),
        ...(hover && !disabled && HOVER_FG[variant] ? { color: HOVER_FG[variant] } : null),
        ...style,
      }}
      {...rest}
    >{children}</button>
  );
}
