/* ── Projects ──────────────────────────────────────────────── */
function ProjectsScreen({ open }) {
  const { Button, Input, Select, Textarea, Card, EmptyState, Icon, StatusPill, DataTable } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  const [projects, setProjects] = React.useState(D.projects);
  const [name, setName] = React.useState('');
  const [desc, setDesc] = React.useState('');
  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%' }}>
      <PageHeader title="Projects" sub={projects.length + ' projeto(s)'} />
      <div style={{ padding:24 }}>
        <form style={{ display:'flex', gap:8, marginBottom:24 }} onSubmit={(e) => { e.preventDefault(); if (!name.trim()) return;
          setProjects((p) => [...p, { id:'p' + (p.length + 1), name, description:desc, status:'active' }]); setName(''); setDesc(''); }}>
          <Input full={false} style={{ width:220 }} placeholder="Nome do projeto" value={name} onChange={(e) => setName(e.target.value)} />
          <Input full={false} style={{ flex:1 }} placeholder="Descrição (opcional)" value={desc} onChange={(e) => setDesc(e.target.value)} />
          <Button type="submit">Criar projeto</Button>
        </form>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:16 }}>
          {projects.map((p) => (
            <Card key={p.id} tone="raised" hoverable pad={16} style={{ cursor:'pointer' }} onClick={() => open(p)}>
              <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
                <span style={{ fontSize:'var(--text-sm)', fontWeight:'var(--weight-medium)', color:'var(--text-primary)' }}>{p.name}</span>
                <StatusPill kind="state" status={p.status === 'active' ? 'on' : 'off'}>{p.status}</StatusPill>
              </div>
              {p.description && <p style={{ margin:'4px 0 0', fontSize:'var(--text-xs)', color:'var(--text-subtle)' }}>{p.description}</p>}
              <p style={{ margin:'8px 0 0', fontSize:'var(--text-xs)', color:'var(--text-subtle)' }}>{D.issueCounts[p.id] || 0} issue(s)</p>
            </Card>
          ))}
          {projects.length === 0 && <EmptyState>Nenhum projeto ainda. Crie o primeiro acima.</EmptyState>}
        </div>
      </div>
    </div>
  );
}

function ProjectDetailScreen({ project, issues, back }) {
  const { Button, Input, Select, Textarea, Card, EmptyState, Icon, StatusPill, DataTable } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  const items = issues.filter((i) => (D.issueCounts[project.id] ? true : false)).slice(0, D.issueCounts[project.id] || 0);
  return (
    <div style={{ maxWidth:'var(--content-max)', margin:'0 auto', padding:24 }}>
      <a href="#" onClick={(e) => { e.preventDefault(); back(); }} style={{ fontSize:'var(--text-xs)', color:'var(--text-subtle)' }}>← Projects</a>
      <div style={{ display:'flex', alignItems:'center', gap:8, marginTop:4 }}>
        <h1 style={{ margin:0, fontSize:'var(--text-lg)', fontWeight:'var(--weight-semibold)', color:'var(--text-primary)' }}>{project.name}</h1>
        <StatusPill kind="state" status={project.status === 'active' ? 'on' : 'off'}>{project.status}</StatusPill>
      </div>
      {project.description && <p style={{ margin:'4px 0 0', fontSize:'var(--text-sm)', color:'var(--text-subtle)' }}>{project.description}</p>}
      <h2 style={{ margin:'24px 0 8px', fontSize:'var(--text-sm)', fontWeight:'var(--weight-medium)', color:'var(--text-secondary)' }}>Issues ({items.length})</h2>
      <div style={{ border:'1px solid var(--border-default)', borderRadius:'var(--radius-lg)', overflow:'hidden' }}>
        {items.map((i) => (
          <div key={i.key} style={{ display:'flex', alignItems:'center', gap:12, padding:'10px 16px', borderBottom:'1px solid var(--border-hairline)' }}>
            <span style={{ font:'var(--type-key)', color:'var(--text-subtle)', width:70, flexShrink:0 }}>{i.key}</span>
            <span style={{ flex:1, fontSize:'var(--text-sm)', color:'var(--text-body)' }}>{i.title}</span>
            <StatusPill kind="task" status="queued">{D.statusTitles[i.status]}</StatusPill>
          </div>
        ))}
        {items.length === 0 && <div style={{ padding:24, textAlign:'center', fontSize:'var(--text-sm)', color:'var(--text-subtle)' }}>Nenhuma issue neste projeto.</div>}
      </div>
    </div>
  );
}

