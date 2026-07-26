import * as React from 'react';

/**
 * Sidebar de 224px do Ryu: marca + busca ⌘K + New Issue + navegação + rodapé de usuário clicável.
 */
export interface SidebarProps {
  /** \`nickname\` é o que aparece no rodapé; \`name\` só alimenta as iniciais quando falta apelido; \`avatar\` é opcional. */
  user?: { nickname?: string; name?: string; avatar?: string };
  onSearch?: React.ChangeEventHandler<HTMLInputElement>;
  /** \`NavItem\`s e \`SidebarSection\`s */
  children?: React.ReactNode;
  /** clique no rodapé de usuário — normalmente abre a subpágina de perfil */
  onProfileClick?: React.MouseEventHandler;
  style?: React.CSSProperties;
}
export declare function Sidebar(props: SidebarProps): JSX.Element;
export interface SidebarSectionProps { children?: React.ReactNode }
export declare function SidebarSection(props: SidebarSectionProps): JSX.Element;
