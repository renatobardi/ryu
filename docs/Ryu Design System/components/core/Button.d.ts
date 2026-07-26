import * as React from 'react';

/**
 * Botão do Ryu. Primary é violet-600; secondary é zinc-800; link/danger são
 * texto de 12px usados nas ações inline de listas ("rodar agora", "excluir").
 */
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'link' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  /** ocupa 100% da largura (usado no login e no "New Issue" da sidebar) */
  full?: boolean;
  children?: React.ReactNode;
}
export declare function Button(props: ButtonProps): JSX.Element;
