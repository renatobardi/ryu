# Convenção de tradução JSX → Jinja

Resolução do ticket "Convenção de tradução JSX → Jinja" do mapa
"Implantação do novo Ryu Design System". Estes arquivos são **exemplos-prova
da mecânica**, não produção — nenhum é importado por `base.html` ou por
qualquer template real. A aplicação nas 28 telas é execução, fora do mapa.

## Convenção

- **Local**: `src/ryu/web/templates/_components/{core,data,app}/<nome>.html`
  — exceção explícita à regra 2 do CONTRACTS.md (cross-cutting, como `base.html`).
- **Uma macro por arquivo**, nome do arquivo = nome da macro em snake_case.
- **Estilo**: classes Tailwind, não `style` inline com `var(--token)` — usa
  `hover:`/`dark:` nativos do Tailwind em vez de JS simulando `:hover`.
- **Children/slot único** (JSX `children`) → `{% call %}` (Jinja só suporta
  um caller por macro, o que já bate 1:1).
- **Props extras/handlers** (JSX `onClick`, `...rest`) → parâmetro `attrs={}`,
  despejado como atributos HTML (`hx-*`, `href`, `onclick`, etc.).
- **Doc por componente**: comentário Jinja `{# ... #}` no topo do arquivo,
  só pra regras não-óbvias (ex: "status é sempre cru, sem tradução") — sem
  arquivo `.md` paralelo por componente.
- **Regra geral pra desvios de conteúdo**: onde o codebase atual diverge do
  que o DS documenta, o DS vence — correção fica pro ticket de migração da
  tela específica (execução).

## Uso

```jinja
{% from "_components/core/button.html" import button %}
{% from "_components/data/status_pill.html" import status_pill %}
{% from "_components/app/sidebar.html" import sidebar %}

{% call button(variant='primary', full=True, attrs={'hx-get': '/w/' ~ workspace.slug ~ '/board/new-issue', 'hx-target': '#modal'}) %}
  ＋ New Issue
{% endcall %}

{{ status_pill(kind='state', status=issue.status) }}

{% call sidebar(workspace, user) %}
  {{ nav_item('board', 'Board', url_for('board'), 'layout-grid') }}
{% endcall %}
```
