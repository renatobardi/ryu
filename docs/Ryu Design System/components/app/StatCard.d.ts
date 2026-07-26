import * as React from 'react';

/**
 * Métrica do dashboard e da tela de Usage: número de 24px semibold + rótulo pequeno.
 */
export interface StatCardProps {
  value?: React.ReactNode;
  label?: React.ReactNode;
  /** quando presente, o rótulo ganha a bolinha de status da issue (grid do dashboard) */
  status?: 'backlog' | 'todo' | 'in_progress' | 'in_review' | 'done' | 'blocked' | 'cancelled';
  /** valor em emerald — usado só para custo em USD */
  accent?: boolean;
  hoverable?: boolean;
  style?: React.CSSProperties;
}
export declare function StatCard(props: StatCardProps): JSX.Element;
