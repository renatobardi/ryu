Casca de navegação do workspace. A marca é um quadrado índigo de 24px com a letra **R** — o Ryu não tem arquivo de logo.

```jsx
<Sidebar user={{nickname:'renatob'}} onProfileClick={() => go('profile')}>
  <NavItem icon={<Icon name="inbox" size={15}/>} label="Inbox" count={2} />
  <SidebarSection>Workspace</SidebarSection>
  <NavItem icon={<Icon name="layout-grid" size={15}/>} label="Issues" active />
</Sidebar>
```

O rodapé é um botão único: avatar (imagem ou iniciais em círculo) + apelido — sem nome completo, sem e-mail, sem botão "Sair" visível. Clique abre a subpágina de perfil, onde ficam avatar, apelido, e-mail e a opção de sair.

Grupos: (sem título) Inbox/Chat/My Issues · **Workspace** Issues/Projects/Autopilots/Agents/Squads/Usage · **Configure** Runtimes/Skills/Settings.
