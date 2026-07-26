/* ── Dashboard ─────────────────────────────────────────────── */
function DashboardScreen({ issues, go }) {
  const { Button, Input, Select, Textarea, Card, EmptyState, StatusDot, StatusPill, PriorityTag, CountBadge, IssueKey, DataTable, ChatBubble, InboxItem, StatCard, AgentCard, Icon } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  return (
    <div style={{ padding:24, display:'flex', flexDirection:'column', gap:32 }}>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
        <div>
          <h1 style={{ margin:0, fontSize:'var(--text-xl)', fontWeight:'var(--weight-semibold)', color:'var(--text-primary)' }}>{D.workspace.name}</h1>
          <p style={{ margin:'2px 0 0', fontSize:'var(--text-sm)', color:'var(--text-subtle)' }}>Visão geral do workspace</p>
        </div>
        <Button onClick={() => go('board')}>Ir para o Board</Button>
      </div>
      <section>
        <h2 style={{ margin:'0 0 12px', fontSize:'var(--text-sm)', fontWeight:'var(--weight-medium)', color:'var(--text-muted)', textTransform:'uppercase', letterSpacing:'var(--tracking-wider)' }}>Issues</h2>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(7, 1fr)', gap:12 }}>
          {D.statusOrder.map((s) => (
            <StatCard key={s} hoverable value={issues.filter((i) => i.status === s).length}
              label={D.statusTitles[s]} status={s} style={{ cursor:'pointer' }} onClick={() => go('board')} />
          ))}
        </div>
      </section>
      <section>
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:12 }}>
          <h2 style={{ margin:0, fontSize:'var(--text-sm)', fontWeight:'var(--weight-medium)', color:'var(--text-muted)', textTransform:'uppercase', letterSpacing:'var(--tracking-wider)' }}>Agents</h2>
          <a href="#" onClick={(e) => { e.preventDefault(); go('agents'); }} style={{ fontSize:'var(--text-xs)' }}>ver todos</a>
        </div>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:12 }}>
          {D.agents.map((a) => <AgentCard key={a.id} compact {...a} />)}
        </div>
      </section>
      <section>
        <h2 style={{ margin:'0 0 12px', fontSize:'var(--text-sm)', fontWeight:'var(--weight-medium)', color:'var(--text-muted)', textTransform:'uppercase', letterSpacing:'var(--tracking-wider)' }}>Tasks recentes</h2>
        <DataTable
          columns={[{key:'agent',label:'Agente'},{key:'kind',label:'Tipo',muted:true},{key:'status',label:'Status'},{key:'summary',label:'Resumo',muted:true,maxWidth:280},{key:'at',label:'Criada',align:'right',small:true,muted:true}]}
          rows={D.tasks.map((t) => ({ ...t, status:<StatusPill kind="task" status={t.status} /> }))}
          empty="Nenhuma task executada ainda." />
      </section>
    </div>
  );
}

