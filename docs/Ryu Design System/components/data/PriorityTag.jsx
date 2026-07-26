import React from 'react';

const P = {
  urgent: ['--prio-urgent-bg', '--prio-urgent-fg'], high: ['--prio-high-bg', '--prio-high-fg'],
  medium: ['--prio-medium-bg', '--prio-medium-fg'], low: ['--prio-low-bg', '--prio-low-fg'],
};

export function PriorityTag({ priority = 'medium', style }) {
  if (priority === 'none') return null;
  const pair = P[priority] || P.low;
  return (
    <span style={{
      font: 'var(--type-pill)', textTransform: 'uppercase', borderRadius: 'var(--radius-sm)',
      padding: '2px 6px', background: 'var(' + pair[0] + ')', color: 'var(' + pair[1] + ')', ...style,
    }}>{priority}</span>
  );
}
