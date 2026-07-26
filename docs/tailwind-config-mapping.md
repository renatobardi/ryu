# Mapeamento de tokens pro `tailwind.config` (base.html)

Resolução do ticket "Mapeamento de tokens pro Tailwind/app.css" do mapa
"Implantação do novo Ryu Design System". Isto é spec — não foi aplicado em
`base.html` real (owner é "o agente de UI" por CONTRACTS.md regra 7; aplicar
é execução, fora deste mapa).

`app.css` (neste branch) já tem os custom properties. Abaixo, a extensão de
`tailwind.config` que os expõe como classes Tailwind — só a camada semântica
(ver ticket, opção "só semântica"), nunca `gray-*`/`indigo-*` cru.

```js
tailwind.config = {
  darkMode: ['selector', '[data-theme="dark"]'], // decidido em "Persistência de tema"
  theme: {
    extend: {
      colors: {
        'surface-app': 'var(--surface-app)',
        'surface-chrome': 'var(--surface-chrome)',
        'surface-card': 'var(--surface-card)',
        'surface-raised': 'var(--surface-raised)',
        'surface-sunken': 'var(--surface-sunken)',
        'surface-input': 'var(--surface-input)',
        'surface-input-alt': 'var(--surface-input-alt)',
        'surface-column': 'var(--surface-column)',
        'surface-hover': 'var(--surface-hover)',
        'surface-active': 'var(--surface-active)',

        'border-default': 'var(--border-default)',
        'border-soft': 'var(--border-soft)',
        'border-hairline': 'var(--border-hairline)',
        'border-strong': 'var(--border-strong)',
        'border-hover': 'var(--border-hover)',
        'border-focus': 'var(--border-focus)',

        'text-primary': 'var(--text-primary)',
        'text-body': 'var(--text-body)',
        'text-secondary': 'var(--text-secondary)',
        'text-muted': 'var(--text-muted)',
        'text-subtle': 'var(--text-subtle)',
        'text-faint': 'var(--text-faint)',
        'text-accent': 'var(--text-accent)',
        'text-on-accent': 'var(--text-on-accent)',

        accent: { DEFAULT: 'var(--accent)', hover: 'var(--accent-hover)' },

        'status-backlog': 'var(--status-backlog)',
        'status-todo': 'var(--status-todo)',
        'status-in-progress': 'var(--status-in-progress)',
        'status-in-review': 'var(--status-in-review)',
        'status-done': 'var(--status-done)',
        'status-blocked': 'var(--status-blocked)',
        'status-cancelled': 'var(--status-cancelled)',

        'agent-idle-bg': 'var(--agent-idle-bg)', 'agent-idle-fg': 'var(--agent-idle-fg)',
        'agent-working-bg': 'var(--agent-working-bg)', 'agent-working-fg': 'var(--agent-working-fg)',
        'agent-blocked-bg': 'var(--agent-blocked-bg)', 'agent-blocked-fg': 'var(--agent-blocked-fg)',
        'agent-error-bg': 'var(--agent-error-bg)', 'agent-error-fg': 'var(--agent-error-fg)',
        'agent-offline-bg': 'var(--agent-offline-bg)', 'agent-offline-fg': 'var(--agent-offline-fg)',

        'task-queued-bg': 'var(--task-queued-bg)', 'task-queued-fg': 'var(--task-queued-fg)',
        'task-dispatched-bg': 'var(--task-dispatched-bg)', 'task-dispatched-fg': 'var(--task-dispatched-fg)',
        'task-running-bg': 'var(--task-running-bg)', 'task-running-fg': 'var(--task-running-fg)',
        'task-completed-bg': 'var(--task-completed-bg)', 'task-completed-fg': 'var(--task-completed-fg)',
        'task-failed-bg': 'var(--task-failed-bg)', 'task-failed-fg': 'var(--task-failed-fg)',
        'task-cancelled-bg': 'var(--task-cancelled-bg)', 'task-cancelled-fg': 'var(--task-cancelled-fg)',

        'sev-action-required-bg': 'var(--sev-action-required-bg)', 'sev-action-required-fg': 'var(--sev-action-required-fg)',
        'sev-attention-bg': 'var(--sev-attention-bg)', 'sev-attention-fg': 'var(--sev-attention-fg)',
        'sev-info-bg': 'var(--sev-info-bg)', 'sev-info-fg': 'var(--sev-info-fg)',

        'prio-urgent-bg': 'var(--prio-urgent-bg)', 'prio-urgent-fg': 'var(--prio-urgent-fg)',
        'prio-high-bg': 'var(--prio-high-bg)', 'prio-high-fg': 'var(--prio-high-fg)',
        'prio-medium-bg': 'var(--prio-medium-bg)', 'prio-medium-fg': 'var(--prio-medium-fg)',
        'prio-low-bg': 'var(--prio-low-bg)', 'prio-low-fg': 'var(--prio-low-fg)',

        'state-on-bg': 'var(--state-on-bg)', 'state-on-fg': 'var(--state-on-fg)',
        'state-off-bg': 'var(--state-off-bg)', 'state-off-fg': 'var(--state-off-fg)',

        'chat-bubble-agent-bg': 'var(--chat-bubble-agent-bg)', 'chat-bubble-agent-fg': 'var(--chat-bubble-agent-fg)',
        'chat-bubble-system-bg': 'var(--chat-bubble-system-bg)', 'chat-bubble-system-fg': 'var(--chat-bubble-system-fg)',
        'chat-list-bg': 'var(--chat-list-bg)', 'chat-panel-bg': 'var(--chat-panel-bg)',
      },
      fontSize: {
        '2xs': ['10px', { lineHeight: '1.4' }],
        '11': ['11px', { lineHeight: '1.4' }],
      },
      letterSpacing: {
        code: '.5em',
      },
      transitionDuration: {
        '120': '120ms',
      },
      spacing: {
        'issue-sidebar': '260px',
      },
      boxShadow: {
        card: 'var(--card-shadow)',
      },
      ringColor: {
        focus: 'var(--border-focus)',
      },
    },
  },
};
```

