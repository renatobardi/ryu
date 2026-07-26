import * as React from 'react';

/** Container padrão: borda de 1px + troca de superfície. O Ryu nunca usa box-shadow. */
export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** `panel` #111116 (dashboard/login) · `raised` zinc-900 (formulários) · `muted` zinc-900/60 (colunas, comentários) */
  tone?: 'panel' | 'raised' | 'muted' | 'bare';
  dashed?: boolean;
  hoverable?: boolean;
  pad?: number;
  children?: React.ReactNode;
}
export declare function Card(props: CardProps): JSX.Element;
