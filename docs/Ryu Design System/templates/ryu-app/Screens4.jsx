/* ── Autopilots ────────────────────────────────────────────── */
function AutopilotsScreen() {
  const { Button, Input, Select, Textarea, Card, EmptyState, StatusPill, Icon } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  const [items, setItems] = React.useState(D.autopilots);
  const [name, setName] = React.useState('');
  const [trigger, setTrigger] = React.useState('cron');
  const [cron, setCron] = React.useState('');
  const [agent, setAgent] = React.useState('');
  const [rule, setRule] = React.useState('');
  return (
    <div style={{ maxWidth:'var(--content-max)', margin:'0 auto', padding:24, display:'flex', flexDirection:'column', gap:24 }}>
      <h1 style={{ margin:0, fontSize:'var(--text-xl)', fontWeight:'var(--weight-semibold)', color:'var(--text-primary)' }}>Autopilots</h1>
      <Card tone="raised" pad={16} style={{ display:'flex', flexDirection:'column', gap:12 }}>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(2, 1fr)', gap:12 }}>
          <Input placeholder="Nome do autopilot" value={name} onChange={(e) => setName(e.target.value)} />
          <Select value={trigger} onChange={(e) => setTrigger(e.target.value)}><option value="cron">cron</option><option value="webhook">webhook</option><option value="manual">manual</option></Select>
          <Input placeholder="Cron (ex: 0 9 * * 1-5)" value={cron} onChange={(e) => setCron(e.target.value)} disabled={trigger !== 'cron'} />
          <Select value={agent} onChange={(e) => setAgent(e.target.value)}><option value="">— sem agente (issue vai p/ backlog) —</option>{D.agents.map((a) => <option key={a.id} value={a.handle}>{a.name}</option>)}</Select>
        </div>
        <Textarea rows={3} placeholder="Regra / instrução — vira a descrição da issue criada em cada run…" value={rule} onChange={(e) => setRule(e.target.value)} />
        <div><Button onClick={() => { if (!name.trim()) return; setItems((p) => [...p, { id:'ap' + (p.length + 1), name, trigger_type:trigger, cron_expr:cron, enabled:true, target_agent:agent, rule }]); setName(''); setRule(''); setCron(''); setAgent(''); }}>Criar autopilot</Button></div>
      </Card>
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        {items.map((ap) => (
          <Card key={ap.id} tone="raised" pad={16}>
            <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between', gap:12 }}>
              <div>
                <div style={{ display:'flex', alignItems:'center', gap:8, flexWrap:'wrap' }}>
                  <span style={{ fontSize:'var(--text-sm)', fontWeight:'var(--weight-medium)', color:'var(--text-primary)' }}>{ap.name}</span>
                  <StatusPill kind="state" status={ap.enabled ? 'on' : 'off'}>{ap.enabled ? 'ativo' : 'pausado'}</StatusPill>
                  <span style={{ fontSize:'var(--text-2xs)', background:'var(--surface-active)', color:'var(--text-muted)', borderRadius:'var(--radius-full)', padding:'2px 8px' }}>{ap.trigger_type}</span>
                  {ap.cron_expr && <span style={{ fontSize:'var(--text-xs)', fontFamily:'var(--font-mono)', color:'var(--text-subtle)' }}>{ap.cron_expr}</span>}
                </div>
                {ap.rule && <div style={{ fontSize:'var(--text-sm)', color:'var(--text-muted)', marginTop:4 }}>{ap.rule}</div>}
                <div style={{ fontSize:'var(--text-xs)', color:'var(--text-subtle)', marginTop:4 }}>
                  agente: {ap.target_agent || '—'}{ap.webhook_token && <React.Fragment> · webhook: <code style={{ fontFamily:'var(--font-mono)' }}>/api/autopilots/hook/{ap.webhook_token}</code></React.Fragment>}
                </div>
              </div>
              <div style={{ display:'flex', alignItems:'center', gap:12, flexShrink:0 }}>
                <Button variant="link">rodar agora</Button>
                <Button variant="ghost" size="sm" onClick={() => setItems((p) => p.map((x) => x.id === ap.id ? { ...x, enabled: !x.enabled } : x))}>{ap.enabled ? 'pausar' : 'ativar'}</Button>
                <Button variant="danger" onClick={() => setItems((p) => p.filter((x) => x.id !== ap.id))}>excluir</Button>
              </div>
            </div>
          </Card>
        ))}
        {items.length === 0 && <EmptyState>Nenhum autopilot ainda.</EmptyState>}
      </div>
    </div>
  );
}

