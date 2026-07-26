import * as React from 'react';

/** Alterna `data-theme` no `<html>` entre claro (padrão) e escuro. Ícone muda: 🌙 no claro, ☀️ no escuro. */
export interface ThemeToggleProps {
  theme?: 'light' | 'dark';
  onChange?: (next: 'light' | 'dark') => void;
  style?: React.CSSProperties;
}
export declare function ThemeToggle(props: ThemeToggleProps): JSX.Element;
