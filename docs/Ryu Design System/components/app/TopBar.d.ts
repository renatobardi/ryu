import * as React from 'react';

/** Header de 44px: ponto de conexão WebSocket + atalho para o Inbox. Alinhado à direita. */
export interface TopBarProps {
  /** verde = conectado, vermelho = queda (o hub reconecta com backoff), cinza = conectando */
  connection?: 'connected' | 'disconnected' | 'connecting';
  inboxCount?: number;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}
export declare function TopBar(props: TopBarProps): JSX.Element;
