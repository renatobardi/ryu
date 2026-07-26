import React from 'react';

const COLORS = {
  backlog: 'var(--status-backlog)', todo: 'var(--status-todo)', in_progress: 'var(--status-in-progress)',
  in_review: 'var(--status-in-review)', done: 'var(--status-done)', blocked: 'var(--status-blocked)',
  cancelled: 'var(--status-cancelled)',
};

export function StatusDot({ status = 'backlog', size = 8, style }) {
  return <span aria-label={status} style={{ display: 'inline-block', width: size, height: size, borderRadius: 'var(--radius-full)', background: COLORS[status] || COLORS.backlog, flexShrink: 0, ...style }} />;
}
