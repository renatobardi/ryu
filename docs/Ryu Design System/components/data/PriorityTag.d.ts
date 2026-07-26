import * as React from 'react';

/** Tag de prioridade do card do board — cantos de 4px (não é pill), texto UPPERCASE de 10px. */
export interface PriorityTagProps {
  priority?: 'urgent' | 'high' | 'medium' | 'low' | 'none';
  style?: React.CSSProperties;
}
export declare function PriorityTag(props: PriorityTagProps): JSX.Element;
