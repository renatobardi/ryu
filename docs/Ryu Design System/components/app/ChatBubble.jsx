import React from 'react';

export function ChatBubble({ role = 'agent', children, time, typing, style }) {
  const user = role === 'user', system = role === 'system';
  const bg = user ? 'var(--accent)' : system ? 'var(--chat-bubble-system-bg)' : 'var(--chat-bubble-agent-bg)';
  const fg = user ? '#fff' : system ? 'var(--chat-bubble-system-fg)' : 'var(--chat-bubble-agent-fg)';
  return (
    <div style={{ display: 'flex', justifyContent: user ? 'flex-end' : 'flex-start', ...style }}>
      <div style={{
        maxWidth: '75%', borderRadius: 'var(--radius-xl)', padding: '8px 12px',
        fontSize: 'var(--text-sm)', fontFamily: 'var(--font-sans)', whiteSpace: 'pre-wrap',
        background: bg, color: typing ? 'var(--text-subtle)' : fg,
        border: system ? '1px solid var(--border-default)' : undefined,
        animation: typing ? 'var(--animate-pulse)' : undefined,
      }}>
        {!user && !typing && (
          <div style={{ fontSize: 'var(--text-2xs)', textTransform: 'uppercase', letterSpacing: 'var(--tracking-wide)', marginBottom: 4, color: system ? 'var(--chat-bubble-system-fg)' : 'var(--text-subtle)' }}>
            {system ? 'sistema' : 'agente'}
          </div>
        )}
        {children}
        {time && !typing && <div style={{ fontSize: 'var(--text-2xs)', marginTop: 4, opacity: .6 }}>{time}</div>}
      </div>
    </div>
  );
}
