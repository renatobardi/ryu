import React from 'react';

export function DataTable({ columns = [], rows = [], empty = 'Sem dados.', bordered = true }) {
  const table = (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)', fontFamily: 'var(--font-sans)' }}>
      <thead>
        <tr style={{ borderBottom: '1px solid var(--border-default)' }}>
          {columns.map((c, i) => (
            <th key={i} style={{
              textAlign: c.align || 'left', fontSize: 'var(--text-xs)', fontWeight: 'var(--weight-medium)',
              color: 'var(--text-subtle)', padding: bordered ? '8px 16px' : '8px 16px 8px 0', whiteSpace: 'nowrap',
            }}>{c.label}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 && (
          <tr><td colSpan={columns.length} style={{ padding: '24px 16px', textAlign: 'center', color: 'var(--text-subtle)' }}>{empty}</td></tr>
        )}
        {rows.map((r, i) => (
          <tr key={i} style={{ borderBottom: '1px solid var(--border-hairline)' }}>
            {columns.map((c, j) => (
              <td key={j} style={{
                textAlign: c.align || 'left', padding: bordered ? '8px 16px' : '8px 16px 8px 0',
                color: c.muted ? 'var(--text-subtle)' : 'var(--text-secondary)',
                fontSize: c.small ? 'var(--text-xs)' : undefined,
                fontFamily: c.mono ? 'var(--font-mono)' : undefined,
                maxWidth: c.maxWidth, overflow: c.maxWidth ? 'hidden' : undefined,
                textOverflow: c.maxWidth ? 'ellipsis' : undefined, whiteSpace: c.maxWidth ? 'nowrap' : undefined,
              }}>{r[c.key]}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
  if (!bordered) return table;
  return (
    <div style={{ background: 'var(--surface-card)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>{table}</div>
  );
}