/* ── Chat ──────────────────────────────────────────────────── */
function ChatScreen() {
  const { Button, Input, Select, Textarea, Card, EmptyState, StatusDot, StatusPill, PriorityTag, CountBadge, IssueKey, DataTable, ChatBubble, InboxItem, StatCard, AgentCard, Icon } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  const [messages, setMessages] = React.useState(D.messages);
  const [draft, setDraft] = React.useState('');
  const [active, setActive] = React.useState(0);
  const sessions = [{ title:'RYU-142 · travamento do runner', pinned:true }, { title:'Plano de migração p/ Postgres' }, { title:'Revisão do CONTRACTS.md' }];
  const typing = messages[messages.length - 1] && messages[messages.length - 1].role === 'user';
  return (
    <div style={{ display:'flex', height:'100%' }}>
      <aside style={{ width:'var(--chat-list-width)', flexShrink:0, borderRight:'1px solid var(--border-default)', background:'var(--chat-list-bg)', display:'flex', flexDirection:'column' }}>
        <div style={{ padding:12, borderBottom:'1px solid var(--border-default)', display:'flex', gap:8 }}>
          <Select full>{D.agents.map((a) => <option key={a.id}>{a.name} ({a.handle})</option>)}</Select>
          <Button size="sm" style={{ padding:'6px 12px' }}>Novo</Button>
        </div>
        <nav style={{ flex:1, overflowY:'auto', padding:'8px 4px' }}>
          {sessions.map((s, i) => (
            <a key={i} href="#" onClick={(e) => { e.preventDefault(); setActive(i); }}
              style={{ display:'flex', alignItems:'center', gap:8, padding:'8px 12px', margin:'0 4px', borderRadius:'var(--radius-md)', fontSize:'var(--text-sm)', textDecoration:'none',
                background: active === i ? 'var(--surface-active)' : 'transparent', color: active === i ? 'var(--text-primary)' : 'var(--text-muted)' }}>
              {s.pinned && <Icon name="star" size={12} style={{ color:'var(--amber-500)' }} />}
              <span style={{ overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{s.title}</span>
            </a>
          ))}
        </nav>
      </aside>
      <section style={{ flex:1, display:'flex', flexDirection:'column', background:'var(--chat-panel-bg)', minWidth:0 }}>
        <header style={{ display:'flex', alignItems:'center', gap:8, padding:'12px 16px', borderBottom:'1px solid var(--border-default)' }}>
          <span style={{ flex:1, fontSize:'var(--text-sm)', fontWeight:'var(--weight-medium)', color:'var(--text-primary)' }}>{sessions[active].title}</span>
          <span style={{ color:'var(--amber-500)', cursor:'pointer', display:'inline-flex' }}><Icon name="star" size={16} /></span>
          <span style={{ color:'var(--text-subtle)', cursor:'pointer', display:'inline-flex' }}><Icon name="archive" size={16} /></span>
        </header>
        <div style={{ flex:1, overflowY:'auto', padding:16, display:'flex', flexDirection:'column', gap:12 }}>
          {messages.map((m, i) => <ChatBubble key={i} role={m.role} time={m.time}>{m.content}</ChatBubble>)}
          {typing && <ChatBubble typing>agente digitando…</ChatBubble>}
        </div>
        <footer style={{ padding:12, borderTop:'1px solid var(--border-default)' }}>
          <form style={{ display:'flex', gap:8 }} onSubmit={(e) => { e.preventDefault(); if (!draft.trim()) return;
            setMessages((m) => [...m, { role:'user', content:draft, time:'agora' }]); setDraft('');
            setTimeout(() => setMessages((m) => [...m, { role:'agent', content:'Anotado. Abrindo a issue e enfileirando a task.', time:'agora' }]), 1200); }}>
            <Input placeholder="Mensagem para o agente…" value={draft} onChange={(e) => setDraft(e.target.value)}
              style={{ background:'var(--surface-input)', borderColor:'var(--border-strong)', borderRadius:'var(--radius-lg)', padding:'8px 12px' }} />
            <Button type="submit" size="lg" style={{ borderRadius:'var(--radius-lg)' }}>Enviar</Button>
          </form>
        </footer>
      </section>
    </div>
  );
}

/* ── Inbox ─────────────────────────────────────────────────── */
function InboxScreen({ items, markRead, markAll }) {
  const { Button, Input, Select, Textarea, Card, EmptyState, StatusDot, StatusPill, PriorityTag, CountBadge, IssueKey, DataTable, ChatBubble, InboxItem, StatCard, AgentCard, Icon } = window.RyuDesignSystem_7ed69e;
  const unread = items.filter((i) => !i.read).length;
  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%' }}>
      <PageHeader title="Inbox" right={
        <React.Fragment>
          <Select size="sm"><option>Todas severidades</option><option>Ação necessária</option><option>Atenção</option></Select>
          <Select size="sm"><option>Todas</option><option>Não lidas</option><option>Lidas</option></Select>
          <Button variant="secondary" size="sm" onClick={markAll}>Marcar todas como lidas</Button>
        </React.Fragment>
      } kicker={unread ? unread + ' não lidas' : null} />
      <div style={{ flex:1, overflowY:'auto' }}>
        {items.length === 0 && <div style={{ padding:'48px 24px', textAlign:'center', fontSize:'var(--text-sm)', color:'var(--text-subtle)' }}>Inbox vazia. Nada por aqui.</div>}
        {items.map((it, i) => (
          <InboxItem key={i} {...it} time={it.at}>
            {!it.read && <Button variant="ghost" size="sm" onClick={() => markRead(i)}>Lida</Button>}
            <Button variant="ghost" size="sm">Arquivar</Button>
          </InboxItem>
        ))}
      </div>
    </div>
  );
}

/* ── Agents ────────────────────────────────────────────────── */
function AgentsScreen() {
  const { Button, Input, Select, Textarea, Card, EmptyState, StatusDot, StatusPill, PriorityTag, CountBadge, IssueKey, DataTable, ChatBubble, InboxItem, StatCard, AgentCard, Icon } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  return (
    <div style={{ maxWidth:'var(--content-max)', margin:'0 auto', padding:24, display:'flex', flexDirection:'column', gap:32 }}>
      <h1 style={{ margin:0, fontSize:'var(--text-xl)', fontWeight:'var(--weight-semibold)', color:'var(--text-primary)' }}>Agents</h1>
      <Card tone="muted" pad={16} style={{ display:'flex', flexWrap:'wrap', gap:8, alignItems:'flex-end' }}>
        {[['Nome','Codebot',140],['Handle','@codebot',140],['Descrição','O que este agente faz',0]].map(([l, ph, w]) => (
          <div key={l} style={{ display:'flex', flexDirection:'column', gap:4, flex: w ? 'none' : 1, width: w || undefined }}>
            <label style={{ fontSize:'var(--text-xs)', color:'var(--text-muted)' }}>{l}</label>
            <Input size="sm" tone="raised" placeholder={ph} style={{ background:'var(--zinc-800)' }} />
          </div>
        ))}
        <div style={{ display:'flex', flexDirection:'column', gap:4 }}>
          <label style={{ fontSize:'var(--text-xs)', color:'var(--text-muted)' }}>Runtime</label>
          <Select size="sm" style={{ background:'var(--zinc-800)' }}><option>claude</option><option>codex</option><option>gemini</option></Select>
        </div>
        <Button size="sm" style={{ padding:'6px 16px' }}>Criar agente</Button>
      </Card>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:12 }}>
        {D.agents.map((a) => <AgentCard key={a.id} {...a} />)}
      </div>
      <div>
        <h2 style={{ margin:'0 0 8px', fontSize:'var(--text-sm)', fontWeight:'var(--weight-semibold)', color:'var(--text-secondary)' }}>Tasks recentes</h2>
        <DataTable columns={[{key:'agent',label:'Agente'},{key:'kind',label:'Kind',muted:true},{key:'status',label:'Status'},{key:'at',label:'Criada',small:true,muted:true}]}
          rows={D.tasks.map((t) => ({ ...t, status:<StatusPill kind="task" status={t.status} /> }))} empty="Nenhuma task ainda." />
      </div>
    </div>
  );
}

