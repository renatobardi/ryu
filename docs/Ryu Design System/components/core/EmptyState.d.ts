import * as React from 'react';

/** Estado vazio do Ryu: card tracejado, texto de 14px zinc-500, frase curta em pt-BR. */
export interface EmptyStateProps {
  children?: React.ReactNode;
  dashed?: boolean;
  pad?: number;
}
export declare function EmptyState(props: EmptyStateProps): JSX.Element;
