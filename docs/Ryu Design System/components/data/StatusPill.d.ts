import * as React from 'react';

/** Pill de 10px arredondada — status de agente, de task, severidade de inbox ou estado ativo/pausado. */
export interface StatusPillProps {
  kind?: 'agent' | 'task' | 'severity' | 'state' | 'neutral';
  status?: string;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}
export declare function StatusPill(props: StatusPillProps): JSX.Element;