/* ── Usage ─────────────────────────────────────────────────── */
function UsageScreen() {
  const { Button, Input, Select, Textarea, Card, EmptyState, StatusDot, StatusPill, PriorityTag, CountBadge, IssueKey, DataTable, ChatBubble, InboxItem, StatCard, AgentCard, Icon } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA, u = D.usage;
  const fmt = (n) => n.toLocaleString('en-US');
  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%', overflowY:'auto' }}>
      <PageHeader title="Usage" sub={`Últimos ${u.days} dias — desde 2026-06-25`} />
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4, 1fr)', gap:16, padding:'24px' }}>
        <StatCard value={u.tasks} label="Tasks" />
        <StatCard value={fmt(u.input)} label="Input tokens" />
        <StatCard value={fmt(u.output)} label="Output tokens" />
        <StatCard value={'$' + u.cost.toFixed(4)} label="Custo (USD)" accent />
      </div>
      <div style={{ padding:'0 24px 24px' }}>
        <h2 style={{ margin:'0 0 8px', fontSize:'var(--text-sm)', fontWeight:'var(--weight-medium)', color:'var(--text-secondary)' }}>Por agente</h2>
        <DataTable bordered={false}
          columns={[{key:'agent',label:'Agente'},{key:'tasks',label:'Tasks'},{key:'i',label:'Input'},{key:'o',label:'Output'},{key:'c',label:'Custo'},{key:'s',label:'Status',small:true,muted:true}]}
          rows={[{agent:'Codebot',tasks:141,i:'3,204,881',o:'268,110',c:'$25.9012',s:'completed: 118 · failed: 9'},
                 {agent:'Reviewer',tasks:52,i:'1,102,441',o:'88,220',c:'$9.4180',s:'completed: 50 · cancelled: 2'},
                 {agent:'Docs',tasks:21,i:'505,578',o:'35,112',c:'$2.9519',s:'completed: 21'}]} />
      </div>
    </div>
  );
}

