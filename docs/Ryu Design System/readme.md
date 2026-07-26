# Ryu — Design System

Design system extraído do produto **Ryu**: um issue tracker onde agentes de IA (Claude Code, Codex, Gemini CLI) são membros da equipe. Você cria issues num board estilo Linear, atribui a um agente, e ele trabalha num workspace isolado reportando progresso em tempo real por WebSocket. Humanos e agentes convivem no mesmo board, chat e inbox.

**Fonte única:** [github.com/renatobardi/ryu](https://github.com/renatobardi/ryu) (branch `main`) — em especial `src/ryu/web/templates/` e `src/ryu/web/static/app.css`. Vale explorar o repositório diretamente antes de desenhar algo novo: os templates Jinja são a verdade sobre espaçamentos e estados.

> **Errata (issue [renatobardi/ryu#7](https://github.com/renatobardi/ryu/issues/7)):** três afirmações abaixo ficaram desatualizadas em relação a `tokens/colors.css` e às decisões de implantação — a fonte de verdade atual é o mapa linkado, não este texto.
> - "Dark-only. Não existe tema claro" (linha ~39) — revogado: produto tem tema claro e escuro, claro é o default.
> - "o acento único é violet" (linha ~41) — revogado: o accent real é ciano (`--indigo-600`/`#0891b2` em `tokens/colors.css`), não violet.
> - "Chat usa `neutral`, inconsistência preservada por fidelidade" (linha ~41) — revogado: Chat usa os mesmos tokens semânticos do resto do produto.

## O produto

Uma superfície só: **aplicação web** servida pelo próprio FastAPI (Jinja2 + HTMX + Tailwind via CDN + `app.css`). Não há site de marketing, app mobile nem docs separados. Rotas de página em `/w/{slug}/...`; API em `/api/*`; realtime em `/ws/{workspace_id}`.

Telas: Login (código de verificação em 2 passos) · Dashboard · Board (7 colunas, drag-and-drop) · Issue detail · Chat com agentes · Inbox de eventos · My Issues · Projects · Autopilots · Agents · Squads · Usage · Runtimes · Skills · Settings · Search.

Domínios de vocabulário: **issue** (backlog|todo|in_progress|in_review|done|blocked|cancelled), **task** (queued|dispatched|running|completed|failed|cancelled), **agent** (idle|working|blocked|error|offline), **runtime** (claude|codex|gemini), **autopilot** (cron|webhook|manual), **squad**, **skill**, **workspace**.

---

## CONTENT FUNDAMENTALS

**A UI é bilíngue por convenção, não por acidente.** Rótulos de navegação e nomes de entidade ficam em **inglês** (Inbox, Chat, My Issues, Issues, Projects, Autopilots, Agents, Squads, Usage, Runtimes, Skills, Settings); títulos de página seguem o mesmo inglês. Tudo que é **frase** — instrução, placeholder, estado vazio, botão de ação — é **português do Brasil**: "Criar agente", "Enviar código", "Marcar todas como lidas", "Nenhuma task executada ainda.".

**Estados do backend nunca são traduzidos nem capitalizados.** `working`, `completed`, `queued`, `in_progress`, `urgent` aparecem crus, em minúsculas, dentro das pills. Só os títulos de coluna do board recebem forma humana ("In Progress"), e ainda em inglês.

**Casing:** sentence case em tudo. UPPERCASE só em labels estruturais de 10px com `tracking-wider` (WORKSPACE, CONFIGURE, ISSUES, AGENTS, TASKS RECENTES) e nas tags de prioridade.

**Tom:** direto, sem marketing, sem exclamação, sem "nós". Fala com o usuário na segunda pessoa implícita e usa imperativo: "Digite o e-mail", "Instale o CLI desejado no host". Explicações técnicas assumem que quem lê é engenheiro — cita `PATH`, `cwd`, `asyncpg` sem glossário.

**Estados vazios** são uma frase curta + o próximo passo, quando existe: *"Nenhum agente ainda. Crie o primeiro em Agents."*, *"Inbox vazia. Nada por aqui."*, *"Sem mensagens ainda. Diga oi."*. Nunca ilustração, nunca parágrafo.

**Ações inline em listas são verbos minúsculos**: "rodar agora", "pausar", "excluir", "+ agente", "ver todos", "usar outro e-mail". Botões de formulário são Title-ish com maiúscula inicial: "Criar autopilot", "Salvar".

**Emoji faz parte da voz** — como marcador de tipo, não como decoração: 🤖 sempre significa agente e 👤 sempre significa humano, no board, nos comentários e no chat.

**Números e datas:** datas curtas em `dd/MM HH:mm`, longas em `dd/MM/yyyy HH:mm`; custo com 4 casas (`$0.4213`); tokens com separador de milhar.

---

## VISUAL FOUNDATIONS

**Dark-only.** Não existe tema claro; `color-scheme: dark` é declarado globalmente e a paleta parte de `#0b0b0f`.

**Cor.** Quatro superfícies quase idênticas fazem toda a estratificação: `#0b0b0f` (body), `#0e0e13` (sidebar e topbar), `#111116` (cards), `#18181b`/`#09090b` (zinc-900/950, campos e painéis). O neutro é a escala **zinc** do Tailwind — exceto a tela de Chat, que usa **neutral**; é uma inconsistência real do produto, preservada aqui por fidelidade. O acento único é **violet**: `violet-600` em ações, `violet-500` em hover e foco, `violet-400` em links, seleção de texto em violet 35%. Semânticas nunca são sólidas: toda pill é fundo da cor com 15–35% de alpha + texto na variante clara.

**Tipografia.** Nenhuma webfont é carregada — a stack é a `font-sans` padrão do Tailwind (system-ui) e `ui-monospace` para chaves de issue, expressões cron e caminhos. Escala apertada: 10 · 11 · 12 · 14 · 18 · 20 · 24px. 14px é o corpo; 24px só em título de issue e números de métrica. Hierarquia é feita **por cor** (zinc-100 → zinc-600), não por tamanho.

**Espaçamento.** Grid de 4px, densidade alta: controles com `6px/12px`, cards com 16px, páginas com 24px. Larguras fixas: sidebar 224px, topbar 44px, coluna do board 288px, lista de chats 288px, sidebar da issue 260px, conteúdo 1024px, formulários 672px.

**Fundos.** Sólidos, sempre. Não há imagem, gradiente, textura, padrão repetido nem ilustração em lugar nenhum do produto.

**Profundidade.** **Zero `box-shadow`.** Separação é sempre borda de 1px (`zinc-800`, `zinc-800/70` no chrome, `zinc-800/50` em linhas de tabela) mais troca de superfície. Estado vazio usa borda **tracejada**.

**Cards.** Fundo `#111116` (dashboard/login) ou `zinc-900`/`zinc-900/60` (formulários, colunas, comentários), borda 1px zinc-800, raio 8px, padding 16px, sem sombra. Hover de card clicável clareia a borda para zinc-700/zinc-600 — nada mais.

**Raios.** 4px em tags, 6px no default (botões, inputs, itens de nav), 8px em cards e colunas, 12px só no card de login e nas bolhas de chat, pill em status e contadores.

**Hover.** Fundo um passo mais claro (`zinc-800/50` na nav, `zinc-800/40` em linhas de lista, `violet-500` no botão primário) ou texto um passo mais claro (`zinc-500 → zinc-200`; `violet-400 → violet-300`; `zinc-500 → red-400` em excluir). Nunca escurece.

**Press.** Não existe estado de press desenhado — sem shrink, sem transform, sem escala. O feedback é o resultado (swap do HTMX).

**Foco.** Só a borda muda de cor, para `violet-500`. Não há ring, glow nem outline.

**Animação.** Mínima e funcional: swaps do HTMX fazem fade de 120ms (`opacity 0 → 1`, ease-out/ease-in); durante a requisição o elemento vai a `opacity .6` e perde `pointer-events`; o indicador "agente digitando…" pulsa. Nada de bounce, spring ou entrada em cascata.

**Transparência e blur.** Transparência sim (alphas nas pills, bordas `/70`, superfícies `/60`), **blur nunca** — não há `backdrop-filter` no produto.

**Layout fixo.** Sidebar e topbar são fixas; só o `<main>` rola. O board rola horizontalmente. O body tem `overflow: hidden`.

**Imagens.** Não há nenhuma. Nem foto, nem avatar real — o "avatar" de agente é o emoji 🤖 num quadrado zinc-800. Se precisar de imagem em algum artefato novo, peça o asset em vez de inventar.

**Scrollbars** são customizadas: 8px, thumb `#2a2a33` (hover `#3a3a45`), track transparente.

---

## ICONOGRAPHY

**O repositório do Ryu não define nenhuma biblioteca de ícones** — a UI original usava emoji Unicode como substituto. Este design system faz a substituição consciente para **Lucide** (via CDN, `unpkg.com/lucide@latest`): ícones de linha, monocromáticos, herdando `currentColor` — sem preenchimento, sem cor própria, no espírito de assistentes de IA como o ChatGPT.

- **Nav da sidebar**: `inbox`, `message-circle`, `user`, `layout-grid`, `folder`, `zap`, `bot`, `users`, `bar-chart-2`, `puzzle`, `book-open`, `settings`.
- **Marcadores semânticos**: `bot` = agente, `user` = humano — em cards do board, comentários, chat, squads.
- **Ações**: `plus` (nova issue), `search`, `star` (fixar), `archive`, `arrow-left` (voltar), `moon`/`sun` (alternar tema).

O componente **Icon** (`components/core/Icon.jsx`) encapsula isso — passe o nome do Lucide e o tamanho; ele carrega o glifo via `window.lucide.createIcons()`. Qualquer página que use `Icon` precisa do script `<script src="https://unpkg.com/lucide@latest"></script>` antes da montagem.

**Logo:** o repositório **não contém arquivo de logo**. A marca é um quadrado `var(--accent)` (índigo) com a letra **R** em branco bold — 24px/raio 6px na sidebar, 40px/raio 16px no login — ao lado do nome do workspace. Nenhum logotipo foi desenhado neste design system, por princípio.

---

## Índice

**Raiz**
- `styles.css` — ponto de entrada; só `@import`s.
- `readme.md` — este guia. `SKILL.md` — versão Agent Skill. `github.md` — vínculo com o repositório de origem.
- `thumbnail.html` — tile do design system.

**`tokens/`** — `colors.css` (197 tokens: superfícies, zinc, neutral, violet, status, pills), `typography.css`, `spacing.css`, `radius.css`, `effects.css`, `motion.css`.

**`guidelines/`** — cards de fundação: Surfaces, Accent — violet, Neutros — zinc, Status de issue, Semânticas translúcidas, Escala, Famílias, Papéis de texto, Escala 4px, Medidas de layout, Raios, Profundidade, Movimento e estados, Marca, Iconografia.

**`components/`** — 24 exports em três grupos:
- `core/` — **Button**, **Input**, **Select**, **Textarea**, **Card**, **EmptyState**, **ThemeToggle**, **Icon**
- `data/` — **StatusDot**, **StatusPill**, **PriorityTag**, **CountBadge**, **IssueKey**, **DataTable**
- `app/` — **Sidebar** (+ **SidebarSection**), **NavItem**, **TopBar**, **IssueCard**, **BoardColumn**, **ChatBubble**, **InboxItem**, **StatCard**, **AgentCard**

Cada componente tem `.jsx`, `.d.ts` (contrato de props) e `.prompt.md` (quando e como usar).

**`ui_kits/ryu-app/`** — recriação clicável do workspace (login, dashboard, board, issue, chat, inbox, agents, usage). Veja o `README.md` de lá para o mapa tela ↔ template.

### Adições intencionais

- **EmptyState** e **DataTable** não existem como componentes no produto (HTMX + Jinja repetem o markup em cada template), mas o padrão é literalmente idêntico em 6+ telas — foram extraídos para evitar divergência.
- **PageHeader** vive no UI kit, não em `components/`, porque a variação entre telas ainda é grande demais para congelar um contrato.

### Lacunas conhecidas

- Sem arquivos de fonte (o produto usa a stack do sistema) e sem assets de imagem — nada foi substituído por aproximação.
- Telas não recriadas: Invite (aceitar convite) e Pinned items (seção fixada na sidebar).
