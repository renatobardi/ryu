# Convenção de tradução JSX → Jinja

Resolução do ticket "Convenção de tradução JSX → Jinja" do mapa
"Implantação do novo Ryu Design System". Estes arquivos são **exemplos-prova
da mecânica**, não produção — nenhum é importado por `base.html` ou por
qualquer template real. A aplicação nas 28 telas é execução, fora do mapa.

As classes de cor usadas aqui (`bg-surface-*`, `text-text-*`, `bg-accent`,
`bg-agent-*-bg`, ...) são as semânticas definidas em `app.css` e registradas
no `tailwind.config` — ver `docs/tailwind-config-mapping.md`. Elas só existem
depois que aquele mapeamento entrar no `base.html`, o que também é execução.

## Convenção

- **Local**: `src/ryu/web/templates/_components/{core,data,app}/<nome>.html`
  — exceção explícita à regra 2 do CONTRACTS.md (cross-cutting, como `base.html`).
- **Uma macro por arquivo**, nome do arquivo = nome da macro em snake_case.
  Um `.jsx` com N exports vira N arquivos (ex. `Sidebar.jsx` → `sidebar.html`
  + `sidebar_section.html`).
- **Estilo**: classes Tailwind semânticas, não `style` inline com
  `var(--token)`. Isso dá `hover:` nativo, dispensando o
  `onMouseEnter`/`onMouseLeave` que o JSX usa pra simular `:hover`. O tema
  **não** usa o prefixo `dark:`: `data-theme` no `<html>` troca o valor da
  variável, então a mesma classe já serve aos dois temas (ticket
  "Persistência de tema").
- **Children/slot único** (JSX `children`) → `{% call %}` (Jinja só suporta
  um caller por macro, o que já bate 1:1). Quando o slot é opcional, o macro
  testa `caller is defined` e cai num default.
- **Props extras/handlers** (JSX `onClick`, `onSearch`, `...rest`) → parâmetro
  de dict despejado como atributos HTML (`hx-*`, `href`, ...). Um único slot
  de passthrough chama-se `attrs`; havendo mais de um alvo, o nome diz qual
  (`search_attrs`, `profile_attrs`).
- **Doc por componente**: comentário Jinja `{# ... #}` no topo do arquivo,
  só pra regras não-óbvias — sem arquivo `.md` paralelo por componente.
- **Regra geral pra desvios de conteúdo**: onde o codebase atual diverge do
  que o DS documenta, o DS vence — correção fica pro ticket de migração da
  tela específica (execução).
- **Lacuna de backend vira comentário, não gambiarra**: se o DS pede um campo
  que o modelo não tem (ex. `user.nickname`/`user.avatar`), o macro degrada
  pro que existe e registra o gap no comentário — `models.py` não se edita
  (CONTRACTS.md regra 1).

## Uso

```jinja
{% from "_components/core/button.html" import button %}
{% from "_components/data/status_pill.html" import status_pill %}
{% from "_components/app/sidebar.html" import sidebar %}
{% from "_components/app/sidebar_section.html" import sidebar_section %}

{% call button(variant='primary', size='sm', attrs={
     'hx-get': '/w/' ~ workspace.slug ~ '/issues/new',
     'hx-target': '#modal',
   }) %}Criar issue{% endcall %}

{# rótulo padrão = valor cru do backend #}
{{ status_pill(kind='task', status=task.status) }}

{# slot sobrepõe o rótulo quando o valor cru não é apresentável #}
{% call status_pill(kind='state', status='on' if autopilot.enabled else 'off') %}
  {{ 'ativo' if autopilot.enabled else 'pausado' }}
{% endcall %}

{% call sidebar(user=user, profile_attrs={'hx-get': '/w/' ~ workspace.slug ~ '/profile'}) %}
  <a href="/w/{{ workspace.slug }}/inbox"
     class="flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs text-text-muted hover:bg-surface-hover hover:text-text-body">
    <i data-lucide="inbox" class="w-4 h-4"></i> Inbox
  </a>
  {% call sidebar_section() %}Workspace{% endcall %}
  <a href="/w/{{ workspace.slug }}/board"
     class="flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs text-text-muted hover:bg-surface-hover hover:text-text-body">
    <i data-lucide="layout-grid" class="w-4 h-4"></i> Issues
  </a>
{% endcall %}
```
