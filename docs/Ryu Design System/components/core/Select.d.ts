import * as React from 'react';

/** Select nativo estilizado — texto zinc-300, um pouco mais apagado que o Input. */
export interface SelectProps extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'size'> {
  size?: 'sm' | 'md';
  tone?: 'raised' | 'sunken';
  full?: boolean;
  children?: React.ReactNode;
}
export declare function Select(props: SelectProps): JSX.Element;
