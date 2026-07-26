import * as React from 'react';

/** Agente como membro do time: nome, @handle · runtime, status e descrição. */
export interface AgentCardProps {
  name?: string;
  handle?: string;
  /** `claude` | `codex` | `gemini` — o campo runtime do modelo Agent */
  runtime?: string;
  status?: 'idle' | 'working' | 'blocked' | 'error' | 'offline';
  description?: string;
  /** variante do dashboard: avatar 🤖 de 36px e sem descrição */
  compact?: boolean;
  style?: React.CSSProperties;
}
export declare function AgentCard(props: AgentCardProps): JSX.Element;
