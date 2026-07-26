import React from 'react';
import { Card } from './Card.jsx';

export function EmptyState({ children, dashed = true, pad = 24 }) {
  return (
    <Card tone="panel" dashed={dashed} pad={pad}
      style={{ textAlign: 'center', fontSize: 'var(--text-sm)', color: 'var(--text-subtle)' }}>
      {children}
    </Card>
  );
}