/* ── Runtimes ──────────────────────────────────────────────── */
function RuntimesScreen() {
  const { Button, Input, Select, Textarea, Card, EmptyState, Icon, StatusPill, DataTable } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%' }}>
      <PageHeader title="Runtimes" sub="CLIs detectados no servidor onde o Ryu roda." />
      <div style={{ padding:24 }}>
        <DataTable columns={[{key:'name',label:'Runtime',mono:true},{key:'status',label:'Status'},{key:'path',label:'Caminho',muted:true,mono:true}]}
          rows={D.runtimes.map((r) => ({ name:r.name, status:<StatusPill kind="state" status={r.available ? 'on' : 'off'}>{r.available ? 'disponível' : 'indisponível'}</StatusPill>, path:r.path || '—' }))} />
        <Card tone="raised" pad={16} style={{ marginTop:24, maxWidth:640, fontSize:'var(--text-sm)', color:'var(--text-muted)' }}>
          <p style={{ margin:'0 0 4px', color:'var(--text-secondary)', fontWeight:'var(--weight-medium)' }}>Como configurar</p>
          <p style={{ margin:0 }}>Instale o CLI desejado no host e garanta que ele esteja no <code style={{ color:'var(--text-accent)' }}>PATH</code> do processo do Ryu. Cada agent usa o campo <code style={{ color:'var(--text-accent)' }}>runtime</code> (claude|codex|gemini).</p>
        </Card>
      </div>
    </div>
  );
}

/* ── Settings ──────────────────────────────────────────────── */
function SettingsScreen({ onLogout }) {
  const { Button, Input, Select, Textarea, Card, EmptyState, Icon, StatusPill, DataTable } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  const [name, setName] = React.useState(D.workspace.name);
  const [prefix, setPrefix] = React.useState(D.workspace.prefix);
  const [tokens, setTokens] = React.useState(D.patTokens);
  const [tokName, setTokName] = React.useState('');
  const [newTok, setNewTok] = React.useState('');
  return (
    <div style={{ maxWidth:'var(--form-max)', margin:'0 auto', padding:24, display:'flex', flexDirection:'column', gap:24 }}>
      <h1 style={{ margin:0, fontSize:'var(--text-lg)', fontWeight:'var(--weight-semibold)', color:'var(--text-primary)' }}>Settings</h1>
      <section>
        <h2 style={{ margin:'0 0 8px', fontSize:'var(--text-sm)', fontWeight:'var(--weight-medium)', color:'var(--text-secondary)' }}>Workspace</h2>
        <Card tone="raised" pad={16} style={{ display:'flex', flexDirection:'column', gap:12 }}>
          <div><label style={{ display:'block', marginBottom:4, fontSize:'var(--text-xs)', color:'var(--text-subtle)' }}>Nome do workspace</label><Input value={name} onChange={(e) => setName(e.target.value)} /></div>
          <div><label style={{ display:'block', marginBottom:4, fontSize:'var(--text-xs)', color:'var(--text-subtle)' }}>Issue prefix</label><Input value={prefix} onChange={(e) => setPrefix(e.target.value.toUpperCase())} style={{ width:120, fontFamily:'var(--font-mono)', textTransform:'uppercase' }} /></div>
          <div><Button size="sm">Salvar</Button></div>
        </Card>
      </section>
      <section>
        <h2 style={{ margin:'0 0 8px', fontSize:'var(--text-sm)', fontWeight:'var(--weight-medium)', color:'var(--text-secondary)' }}>Personal Access Tokens (ryu_)</h2>
        <Card tone="raised" pad={16} style={{ display:'flex', flexDirection:'column', gap:12 }}>
          <div style={{ display:'flex', gap:8 }}>
            <Input placeholder="Nome do token (ex.: cli local)" value={tokName} onChange={(e) => setTokName(e.target.value)} />
            <Button onClick={() => { setTokens((t) => [...t, { id:'t' + (t.length + 1), name:tokName || '(sem nome)', created:'26/07/2026' }]); setNewTok('ryu_' + Math.random().toString(36).slice(2, 18)); setTokName(''); }}>Criar token</Button>
          </div>
          {newTok && <div style={{ fontSize:'var(--text-xs)', fontFamily:'var(--font-mono)', color:'var(--emerald-500)', border:'1px solid var(--emerald-500)', borderRadius:'var(--radius-md)', padding:12, wordBreak:'break-all' }}>Copie agora (exibido uma única vez): {newTok}</div>}
          <div style={{ display:'flex', flexDirection:'column' }}>
            {tokens.map((t) => (
              <div key={t.id} style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'8px 0', borderTop:'1px solid var(--border-hairline)' }}>
                <span style={{ fontSize:'var(--text-sm)', color:'var(--text-secondary)' }}>{t.name} <span style={{ fontSize:'var(--text-xs)', color:'var(--text-subtle)' }}>· {t.created}</span></span>
                <Button variant="danger" onClick={() => setTokens((ts) => ts.filter((x) => x.id !== t.id))}>Revogar</Button>
              </div>
            ))}
            {tokens.length === 0 && <p style={{ margin:'8px 0 0', fontSize:'var(--text-xs)', color:'var(--text-subtle)' }}>Nenhum token ativo.</p>}
          </div>
        </Card>
      </section>
      <section>
        <h2 style={{ margin:'0 0 8px', fontSize:'var(--text-sm)', fontWeight:'var(--weight-medium)', color:'var(--text-secondary)' }}>Sessão</h2>
        <Card tone="raised" pad={16}><Button variant="secondary" onClick={onLogout}>Sair (logout)</Button></Card>
      </section>
    </div>
  );
}