/* ── Skills ────────────────────────────────────────────────── */
function SkillsScreen() {
  const { Button, Input, Select, Textarea, Card, EmptyState, StatusPill, Icon } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  const [items, setItems] = React.useState(D.skills);
  const [name, setName] = React.useState('');
  const [desc, setDesc] = React.useState('');
  const [content, setContent] = React.useState('');
  return (
    <div style={{ maxWidth:'var(--content-max)', margin:'0 auto', padding:24, display:'flex', flexDirection:'column', gap:24 }}>
      <h1 style={{ margin:0, fontSize:'var(--text-xl)', fontWeight:'var(--weight-semibold)', color:'var(--text-primary)' }}>Skills</h1>
      <Card tone="raised" pad={16} style={{ display:'flex', flexDirection:'column', gap:12 }}>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(2, 1fr)', gap:12 }}>
          <Input placeholder="Nome da skill" value={name} onChange={(e) => setName(e.target.value)} />
          <Input placeholder="Descrição curta" value={desc} onChange={(e) => setDesc(e.target.value)} />
        </div>
        <Textarea mono rows={4} placeholder="Conteúdo em markdown…" value={content} onChange={(e) => setContent(e.target.value)} />
        <div><Button onClick={() => { if (!name.trim()) return; setItems((p) => [...p, { id:'s' + (p.length + 1), name, description:desc, content, attached:[] }]); setName(''); setDesc(''); setContent(''); }}>Criar skill</Button></div>
      </Card>
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        {items.map((s) => (
          <Card key={s.id} tone="raised" pad={16}>
            <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between' }}>
              <div><div style={{ fontSize:'var(--text-sm)', fontWeight:'var(--weight-medium)', color:'var(--text-primary)' }}>{s.name}</div>{s.description && <div style={{ fontSize:'var(--text-sm)', color:'var(--text-muted)' }}>{s.description}</div>}</div>
              <Button variant="danger" onClick={() => setItems((p) => p.filter((x) => x.id !== s.id))}>excluir</Button>
            </div>
            {s.content && <pre style={{ marginTop:8, fontSize:'var(--text-xs)', color:'var(--text-muted)', background:'var(--surface-sunken)', border:'1px solid var(--border-default)', borderRadius:'var(--radius-md)', padding:8, overflowX:'auto', maxHeight:120, fontFamily:'var(--font-mono)' }}>{s.content}</pre>}
            <div style={{ marginTop:12, display:'flex', flexWrap:'wrap', alignItems:'center', gap:8 }}>
              {(s.attached || []).map((a) => (<span key={a} style={{ display:'inline-flex', alignItems:'center', gap:4, background:'var(--surface-active)', color:'var(--text-secondary)', fontSize:'var(--text-xs)', borderRadius:'var(--radius-full)', padding:'2px 8px' }}>{a} <span style={{ cursor:'pointer', color:'var(--text-subtle)' }} onClick={() => setItems((p) => p.map((x) => x.id === s.id ? { ...x, attached: x.attached.filter((y) => y !== a) } : x))}>×</span></span>))}
              <Button variant="link">+ agente</Button>
            </div>
          </Card>
        ))}
        {items.length === 0 && <EmptyState>Nenhuma skill ainda.</EmptyState>}
      </div>
    </div>
  );
}

