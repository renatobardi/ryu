/* ── Board ─────────────────────────────────────────────────── */
function BoardScreen({ issues, addIssue, openIssue }) {
  const { Button, Input, Select, Textarea, Card, EmptyState, StatusDot, StatusPill, PriorityTag, CountBadge, IssueKey, DataTable, IssueCard, BoardColumn, ChatBubble, InboxItem, StatCard, AgentCard, Icon } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  const [title, setTitle] = React.useState('');
  const [status, setStatus] = React.useState('backlog');
  const [agent, setAgent] = React.useState('');
  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%' }}>
      <PageHeader title={D.workspace.name} kicker="Board" right={
        <form style={{ display:'flex', alignItems:'center', gap:8 }} onSubmit={(e) => { e.preventDefault(); if (!title.trim()) return; addIssue(title, status, agent); setTitle(''); }}>
          <Input full={false} style={{ width:256 }} placeholder="Nova issue..." value={title} onChange={(e) => setTitle(e.target.value)} />
          <Select value={status} onChange={(e) => setStatus(e.target.value)}>
            {D.statusOrder.map((s) => <option key={s} value={s}>{D.statusTitles[s]}</option>)}
          </Select>
          <Select value={agent} onChange={(e) => setAgent(e.target.value)}>
            <option value="">Sem agente</option>
            {D.agents.map((a) => <option key={a.id} value={a.handle}>@{a.handle}</option>)}
          </Select>
          <Button type="submit" size="sm" style={{ padding:'6px 12px' }}>Criar</Button>
        </form>
      } />
      <div style={{ display:'flex', gap:16, padding:'16px 24px', overflowX:'auto', flex:1 }}>
        {D.statusOrder.map((s) => {
          const items = issues.filter((i) => i.status === s);
          return (
            <BoardColumn key={s} title={D.statusTitles[s]} count={items.length}>
              {items.map((i) => (
                <IssueCard key={i.key} issueKey={i.key} title={i.title} priority={i.priority}
                  assignee={i.assignee} onClick={() => openIssue(i)} />
              ))}
            </BoardColumn>
          );
        })}
      </div>
    </div>
  );
}