/* ── Placeholder para telas não recriadas ──────────────────── */
function StubScreen({ title, note }) {
  const { Button, Input, Select, Textarea, Card, EmptyState, StatusDot, StatusPill, PriorityTag, CountBadge, IssueKey, DataTable, ChatBubble, InboxItem, StatCard, AgentCard, Icon } = window.RyuDesignSystem_7ed69e;
  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%' }}>
      <PageHeader title={title} />
      <div style={{ padding:24 }}><EmptyState>{note}</EmptyState></div>
    </div>
  );
}

/* ── Profile ───────────────────────────────────────────────── */
function ProfileScreen({ user, setUser, onLogout }) {
  const { Button, Input, Select, Textarea, Card, EmptyState, StatusDot, StatusPill, PriorityTag, CountBadge, IssueKey, DataTable, ChatBubble, InboxItem, StatCard, AgentCard, Icon } = window.RyuDesignSystem_7ed69e;
  const [nickname, setNickname] = React.useState(user.nickname);
  const [email, setEmail] = React.useState(user.email);
  const initials = (user.nickname || '?').trim().split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase();
  return (
    <div style={{ maxWidth:'var(--form-max)', margin:'0 auto', padding:24, display:'flex', flexDirection:'column', gap:24 }}>
      <h1 style={{ margin:0, fontSize:'var(--text-xl)', fontWeight:'var(--weight-semibold)', color:'var(--text-primary)' }}>Perfil</h1>
      <Card tone="raised" pad={20} style={{ display:'flex', alignItems:'center', gap:16 }}>
        <div style={{ width:64, height:64, borderRadius:'var(--radius-full)', background:'var(--surface-active)', color:'var(--text-secondary)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:'var(--text-xl)', fontWeight:'var(--weight-semibold)', flexShrink:0 }}>{initials}</div>
        <div>
          <Button variant="outline" size="sm">Trocar foto</Button>
          <p style={{ margin:'6px 0 0', fontSize:'var(--text-xs)', color:'var(--text-subtle)' }}>PNG ou JPG, até 2MB. Sem foto, usamos as iniciais do apelido.</p>
        </div>
      </Card>
      <Card tone="raised" pad={20} style={{ display:'flex', flexDirection:'column', gap:16 }}>
        <div>
          <label style={{ display:'block', marginBottom:4, fontSize:'var(--text-xs)', color:'var(--text-muted)' }}>Apelido</label>
          <Input value={nickname} onChange={(e) => setNickname(e.target.value)} />
        </div>
        <div>
          <label style={{ display:'block', marginBottom:4, fontSize:'var(--text-xs)', color:'var(--text-muted)' }}>E-mail</label>
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div><Button onClick={() => setUser((u) => ({ ...u, nickname, email }))}>Salvar</Button></div>
      </Card>
      <Card tone="raised" pad={20}>
        <Button variant="danger" onClick={onLogout}>Sair da conta</Button>
      </Card>
    </div>
  );
}

Object.assign(window, { DashboardScreen, ChatScreen, InboxScreen, AgentsScreen, UsageScreen, StubScreen, ProfileScreen });
