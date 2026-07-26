import * as React from 'react';

/** Linha do inbox: bolinha de severidade, título, corpo truncado, timestamp e ações à direita. */
export interface InboxItemProps {
  severity?: 'action_required' | 'attention' | 'info';
  title?: React.ReactNode;
  body?: React.ReactNode;
  time?: string;
  /** não-lidas ficam com fundo zinc-900/60 e título em zinc-100 medium */
  read?: boolean;
  /** botões de ação ("Lida", "Arquivar") */
  children?: React.ReactNode;
  style?: React.CSSProperties;
}
export declare function InboxItem(props: InboxItemProps): JSX.Element;
