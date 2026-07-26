import * as React from 'react';

/** Campo de texto do Ryu: fundo zinc-900 (ou zinc-950 em `sunken`), borda que vira violet-500 no focus. */
export interface InputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'size'> {
  size?: 'sm' | 'md' | 'lg';
  /** `raised` = zinc-900/zinc-700 (padrão). `sunken` = zinc-950/zinc-800, usado dentro de cards de formulário. */
  tone?: 'raised' | 'sunken';
  full?: boolean;
}
export declare function Input(props: InputProps): JSX.Element;