/* ── Squads ────────────────────────────────────────────────── */
function SquadsScreen() {
  const { Button, Input, Select, Textarea, Card, EmptyState, StatusPill, Icon } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  const [items, setItems] = React.useState(D.squads);
  const [name, setName] = React.useState('');
  const [leader, setLeader] = React.useState(D.agents[0]?.handle || '');
  const [desc, setDesc] = React.useState('');
  return (
    <div style={{ maxWidth:'var(--content-max)', margin:'0 auto', padding:24, display:'flex', flexDirection:'column', gap:24 }}>
      <h1 style={{ margin:0, fontSize:'var(--text-xl)', fontWeight:'var(--weight-semibold)', color:'var(--text-primary)' }}>Squads</h1>
      <Card tone="raised" pad={16} style={{ display:'flex', flexDirection:'column', gap:12 }}>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:12 }}>
          <Input placeholder="Nome da squad" value={name} onChange={(e) => setName(e.target.value)} />
          <Select value={leader} onChange={(e) => setLeader(e.target.value)}>{D.agents.map((a) => <option key={a.id} value={a.handle}>líder: {a.name}</option>)}</Select>
          <Button onClick={() => { if (!name.trim()) return; setItems((p) => [...p, { id:'sq' + (p.length + 1), name, leader, description:desc, instructions:'', members:[[leader,'líder']] }]); setName(''); setDesc(''); }}>Criar squad</Button>
        </div>
        <Input placeholder="Descrição (o que a squad faz)" value={desc} onChange={(e) => setDesc(e.target.value)} />
      </Card>
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        {items.map((s) => (
          <Card key={s.id} tone="raised" pad={16}>
            <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between' }}>
              <div><div style={{ fontSize:'var(--text-sm)', fontWeight:'var(--weight-medium)', color:'var(--text-primary)' }}>{s.name}</div>
                <div style={{ fontSize:'var(--text-xs)', color:'var(--text-subtle)' }}>líder: {s.leader}</div>
                {s.description && <div style={{ fontSize:'var(--text-xs)', color:'var(--text-muted)', marginTop:4 }}>{s.description}</div>}</div>
              <Button variant="danger" onClick={() => setItems((p) => p.filter((x) => x.id !== s.id))}>excluir</Button>
            </div>
            <div style={{ marginTop:8, display:'flex', flexWrap:'wrap', gap:8 }}>
              {s.members.map(([m, role]) => (<span key={m} style={{ background:'var(--surface-active)', color:'var(--text-secondary)', fontSize:'var(--text-xs)', borderRadius:'var(--radius-full)', padding:'2px 8px' }}>{m} {role === 'líder' ? <span style={{ color:'var(--amber-500)' }}>★</span> : <span style={{ color:'var(--text-subtle)' }}>· {role}</span>}</span>))}
            </div>
          </Card>
        ))}
        {items.length === 0 && <EmptyState>Nenhuma squad ainda.</EmptyState>}
      </div>
    </div>
  );
}

