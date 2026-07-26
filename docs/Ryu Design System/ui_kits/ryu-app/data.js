window.RYU_DATA = {
  workspace: { name: 'Ryu', slug: 'ryu', prefix: 'RYU' },
  user: { name: 'Renato Bardi', email: 'renato@exemplo.com' },
  agents: [
    { id:'a1', name:'Codebot', handle:'codebot', runtime:'claude', status:'working', description:'Corrige bugs e abre PRs no backend' },
    { id:'a2', name:'Reviewer', handle:'reviewer', runtime:'codex', status:'idle', description:'Revisa diffs antes do merge' },
    { id:'a3', name:'Docs', handle:'docs', runtime:'gemini', status:'offline', description:'Mantém README e CONTRACTS' },
  ],
  statusOrder: ['backlog','todo','in_progress','in_review','done','blocked','cancelled'],
  statusTitles: { backlog:'Backlog', todo:'Todo', in_progress:'In Progress', in_review:'In Review', done:'Done', blocked:'Blocked', cancelled:'Cancelled' },
  issues: [
    { key:'RYU-142', title:'Runner trava quando a CLI do agente sai com código 1', status:'in_progress', priority:'urgent', assignee:'codebot' },
    { key:'RYU-140', title:'Migrar o hub realtime para Redis pub/sub', status:'in_progress', priority:'high', assignee:'codebot' },
    { key:'RYU-138', title:'Integração bidirecional com GitHub Issues', status:'todo', priority:'high', assignee:'reviewer' },
    { key:'RYU-137', title:'Alembic para migrações em Postgres', status:'todo', priority:'medium' },
    { key:'RYU-131', title:'Marketplace de skills', status:'backlog', priority:'low' },
    { key:'RYU-129', title:'Notificações no Slack por canal de agente', status:'backlog', priority:'none' },
    { key:'RYU-126', title:'Rate limit por workspace no dispatch de tasks', status:'in_review', priority:'medium', assignee:'reviewer' },
    { key:'RYU-118', title:'Login por código de verificação', status:'done', priority:'high' },
    { key:'RYU-115', title:'Workspaces isolados em /data/workspaces', status:'done', priority:'medium', assignee:'codebot' },
    { key:'RYU-109', title:'Adapter do gemini-cli sem binário no PATH', status:'blocked', priority:'medium', assignee:'docs' },
  ],
  tasks: [
    { agent:'Codebot', kind:'issue_work', status:'running', summary:'Rodando pytest em RYU-142', at:'24/07 09:12' },
    { agent:'Reviewer', kind:'review', status:'completed', summary:'Aprovado com 2 comentários', at:'24/07 08:40' },
    { agent:'Codebot', kind:'issue_work', status:'failed', summary:'claude CLI retornou exit 1', at:'23/07 22:05' },
    { agent:'Docs', kind:'chore', status:'queued', summary:'Atualizar CONTRACTS.md', at:'23/07 19:31' },
  ],
  inbox: [
    { severity:'action_required', title:'codebot pediu aprovação em RYU-142', body:'Vai alterar o schema da tabela tasks — precisa de review humano.', at:'24/07 09:12', read:false },
    { severity:'attention', title:'Task falhou em RYU-142', body:'claude CLI retornou exit 1 no workspace /data/workspaces/RYU-142.', at:'23/07 22:05', read:false },
    { severity:'info', title:'reviewer concluiu RYU-126', body:'Aprovado com 2 comentários.', at:'23/07 18:44', read:true },
  ],
  messages: [
    { role:'agent', content:'Peguei a RYU-142. Reproduzi o travamento: o runner não trata exit != 0 do subprocess.', time:'14:01' },
    { role:'user', content:'Manda ver. Cria um teste que cubra exit 1 antes do fix.', time:'14:02' },
    { role:'system', content:'task:dispatched · workspace /data/workspaces/RYU-142', time:'14:02' },
    { role:'agent', content:'Teste escrito em tests/test_flow.py. Rodando pytest…', time:'14:03' },
  ],
  usage: { days: 30, tasks: 214, input: 4812900, output: 391442, cost: 38.2711 },
  projects: [
    { id:'p1', name:'Core Runner', status:'active', description:'Dispatcher de tasks e integração com CLIs de agente' },
    { id:'p2', name:'Integrações', status:'active', description:'GitHub, Slack e webhooks externos' },
    { id:'p3', name:'Onboarding', status:'archived', description:'Fluxo de convite e primeiro workspace' },
  ],
  issueCounts: { p1: 6, p2: 2, p3: 1 },
  autopilots: [
    { id:'ap1', name:'Triagem diária', trigger_type:'cron', cron_expr:'0 9 * * 1-5', enabled:true, target_agent:'codebot', rule:'Revisar issues sem assignee e atribuir ao agente certo com base no título.' },
    { id:'ap2', name:'Deploy hook', trigger_type:'webhook', webhook_token:'wh_9f2a1c', enabled:true, target_agent:'reviewer', rule:'Ao receber webhook de deploy, abrir issue de smoke test.' },
    { id:'ap3', name:'Limpeza de backlog', trigger_type:'manual', enabled:false, target_agent:null, rule:'Fechar issues de backlog com mais de 90 dias sem atividade.' },
  ],
  skills: [
    { id:'s1', name:'Revisão de PR', description:'Checklist de estilo e testes antes de aprovar', content:'# Revisão\\n- Rodar lint\\n- Checar testes\\n- Validar migrations', attached:['codebot','reviewer'] },
    { id:'s2', name:'Runbook de incidente', description:'Passos para triagem de falha em produção', content:'1. Checar logs\\n2. Isolar workspace\\n3. Abrir issue urgent', attached:['docs'] },
  ],
  squads: [
    { id:'sq1', name:'Backend Squad', leader:'codebot', description:'Cuida do runner e da API', instructions:'Sempre rodar testes antes de abrir PR.', members:[['codebot','líder'],['reviewer','revisor']] },
  ],
  runtimes: [
    { name:'claude', available:true, path:'/usr/local/bin/claude' },
    { name:'codex', available:true, path:'/usr/local/bin/codex' },
    { name:'gemini', available:false, path:null },
  ],
  members: [
    { id:'m1', name:'Renato Bardi', email:'renato@exemplo.com', role:'owner', you:true },
    { id:'m2', name:'Ana Souza', email:'ana@exemplo.com', role:'admin' },
    { id:'m3', name:'Bruno Lima', email:'bruno@exemplo.com', role:'member' },
  ],
  invitations: [
    { id:'i1', email:'novo@exemplo.com', role:'member', expires:'02/08/2026' },
  ],
  patTokens: [
    { id:'t1', name:'cli local', created:'20/07/2026' },
  ],
};