## Equivalências sem extensão de config (usar classes Tailwind nativas)

| Token DS | Valor | Classe Tailwind |
|---|---|---|
| `--radius-sm` | 6px | `rounded-md` |
| `--radius-md` | 8px | `rounded-lg` |
| `--radius-lg` | 12px | `rounded-xl` |
| `--radius-xl` | 16px | `rounded-2xl` |
| `--radius-full` | 9999px | `rounded-full` |
| `--sidebar-width` | 224px | `w-56` |
| `--chat-list-width` / `--board-column-width` | 288px | `w-72` |
| `--topbar-height` | 44px | `h-11` |
| `--content-max` | 1024px | `max-w-5xl` |
| `--form-max` | 672px | `max-w-2xl` |
| `--text-xs`..`--text-2xl` | 12/14/16/18/20/24px | `text-xs`/`sm`/`base`/`lg`/`xl`/`2xl` |
| `--tracking-wide` / `--tracking-wider` | .025em / .05em | `tracking-wide` / `tracking-wider` |
| `--weight-normal`..`--weight-bold` | 400-700 | `font-normal`/`medium`/`semibold`/`bold` |
| `--duration-base` | 150ms | `duration-150` |
| `--ease-out` / `--ease-in` | cubic-bezier nativo | `ease-out` / `ease-in` |
| escala de espaçamento 0-48 | grid 4px | `p-*`/`m-*`/`gap-*`/`space-*` nativos |

## Uso

Templates usam classes Tailwind semânticas direto, nunca `style` inline nem
`gray-500`/`indigo-600` cru. **Cuidado:** o modificador de opacidade do
Tailwind (`bg-x/15`) só funciona em cores registradas como função
`rgb(<alpha-value>)` — nossas cores são `var(--token)` simples, então
`bg-status-done/15` **não teria efeito**. Pra pill com fundo translúcido, use
o par de tokens já pré-computado (`*-bg`/`*-fg`, ex. `agent-working-bg`), não
tente aplicar opacidade a um token sólido:

```html
<div class="bg-surface-card border border-border-default rounded-lg p-4">
  <span class="text-text-primary text-sm">...</span>
  <!-- bolinha de status: token sólido, sem par -bg/-fg -->
  <span class="inline-block w-2 h-2 rounded-full bg-status-done"></span>
  <!-- pill: usa o par -bg/-fg, já translúcido no token -->
  <span class="bg-agent-working-bg text-agent-working-fg rounded-full px-2 py-0.5 text-2xs">working</span>
</div>
```