/* ── Members ───────────────────────────────────────────────── */
function MembersScreen() {
  const { Button, Input, Select, Textarea, Card, EmptyState, StatusPill, Icon } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  const [members, setMembers] = React.useState(D.members);
  const [invites, setInvites] = React.useState(D.invitations);
  const [email, setEmail] = React.useState('');
  const [role, setRole] = React.useState('member');
  return (
    <div style={{ maxWidth:'var(--form-max)', margin:'0 auto', padding:24, display:'flex', flexDirection:'column', gap:24 }}>
      <h1 style={{ margin:0, fontSize:'var(--text-lg)', fontWeight:'var(--weight-semibold)', color:'var(--text-primary)' }}>Members</h1>
      <section>
        <h2 style={{ margin:'0 0 8px', fontSize:'var(--text-sm)', fontWeight:'var(--weight-medium)', color:'var(--text-secondary)' }}>Convidar membro</h2>
        <Card tone="raised" pad={16} style={{ display:'flex', gap:8 }}>
          <Input placeholder="email@exemplo.com" value={email} onChange={(e) => setEmail(e.target.value)} />
          <Select value={role} onChange={(e) => setRole(e.target.value)}><option value="member">member</option><option value="admin">admin</option></Select>
          <Button onClick={() => { if (!email.trim()) return; setInvites((p) => [...p, { id:'i' + (p.length + 1), email, role, expires:'02/09/2026' }]); setEmail(''); }}>Convidar</Button>
        </Card>
      </section>
      <section>
        <h2 style={{ margin:'0 0 8px', fontSize:'var(--text-sm)', fontWeight:'var(--weight-medium)', color:'var(--text-secondary)' }}>Membros ({members.length})</h2>
        <Card tone="raised" pad={0} style={{ overflow:'hidden' }}>
          {members.map((m) => (
            <div key={m.id} style={{ display:'flex', alignItems:'center', gap:12, padding:'10px 16px', borderBottom:'1px solid var(--border-hairline)' }}>
              <div style={{ flex:1, minWidth:0 }}>
                <div style={{ fontSize:'var(--text-sm)', color:'var(--text-body)' }}>{m.name}</div>
                <div style={{ fontSize:'var(--text-xs)', color:'var(--text-subtle)' }}>{m.email}</div>
              </div>
              {m.you ? <span style={{ fontSize:'var(--text-xs)', fontFamily:'var(--font-mono)', color:'var(--text-subtle)' }}>{m.role}</span> : (
                <React.Fragment>
                  <Select value={m.role} onChange={(e) => setMembers((p) => p.map((x) => x.id === m.id ? { ...x, role:e.target.value } : x))} style={{ fontSize:'var(--text-xs)' }}>
                    <option value="owner">owner</option><option value="admin">admin</option><option value="member">member</option>
                  </Select>
                  <Button variant="danger" onClick={() => setMembers((p) => p.filter((x) => x.id !== m.id))}>remover</Button>
                </React.Fragment>
              )}
            </div>
          ))}
        </Card>
      </section>
      <section>
        <h2 style={{ margin:'0 0 8px', fontSize:'var(--text-sm)', fontWeight:'var(--weight-medium)', color:'var(--text-secondary)' }}>Convites pendentes ({invites.length})</h2>
        {invites.length ? (
          <Card tone="raised" pad={0} style={{ overflow:'hidden' }}>
            {invites.map((inv) => (
              <div key={inv.id} style={{ display:'flex', alignItems:'center', gap:12, padding:'10px 16px', borderBottom:'1px solid var(--border-hairline)' }}>
                <div style={{ flex:1 }}><div style={{ fontSize:'var(--text-sm)', color:'var(--text-body)' }}>{inv.email}</div><div style={{ fontSize:'var(--text-xs)', color:'var(--text-subtle)' }}>papel: {inv.role} · expira {inv.expires}</div></div>
                <Button variant="danger" onClick={() => setInvites((p) => p.filter((x) => x.id !== inv.id))}>revogar</Button>
              </div>
            ))}
          </Card>
        ) : <p style={{ margin:0, fontSize:'var(--text-xs)', color:'var(--text-subtle)' }}>Nenhum convite pendente.</p>}
      </section>
    </div>
  );
}

/* ── Search ────────────────────────────────────────────────── */
function SearchScreen({ query, setQuery, issues }) {
  const { Button, Input, Select, Textarea, Card, EmptyState, StatusPill, Icon } = window.RyuDesignSystem_7ed69e;
  const q = (query || '').toLowerCase();
  const results = q ? issues.filter((i) => i.title.toLowerCase().includes(q) || i.key.toLowerCase().includes(q)) : [];
  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%' }}>
      <PageHeader title="Search" />
      <div style={{ padding:'0 24px' }}>
        <Input full={false} style={{ width:420, marginTop:12 }} placeholder="Buscar issues, agents, chats…" value={query} onChange={(e) => setQuery(e.target.value)} autoFocus />
      </div>
      <div style={{ padding:24 }}>
        {q && results.length === 0 && <EmptyState>Nenhum resultado para "{query}".</EmptyState>}
        {results.map((i) => (
          <div key={i.key} style={{ display:'flex', alignItems:'center', gap:12, padding:'10px 0', borderBottom:'1px solid var(--border-hairline)' }}>
            <span style={{ font:'var(--type-key)', color:'var(--text-subtle)', width:70 }}>{i.key}</span>
            <span style={{ fontSize:'var(--text-sm)', color:'var(--text-body)' }}>{i.title}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

Object.assign(window, { AutopilotsScreen, SkillsScreen, SquadsScreen, MembersScreen, SearchScreen });
