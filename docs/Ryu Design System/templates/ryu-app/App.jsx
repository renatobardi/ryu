function LoginScreen({ onDone }) {
  const { Card, Input, Button } = window.RyuDesignSystem_7ed69e;
  const [user, setUser] = React.useState('');
  const [password, setPassword] = React.useState('');
  return (
    <div style={{ minHeight:'100%', display:'flex', alignItems:'center', justifyContent:'center', padding:16, background:'var(--surface-app)' }}>
      <div style={{ width:'100%', maxWidth:384 }}>
        <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:32, justifyContent:'center' }}>
          <span style={{ fontSize:44, lineHeight:1, color:'var(--text-primary)' }}>龍</span>
          <div>
            <div style={{ fontSize:28, fontWeight:800, letterSpacing:'-0.03em', color:'var(--text-primary)', lineHeight:1 }}>Ryu</div>
            <div style={{ fontSize:'var(--text-xs)', color:'var(--text-subtle)', marginTop:4 }}>Agentic issue tracking</div>
          </div>
        </div>
        <Card tone="panel" pad={24} style={{ borderRadius:'var(--radius-xl)' }}>
          <form style={{ display:'flex', flexDirection:'column', gap:12 }} onSubmit={(e) => { e.preventDefault(); onDone(); }}>
            <label style={{ fontSize:'var(--text-sm)', color:'var(--text-muted)' }}>Usuário</label>
            <Input required placeholder="voce@empresa.com" value={user} onChange={(e) => setUser(e.target.value)} style={{ padding:'8px 12px' }} />
            <label style={{ fontSize:'var(--text-sm)', color:'var(--text-muted)' }}>Senha</label>
            <Input type="password" required placeholder="••••••••" value={password} onChange={(e) => setPassword(e.target.value)} style={{ padding:'8px 12px' }} />
            <Button type="submit" full size="lg">Entrar</Button>
          </form>
        </Card>
      </div>
    </div>
  );
}

function App() {
  const D = window.RYU_DATA;
  const [authed, setAuthed] = React.useState(false);
  const [route, setRoute] = React.useState('dashboard');
  const [issues, setIssues] = React.useState(D.issues);
  const [inbox, setInbox] = React.useState(D.inbox);
  const [openIssue, setOpenIssue] = React.useState(null);
  const [openProject, setOpenProject] = React.useState(null);
  const [query, setQuery] = React.useState('');
  const [theme, setTheme] = React.useState('light');
  const [user, setUser] = React.useState({ nickname: 'renatob', email: D.user.email });
  const unread = inbox.filter((i) => !i.read).length;
  let seq = React.useRef(143);

  React.useEffect(() => {
    if (theme === 'dark') document.documentElement.setAttribute('data-theme', 'dark');
    else document.documentElement.removeAttribute('data-theme');
  }, [theme]);

  if (!authed) return <LoginScreen onDone={() => setAuthed(true)} />;

  const addIssue = (title, status, assignee) => {
    setIssues((prev) => [{ key: D.workspace.prefix + '-' + (seq.current++), title, status, priority:'none', assignee: assignee || undefined }, ...prev]);
  };
  const patch = (key, field, value) => setIssues((prev) => prev.map((i) => i.key === key ? { ...i, [field]: value } : i));

  let screen;
  if (openIssue) {
    const live = issues.find((i) => i.key === openIssue.key) || openIssue;
    screen = <IssueScreen issue={live} back={() => setOpenIssue(null)} patch={patch} />;
  } else if (openProject) {
    screen = <ProjectDetailScreen project={openProject} issues={issues} back={() => setOpenProject(null)} />;
  } else if (route === 'dashboard') screen = <DashboardScreen issues={issues} go={setRoute} />;
  else if (route === 'board') screen = <BoardScreen issues={issues} addIssue={addIssue} openIssue={setOpenIssue} />;
  else if (route === 'chat') screen = <ChatScreen />;
  else if (route === 'inbox') screen = <InboxScreen items={inbox} markAll={() => setInbox((p) => p.map((i) => ({ ...i, read:true })))}
      markRead={(n) => setInbox((p) => p.map((i, idx) => idx === n ? { ...i, read:true } : i))} />;
  else if (route === 'agents') screen = <AgentsScreen />;
  else if (route === 'usage') screen = <UsageScreen />;
  else if (route === 'profile') screen = <ProfileScreen user={user} setUser={setUser} onLogout={() => setAuthed(false)} />;
  else if (route === 'projects') screen = <ProjectsScreen open={setOpenProject} />;
  else if (route === 'runtimes') screen = <RuntimesScreen />;
  else if (route === 'settings') screen = <SettingsScreen onLogout={() => setAuthed(false)} />;
  else if (route === 'my_issues') screen = <MyIssuesScreen issues={issues} openIssue={setOpenIssue} />;
  else if (route === 'autopilots') screen = <AutopilotsScreen />;
  else if (route === 'skills') screen = <SkillsScreen />;
  else if (route === 'squads') screen = <SquadsScreen />;
  else if (route === 'members') screen = <MembersScreen />;
  else if (route === 'search') screen = <SearchScreen query={query} setQuery={setQuery} issues={issues} />;
  else screen = <StubScreen title={route.replace('_', ' ')} note="Tela existente no Ryu, não recriada neste UI kit." />;

  return (
    <Shell route={openIssue || openProject ? 'board' : route} unread={unread} theme={theme} setTheme={setTheme} user={user} query={query} setQuery={setQuery}
      setRoute={(r) => { setOpenIssue(null); setOpenProject(null); setRoute(r); }}>{screen}</Shell>
  );
}

function mountApp() {
  if (window.__ryuMounted) return;
  if (!window.RyuDesignSystem_7ed69e || !window.Shell) { setTimeout(mountApp, 30); return; }
  window.__ryuMounted = true;
  ReactDOM.createRoot(document.getElementById('root')).render(<App />);
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mountApp); else mountApp();
