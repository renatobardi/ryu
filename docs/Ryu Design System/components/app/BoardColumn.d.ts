import * as React from 'react';

/** Coluna de 288px do board, com contador no cabeçalho e área de drop de 80px mínimos. */
export interface BoardColumnProps {
  title?: React.ReactNode;
  count?: number;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}
export declare function BoardColumn(props: BoardColumnProps): JSX.Element;
