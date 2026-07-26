import React from 'react';

const MAP = {
  agent: {
    idle: ['--agent-idle-bg', '--agent-idle-fg'], working: ['--agent-working-bg', '--agent-working-fg'],
    blocked: ['--agent-blocked-bg', '--agent-blocked-fg'], error: ['--agent-error-bg', '--agent-error-fg'],
    offline: ['--agent-offline-bg', '--agent-offline-fg'],
  },
  task: {
    queued: ['--task-queued-bg', '--task-queued-fg'], dispatched: ['--task-dispatched-bg', '--task-dispatched-fg'],
    running: ['--task-running-bg', '--task-running-fg'], completed: ['--task-completed-bg', '--task-completed-fg'],
    failed: ['--task-failed-bg', '--task-failed-fg'], cancelled: ['--task-cancelled-bg', '--task-cancelled-fg'],
  },
  severity: {
    action_required: ['--sev-action-required-bg', '--sev-action-required-fg'],
    attention: ['--sev-attention-bg', '--sev-attention-fg'], info: ['--sev-info-bg', '--sev-info-fg'],
  },
  state: { on: ['--state-on-bg', '--state-on-fg'], off: ['--state-off-bg', '--state-off-fg'] },
  neutral: { default: [null, null] },
};

export function StatusPill({ kind = 'task', status, children, style }) {
  const pair = (MAP[kind] && MAP[kind][status]) || [null, null];
  return (
    <span style={{
      display: 'inline-block', font: 'var(--type-pill)',
      borderRadius: 'var(--radius-full)', padding: 'var(--pill-pad-y) var(--pill-pad-x)',
      background: pair[0] ? 'var(' + pair[0] + ')' : 'var(--zinc-800)',
      color: pair[1] ? 'var(' + pair[1] + ')' : 'var(--text-muted)',
      whiteSpace: 'nowrap', ...style,
    }}>{children || status}</span>
  );
}
