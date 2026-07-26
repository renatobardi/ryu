import React from 'react';
import { IssueKey } from '../data/IssueKey.jsx';
import { PriorityTag } from '../data/PriorityTag.jsx';
import { Icon } from '../core/Icon.jsx';

export function IssueCard({ issueKey, title, priority = 'none', assignee, assigneeType = 'agent', onClick, style }) {
  const [hover, setHover] = React.useState(false);
  return (
    <div draggable onClick={onClick}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        background: 'var(--surface-raised)', border: '1px solid ' + (hover ? 'var(--border-hover)' : 'var(--border-default)'),
        borderRadius: 'var(--radius-md)', padding: 12, cursor: 'grab',
        transition: 'border-color var(--duration-fast) var(--ease-out)', ...style,
      }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <IssueKey>{issueKey}</IssueKey>
        <PriorityTag priority={priority} />
      </div>
      <div style={{ fontSize: 'var(--text-sm)', lineHeight: 'var(--leading-snug)', fontFamily: 'var(--font-sans)', color: hover ? 'var(--text-accent)' : 'var(--text-primary)' }}>{title}</div>
      {assignee && (
        <div style={{ marginTop: 8 }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 'var(--text-2xs)', padding: '2px 6px', borderRadius: 'var(--radius-sm)', background: 'var(--surface-hover)', color: 'var(--text-muted)' }}>
            <Icon name={assigneeType === 'agent' ? 'bot' : 'user'} size={11} />{assignee}
          </span>
        </div>
      )}
    </div>
  );
}
