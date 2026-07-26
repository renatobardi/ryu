import * as React from 'react';

/**
 * Ícone monocromático (stroke, `currentColor`) via Lucide — substituição intencional, o Ryu
 * não define biblioteca de ícones. Requer `<script src="https://unpkg.com/lucide@latest"></script>`
 * carregado na página antes da montagem.
 */
export interface IconProps {
  /** nome do ícone no Lucide, ex.: "inbox", "message-circle", "bot", "user", "settings" */
  name: string;
  size?: number;
  strokeWidth?: number;
  style?: React.CSSProperties;
}
export declare function Icon(props: IconProps): JSX.Element;
