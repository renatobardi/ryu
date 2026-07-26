import * as React from 'react';

/** Tabela do Ryu: cabeçalho 12px zinc-500, linhas separadas por zinc-800/50, sem zebra. */
export interface DataTableColumn {
  key: string;
  label: React.ReactNode;
  align?: 'left' | 'right' | 'center';
  muted?: boolean;
  small?: boolean;
  mono?: boolean;
  maxWidth?: number;
}
export interface DataTableProps {
  columns?: DataTableColumn[];
  rows?: Record<string, React.ReactNode>[];
  empty?: React.ReactNode;
  /** `true` embrulha em card (dashboard/agents). `false` = tabela nua (Usage, Runtimes). */
  bordered?: boolean;
}
export declare function DataTable(props: DataTableProps): JSX.Element;