/* ── Issue detail ──────────────────────────────────────────── */
function IssueScreen({ issue, back, patch }) {
  const { Button, Input, Select, Textarea, Card, EmptyState, StatusDot, StatusPill, PriorityTag, CountBadge, IssueKey, DataTable, IssueCard, BoardColumn, ChatBubble, InboxItem, StatCard, AgentCard, Icon } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  const [comments, setComments] = React.useState([
    { author:'agent', body:'Reproduzi o travamento: o runner não trata exit != 0 do subprocess. Vou cobrir com teste antes do fix.', at:'24/07 09:05' },
    { author:'system', body:'task:running · /data/workspaces/RYU-142', at:'24/07 09:12' },
  ]);
  const [draft, setDraft] = React.useState('');
  return (
    <div style={{ maxWidth:'var(--content-max)', margin:'0 auto', padding:'24px', display:'grid', gridTemplateColumns:'1fr var(--issue-sidebar-width)', gap:32 }}>
      <div>
        <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:8 }}>
          <a href="#" onClick={(e) => { e.preventDefault(); back(); }} style={{ display:'inline-flex', alignItems:'center', gap:4, fontSize:'var(--text-xs)', color:'var(--text-subtle)' }}><Icon name="arrow-left" size={12} /> Board</a>
          <IssueKey>{issue.key}</IssueKey>
          <span style={{ fontSize:'var(--text-2xs)', padding:'2px 6px', borderRadius:'var(--radius-full)', border:'1px solid var(--border-strong)', color:'var(--text-accent)' }}>runner</span>
        </div>
        <h1 style={{ margin:'0 0 12px', fontSize:'var(--text-2xl)', fontWeight:'var(--weight-semibold)', color:'var(--text-primary)', textWrap:'pretty' }}>{issue.title}</h1>
        <Card tone="muted" pad={16} style={{ marginBottom:24, fontSize:'var(--text-sm)', color:'var(--text-secondary)', whiteSpace:'pre-wrap' }}>
{`O runner despacha a CLI do agente com subprocess e assume exit 0.
Quando a CLI falha, a task fica presa em "running" e o hub nunca publica task:failed.`}
        </Card>
        <h2 style={{ margin:'0 0 8px', fontSize:'var(--text-sm)', fontWeight:'var(--weight-medium)', color:'var(--text-muted)' }}>Comentários</h2>
        <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
          {comments.map((c, i) => (
            <Card key={i} tone="muted" pad={12}>
              <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:4 }}>
                <span style={{ fontSize:'var(--text-xs)', fontWeight:'var(--weight-medium)', color: c.author === 'agent' ? 'var(--text-accent)' : c.author === 'system' ? 'var(--text-subtle)' : 'var(--text-secondary)', display:'inline-flex', alignItems:'center', gap:4 }}>
                  {c.author === 'agent' ? <React.Fragment><Icon name="bot" size={12} /> agent</React.Fragment> : c.author === 'system' ? 'sistema' : <React.Fragment><Icon name="user" size={12} /> member</React.Fragment>}
                </span>
                <span style={{ fontSize:'var(--text-11)', color:'var(--text-faint)' }}>{c.at}</span>
              </div>
              <p style={{ margin:0, fontSize:'var(--text-sm)', color:'var(--text-body)', whiteSpace:'pre-wrap' }}>{c.body}</p>
            </Card>
          ))}
        </div>
        <form style={{ marginTop:16 }} onSubmit={(e) => { e.preventDefault(); if (!draft.trim()) return; setComments([...comments, { author:'member', body:draft, at:'agora' }]); setDraft(''); }}>
          <Textarea rows={3} placeholder="Escreva um comentário..." value={draft} onChange={(e) => setDraft(e.target.value)} />
          <div style={{ marginTop:8, display:'flex', justifyContent:'flex-end' }}><Button type="submit">Comentar</Button></div>
        </form>
      </div>
      <aside style={{ display:'flex', flexDirection:'column', gap:16 }}>
        {[['Status', D.statusOrder.map((s) => [s, D.statusTitles[s]]), issue.status, 'status'],
          ['Prioridade', ['urgent','high','medium','low','none'].map((p) => [p, p]), issue.priority, 'priority']].map(([label, opts, val, key]) => (
          <div key={key}>
            <label style={{ display:'block', marginBottom:4, fontSize:'var(--text-11)', textTransform:'uppercase', letterSpacing:'var(--tracking-wide)', color:'var(--text-subtle)' }}>{label}</label>
            <Select full value={val} onChange={(e) => patch(issue.key, key, e.target.value)}>
              {opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
          </div>
        ))}
        <div>
          <label style={{ display:'block', marginBottom:4, fontSize:'var(--text-11)', textTransform:'uppercase', letterSpacing:'var(--tracking-wide)', color:'var(--text-subtle)' }}>Agente</label>
          <Select full value={issue.assignee || ''} onChange={(e) => patch(issue.key, 'assignee', e.target.value)}>
            <option value="">Sem assignee</option>
            {D.agents.map((a) => <option key={a.id} value={a.handle}>@{a.handle}</option>)}
          </Select>
        </div>
        <div style={{ paddingTop:8, borderTop:'1px solid var(--border-default)', fontSize:'var(--text-xs)', color:'var(--text-subtle)', display:'flex', flexDirection:'column', gap:4 }}>
          <p style={{ margin:0 }}>Criada: 21/07/2026 11:04</p>
          <p style={{ margin:0 }}>Atualizada: 24/07/2026 09:12</p>
          {issue.assignee && <p style={{ margin:0, color:'var(--text-accent)', display:'flex', alignItems:'center', gap:4 }}><Icon name="bot" size={12} /> Assignee: {issue.assignee}</p>}
        </div>
      </aside>
    </div>
  );
}

Object.assign(window, { BoardScreen, IssueScreen });
