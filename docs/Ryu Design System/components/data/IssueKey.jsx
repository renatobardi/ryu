import React from 'react';

export function IssueKey({ children, style }) {
  return <span style={{ font: 'var(--type-key)', color: 'var(--text-subtle)', ...style }}>{children}</span>;
}
