import * as React from 'react';

/** Linha da sidebar: emoji de 16px + rótulo em inglês + contador opcional. */
export interface NavItemProps extends React.AnchorHTMLAttributes<HTMLAnchorElement> {
  /** o glifo — no Ryu é um emoji (📥 💬 👤 ▦ 📁 ⚡ 🤖 👥 📊 🧩 📚 ⚙️) */
  icon?: React.ReactNode;
  label?: React.ReactNode;
  active?: boolean;
  count?: number;
}
export declare function NavItem(props: NavItemProps): JSX.Element;
