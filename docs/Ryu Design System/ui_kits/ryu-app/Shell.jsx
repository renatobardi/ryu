const NAV = [
  { group: null, items: [['inbox','inbox','Inbox'],['chat','message-circle','Chat'],['my_issues','user','My Issues']] },
  { group: 'Workspace', items: [['board','layout-grid','Issues'],['projects','folder','Projects'],['autopilots','zap','Autopilots'],['agents','bot','Agents'],['squads','users','Squads'],['usage','bar-chart-2','Usage']] },
  { group: 'Configure', items: [['runtimes','puzzle','Runtimes'],['skills','book-open','Skills'],['members','users','Members'],['settings','settings','Settings']] },
];

function Shell({ route, setRoute, unread, theme, setTheme, user, query, setQuery, children }) {
  const { Sidebar, SidebarSection, NavItem, TopBar, ThemeToggle, Icon } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  return (
    <div style={{ display:'flex', height:'100%', background:'var(--surface-app)' }}>
      <Sidebar user={user} onSearch={(e) => { setQuery(e.target.value); setRoute('search'); }} onProfileClick={() => setRoute('profile')}>
        {NAV.map((g, i) => (
          <React.Fragment key={i}>
            {g.group && <SidebarSection>{g.group}</SidebarSection>}
            {g.items.map(([key, icon, label]) => (
              <NavItem key={key} icon={<Icon name={icon} size={15} />} label={label} active={route === key}
                count={key === 'inbox' ? unread : 0}
                onClick={(e) => { e.preventDefault(); setRoute(key); }} />
            ))}
          </React.Fragment>
        ))}
      </Sidebar>
      <div style={{ flex:1, display:'flex', flexDirection:'column', minWidth:0 }}>
        <TopBar connection="connected" inboxCount={unread}><ThemeToggle theme={theme} onChange={setTheme} /></TopBar>
        <main style={{ flex:1, overflowY:'auto', minHeight:0 }}>{children}</main>
      </div>
    </div>
  );
}

function PageHeader({ title, sub, right, kicker }) {
  return (
    <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:16, padding:'16px 24px', borderBottom:'1px solid var(--border-default)' }}>
      <div style={{ display:'flex', alignItems:'center', gap:12 }}>
        <h1 style={{ margin:0, font:'var(--type-page-title)', color:'var(--text-primary)' }}>{title}</h1>
        {kicker && <span style={{ fontSize:'var(--text-xs)', color:'var(--text-subtle)', textTransform:'uppercase', letterSpacing:'var(--tracking-wide)' }}>{kicker}</span>}
        {sub && <p style={{ margin:0, fontSize:'var(--text-xs)', color:'var(--text-subtle)' }}>{sub}</p>}
      </div>
      <div style={{ display:'flex', alignItems:'center', gap:8 }}>{right}</div>
    </div>
  );
}

Object.assign(window, { Shell, PageHeader });
