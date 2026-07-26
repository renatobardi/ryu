import * as React from 'react';

/**
 * Bolinha de status de issue — as sete cores canônicas do `app.css`.
 */
export interface StatusDotProps {
  status?: 'backlog' | 'todo' | 'in_progress' | 'in_review' | 'done' | 'blocked' | 'cancelled';
  size?: number;
  style?: React.CSSProperties;
}
export declare function StatusDot(props: StatusDotProps): JSX.Element;