/* ── My Issues ─────────────────────────────────────────────── */
function MyIssuesScreen({ issues, openIssue }) {
  const { Button, Input, Select, Textarea, Card, EmptyState, Icon, StatusPill, DataTable } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  const mine = issues.filter((i) => i.assignee);
  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%' }}>
      <PageHeader title="My Issues" sub={mine.length + ' issue(s) atribuída(s) a você'} />
      <div style={{ padding:24, display:'flex', flexDirection:'column', gap:20 }}>
        {D.statusOrder.map((s) => {
          const items = mine.filter((i) => i.status === s);
          if (!items.length) return null;
          return (
            <div key={s}>
              <h2 style={{ margin:'0 0 8px', fontSize:'var(--text-2xs)', textTransform:'uppercase', letterSpacing:'var(--tracking-wider)', color:'var(--text-subtle)' }}>{D.statusTitles[s]} ({items.length})</h2>
              <div style={{ border:'1px solid var(--border-default)', borderRadius:'var(--radius-lg)', overflow:'hidden' }}>
                {items.map((i) => (
                  <div key={i.key} onClick={() => openIssue(i)} style={{ display:'flex', alignItems:'center', gap:12, padding:'10px 16px', borderBottom:'1px solid var(--border-hairline)', cursor:'pointer' }}>
                    <span style={{ font:'var(--type-key)', color:'var(--text-subtle)', width:70, flexShrink:0 }}>{i.key}</span>
                    <span style={{ flex:1, fontSize:'var(--text-sm)', color:'var(--text-body)' }}>{i.title}</span>
                    <span style={{ fontSize:'var(--text-2xs)', textTransform:'uppercase', background:'var(--surface-active)', color:'var(--text-muted)', borderRadius:'var(--radius-sm)', padding:'2px 6px' }}>{i.priority}</span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
        {mine.length === 0 && <EmptyState>Nenhuma issue atribuída a você neste workspace.</EmptyState>}
      </div>
    </div>
  );
}

Object.assign(window, { ProjectsScreen, ProjectDetailScreen, RuntimesScreen, SettingsScreen, MyIssuesScreen });
