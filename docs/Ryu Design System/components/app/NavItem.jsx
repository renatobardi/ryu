import React from 'react';
import { CountBadge } from '../data/CountBadge.jsx';

export function NavItem({ icon, label, active, count, href = '#', style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  return (
    <a href={href} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: '6px 12px',
        borderRadius: 'var(--radius-md)', textDecoration: 'none', fontSize: 'var(--text-sm)',
        fontFamily: 'var(--font-sans)',
        background: active ? 'var(--surface-active)' : hover ? 'var(--surface-hover)' : 'transparent',
        color: active ? 'var(--text-primary)' : hover ? 'var(--text-body)' : 'var(--text-muted)',
        transition: 'background var(--duration-fast) var(--ease-out), color var(--duration-fast) var(--ease-out)',
        ...style,
      }} {...rest}>
      <span style={{ width: 16, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: .85 }}>{icon}</span>
      <span style={{ flex: 1 }}>{label}</span>
      {count ? <CountBadge count={count} /> : null}
    </a>
  );
}
