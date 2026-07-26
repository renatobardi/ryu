import * as React from 'react';

/**
 * Bolha do chat com agentes. Usuário à direita em violet; agente à esquerda em neutral-800;
 * sistema em âmbar com borda.
 */
export interface ChatBubbleProps {
  role?: 'user' | 'agent' | 'system';
  children?: React.ReactNode;
  time?: string;
  /** estado "agente digitando…" — texto apagado com pulse */
  typing?: boolean;
  style?: React.CSSProperties;
}
export declare function ChatBubble(props: ChatBubbleProps): JSX.Element;
