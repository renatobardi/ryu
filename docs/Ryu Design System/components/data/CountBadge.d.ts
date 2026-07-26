import * as React from 'react';

/** Contador do inbox — pill violet sólida de 10px. Some quando é zero. */
export interface CountBadgeProps {
  count?: number;
  tone?: 'accent' | 'neutral';
  hideZero?: boolean;
  style?: React.CSSProperties;
}
export declare function CountBadge(props: CountBadgeProps): JSX.Element;
