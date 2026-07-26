import * as React from 'react';

/** Textarea do Ryu — comentários de issue, regra de autopilot, conteúdo de skill (`mono`). */
export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  tone?: 'raised' | 'sunken';
  /** usa a fonte mono — o campo de conteúdo markdown das Skills */
  mono?: boolean;
}
export declare function Textarea(props: TextareaProps): JSX.Element;
