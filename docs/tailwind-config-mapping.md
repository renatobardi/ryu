# Mapeamento de tokens pro Tailwind/app.css

Resolução do ticket "Mapeamento de tokens pro Tailwind/app.css"
([#13](https://github.com/renatobardi/ryu/issues/13)) do mapa
[Implantação do novo Ryu Design System](https://github.com/renatobardi/ryu/issues/7).

**Isto é spec — nada aqui está aplicado.** `src/ryu/web/static/app.css`,
`base.html` e os templates seguem intocados; aplicar é execução, e a seção
[Checklist de execução](#checklist-de-execução) diz o que precisa entrar
junto pra não regredir nada.

A fonte é `docs/Ryu Design System/tokens/colors.css` — o vocabulário órfão
`--zinc-*`/`--violet-*`/`--ryu-*` é ignorado, por decisão do ticket
[#12](https://github.com/renatobardi/ryu/issues/12).

---

## 1. Custom properties (vão pro `app.css`)

Transcrição de `tokens/colors.css`: 117 propriedades no `:root` (claro,
padrão) e 101 no bloco escuro, conferidas uma a uma contra a origem.

Duas correções deliberadas de bugs do pacote (não corrigidos no pacote em
si, que segue out-of-scope por [#12](https://github.com/renatobardi/ryu/issues/12)):

- `--focus-ring` aponta pra `--border-focus`; no pacote aponta pro
  `--violet-500`, que não existe em tema nenhum.
- `--overlay-scrim` ganha valor claro (`rgb(0 0 0 / .4)`); o pacote só
  define o escuro.

Sobre `--card-shadow`: `tokens/effects.css` afirma "o produto NÃO usa
box-shadow", mas `tokens/colors.css` (v2, mais recente) define
`--card-shadow` com sombra real no claro e `none` no escuro. Vale o
`colors.css` — o `effects.css` está desatualizado, mesma defasagem já
registrada no `readme.md` do pacote.

```css
:root {
  color-scheme: light;

  /* ── Neutros quentes — claro (padrão) ─────────────────────────── */
  --gray-950: #0d0d0d; --gray-900: #1a1a1a; --gray-800: #2e2e2c; --gray-700: #454440; --gray-600: #5d5d5b;
  --gray-500: #767673; --gray-400: #8e8e8a; --gray-300: #c7c7c2; --gray-200: #e5e5e3; --gray-150: #ececea;
  --gray-100: #f4f4f2; --gray-50: #f9f9f8; --gray-0: #ffffff;

  /* ── Ciano — único acento ──────────────────────────────────────── */
  --indigo-700: #06718f; --indigo-600: #0891b2; --indigo-500: #22a8c9; --indigo-400: #5fc3dd; --indigo-100: #e0f4f8;

  /* ── Semânticas cruas (mesmas nos dois temas) ─────────────────── */
  --emerald-600: #059669; --emerald-500: #10b981; --emerald-400: #34d399;
  --green-500: #16a34a; --green-400: #22c55e;
  --red-600: #dc2626; --red-500: #ef4444; --red-400: #f87171;
  --amber-500: #d97706; --amber-400: #f59e0b;
  --yellow-500: #ca8a04; --yellow-400: #eab308;
  --orange-500: #ea580c; --orange-400: #f97316;
  --blue-500: #3b82f6; --blue-400: #60a5fa;

  /* ── Superfícies / bordas / texto / acento ─────────────────────── */
  --surface-app: var(--gray-0); --surface-chrome: var(--gray-50); --surface-card: var(--gray-0);
  --surface-raised: var(--gray-50); --surface-sunken: var(--gray-100); --surface-input: var(--gray-0);
  --surface-input-alt: var(--gray-50); --surface-column: var(--gray-50);
  --surface-hover: var(--gray-100); --surface-active: var(--gray-150);
  --border-default: var(--gray-200); --border-soft: var(--gray-200); --border-hairline: var(--gray-150);
  --border-strong: var(--gray-300); --border-hover: var(--gray-400); --border-focus: var(--indigo-600);
  --text-primary: var(--gray-950); --text-body: var(--gray-900); --text-secondary: var(--gray-700);
  --text-muted: var(--gray-600); --text-subtle: var(--gray-500); --text-faint: var(--gray-400);
  --text-accent: var(--indigo-600); --text-on-accent: #fff;
  --accent: var(--indigo-600); --accent-hover: var(--indigo-700); --accent-selection: rgb(8 145 178 / .18);
  --card-shadow: 0 1px 2px rgb(0 0 0 / .04);

  /* ── Status / pills ─────────────────────────────────────────────── */
  --status-backlog: var(--gray-400); --status-todo: var(--gray-600); --status-in-progress: var(--yellow-500);
  --status-in-review: var(--indigo-600); --status-done: var(--green-500); --status-blocked: var(--red-500);
  --status-cancelled: var(--gray-300);
  --agent-idle-bg: var(--gray-150); --agent-idle-fg: var(--gray-600);
  --agent-working-bg: rgb(217 119 6 / .12); --agent-working-fg: var(--amber-500);
  --agent-blocked-bg: rgb(239 68 68 / .12); --agent-blocked-fg: var(--red-500);
  --agent-error-bg: rgb(239 68 68 / .16); --agent-error-fg: var(--red-600);
  --agent-offline-bg: var(--gray-150); --agent-offline-fg: var(--gray-500);
  --task-queued-bg: var(--gray-150); --task-queued-fg: var(--gray-600);
  --task-dispatched-bg: rgb(59 130 246 / .12); --task-dispatched-fg: var(--blue-500);
  --task-running-bg: rgb(202 138 4 / .12); --task-running-fg: var(--yellow-500);
  --task-completed-bg: rgb(22 163 74 / .12); --task-completed-fg: var(--green-500);
  --task-failed-bg: rgb(239 68 68 / .12); --task-failed-fg: var(--red-500);
  --task-cancelled-bg: var(--gray-150); --task-cancelled-fg: var(--gray-500);
  --sev-action-required-bg: rgb(239 68 68 / .12); --sev-action-required-fg: var(--red-500);
  --sev-attention-bg: rgb(202 138 4 / .12); --sev-attention-fg: var(--yellow-500);
  --sev-info-bg: var(--gray-150); --sev-info-fg: var(--gray-600);
  --prio-urgent-bg: rgb(239 68 68 / .1); --prio-urgent-fg: var(--red-500);
  --prio-high-bg: rgb(234 88 12 / .1); --prio-high-fg: var(--orange-500);
  --prio-medium-bg: rgb(202 138 4 / .1); --prio-medium-fg: var(--yellow-500);
  --prio-low-bg: var(--gray-150); --prio-low-fg: var(--gray-500);
  --state-on-bg: rgb(5 150 105 / .12); --state-on-fg: var(--emerald-600);
  --state-off-bg: var(--gray-150); --state-off-fg: var(--gray-500);
  --danger-bg: rgb(239 68 68 / .12); --danger-fg: var(--red-500);
  --warning-bg: rgb(217 119 6 / .12); --warning-fg: var(--amber-500);
  --success-bg: rgb(5 150 105 / .12); --success-fg: var(--emerald-600);
  --scrollbar-thumb: var(--gray-300); --scrollbar-thumb-hover: var(--gray-400);
  --chat-bubble-agent-bg: var(--gray-100); --chat-bubble-agent-fg: var(--gray-900);
  --chat-bubble-system-bg: rgb(217 119 6 / .1); --chat-bubble-system-fg: var(--amber-500);
  --chat-list-bg: var(--gray-50); --chat-panel-bg: var(--gray-0);

  /* ── Tipografia (docs/Ryu Design System/tokens/typography.css) ─── */
  --font-sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
  --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  --text-2xs: 10px; --text-11: 11px; --tracking-code: .5em;
  /* text-xs/sm/base/lg/xl/2xl (12/14/16/18/20/24px) já batem 1:1 com o Tailwind
     padrão — use as classes nativas, sem custom property. Idem tracking-wide/
     wider (.025em/.05em) e os pesos (400/500/600/700 = font-normal/medium/
     semibold/bold nativos). */

  /* ── Layout (docs/Ryu Design System/tokens/spacing.css) ─────────── */
  --issue-sidebar-width: 260px;
  /* sidebar-width(224px)=w-56, chat-list-width/board-column-width(288px)=w-72,
     topbar-height(44px)=h-11, content-max(1024px)=max-w-5xl, form-max(672px)=
     max-w-2xl — todos já nativos do Tailwind, sem custom property. Só
     issue-sidebar-width (260px) não tem equivalente nativo. Escala 0-48
     (grid 4px) inteira já é a escala padrão do Tailwind (p-, m-, gap-, space-). */

  /* ── Raios (docs/Ryu Design System/tokens/radius.css) ───────────── */
  /* radius-sm/md/lg/xl/full (6/8/12/16/9999px) = rounded-md/lg/xl/2xl/full
     nativos do Tailwind — nomes diferentes, mesmo valor, sem custom property. */

  /* ── Efeitos (docs/Ryu Design System/tokens/effects.css) ────────── */
  --focus-ring: 0 0 0 1px var(--border-focus);
  --overlay-scrim: rgb(0 0 0 / .4);
  --divider: 1px solid var(--border-hairline);

  /* ── Movimento (docs/Ryu Design System/tokens/motion.css) ───────── */
  --duration-fast: 120ms; --opacity-loading: .6;
  /* ease-out/ease-in já são os nativos do Tailwind (cubic-bezier
     idêntico); duration-150 também é nativo — só duration-fast (120ms) não tem
     classe padrão. */
}

[data-theme="dark"] {
  color-scheme: dark;

  --gray-950: #f5f5f4; --gray-900: #ececea; --gray-800: #d4d4d1; --gray-700: #a8a8a4; --gray-600: #8e8e8a;
  --gray-500: #767673; --gray-400: #5d5d5b; --gray-300: #454440; --gray-200: #333331; --gray-150: #2a2a28;
  --gray-100: #212121; --gray-50: #171717; --gray-0: #131313;

  --indigo-700: #7ddaf0; --indigo-600: #5fc3dd; --indigo-500: #22a8c9; --indigo-400: #0891b2; --indigo-100: rgb(95 195 221 / .18);

  --surface-app: var(--gray-0); --surface-chrome: var(--gray-50); --surface-card: var(--gray-100);
  --surface-raised: var(--gray-100); --surface-sunken: var(--gray-50); --surface-input: var(--gray-100);
  --surface-input-alt: var(--gray-50); --surface-column: var(--gray-100);
  --surface-hover: var(--gray-150); --surface-active: var(--gray-200);
  --border-default: var(--gray-200); --border-soft: var(--gray-200); --border-hairline: var(--gray-150);
  --border-strong: var(--gray-300); --border-hover: var(--gray-400); --border-focus: var(--indigo-600);
  --text-primary: var(--gray-950); --text-body: var(--gray-900); --text-secondary: var(--gray-800);
  --text-muted: var(--gray-700); --text-subtle: var(--gray-600); --text-faint: var(--gray-500);
  --text-accent: var(--indigo-600); --text-on-accent: #0d0d0d;
  --accent: var(--indigo-600); --accent-hover: var(--indigo-700); --accent-selection: rgb(95 195 221 / .28);
  --card-shadow: none;

  --status-backlog: var(--gray-500); --status-todo: var(--gray-700); --status-in-progress: #eab308;
  --status-in-review: var(--indigo-600); --status-done: #22c55e; --status-blocked: #ef4444;
  --status-cancelled: var(--gray-300);
  --agent-idle-bg: var(--gray-150); --agent-idle-fg: var(--gray-700);
  --agent-working-bg: rgb(245 158 11 / .16); --agent-working-fg: #fbbf24;
  --agent-blocked-bg: rgb(239 68 68 / .18); --agent-blocked-fg: #f87171;
  --agent-error-bg: rgb(239 68 68 / .22); --agent-error-fg: #fca5a5;
  --agent-offline-bg: var(--gray-150); --agent-offline-fg: var(--gray-600);
  --task-queued-bg: var(--gray-150); --task-queued-fg: var(--gray-700);
  --task-dispatched-bg: rgb(59 130 246 / .16); --task-dispatched-fg: #93c5fd;
  --task-running-bg: rgb(234 179 8 / .16); --task-running-fg: #facc15;
  --task-completed-bg: rgb(34 197 94 / .16); --task-completed-fg: #4ade80;
  --task-failed-bg: rgb(239 68 68 / .18); --task-failed-fg: #f87171;
  --task-cancelled-bg: var(--gray-150); --task-cancelled-fg: var(--gray-600);
  --sev-action-required-bg: rgb(239 68 68 / .16); --sev-action-required-fg: #f87171;
  --sev-attention-bg: rgb(234 179 8 / .16); --sev-attention-fg: #facc15;
  --sev-info-bg: var(--gray-150); --sev-info-fg: var(--gray-700);
  --prio-urgent-bg: rgb(239 68 68 / .15); --prio-urgent-fg: #f87171;
  --prio-high-bg: rgb(249 115 22 / .15); --prio-high-fg: #fb923c;
  --prio-medium-bg: rgb(234 179 8 / .15); --prio-medium-fg: #facc15;
  --prio-low-bg: var(--gray-150); --prio-low-fg: var(--gray-600);
  --state-on-bg: rgb(5 150 105 / .2); --state-on-fg: #34d399;
  --state-off-bg: var(--gray-150); --state-off-fg: var(--gray-600);
  --danger-bg: rgb(239 68 68 / .18); --danger-fg: #f87171;
  --warning-bg: rgb(245 158 11 / .16); --warning-fg: #fbbf24;
  --success-bg: rgb(5 150 105 / .2); --success-fg: #34d399;
  --scrollbar-thumb: var(--gray-300); --scrollbar-thumb-hover: var(--gray-400);
  --chat-bubble-agent-bg: var(--gray-100); --chat-bubble-agent-fg: var(--gray-900);
  --chat-bubble-system-bg: rgb(245 158 11 / .14); --chat-bubble-system-fg: #fbbf24;
  --chat-list-bg: var(--gray-50); --chat-panel-bg: var(--gray-0);

  --focus-ring: 0 0 0 1px var(--border-focus);
  --overlay-scrim: rgb(11 11 15 / .8);
  --divider: 1px solid var(--border-hairline);
}
```

---

## 2. `tailwind.config` (vai pro `base.html`)

Expõe **só a camada semântica**. `gray-*` e `indigo-*` crus ficam de fora
de propósito: o número neles é papel, não tom — `--gray-950` é quase-preto
no claro e quase-branco no escuro —, e `indigo` renderiza ciano. Expor isso
como cor Tailwind convidaria ao erro.

Cada cor aponta pra `var()`. Como o valor da variável é que muda com
`[data-theme="dark"]`, **a mesma classe serve aos dois temas** — não existe
`dark:` no código de tela. `darkMode` fica declarado só pros casos em que
uma tela precise divergir de propósito.

```js
tailwind.config = {
  darkMode: ['selector', '[data-theme="dark"]'],
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

        'danger-bg': 'var(--danger-bg)', 'danger-fg': 'var(--danger-fg)',
        'warning-bg': 'var(--warning-bg)', 'warning-fg': 'var(--warning-fg)',
        'success-bg': 'var(--success-bg)', 'success-fg': 'var(--success-fg)',

        'chat-bubble-agent-bg': 'var(--chat-bubble-agent-bg)', 'chat-bubble-agent-fg': 'var(--chat-bubble-agent-fg)',
        'chat-bubble-system-bg': 'var(--chat-bubble-system-bg)', 'chat-bubble-system-fg': 'var(--chat-bubble-system-fg)',
        'chat-list-bg': 'var(--chat-list-bg)', 'chat-panel-bg': 'var(--chat-panel-bg)',
      },
      fontSize: {
        '2xs': ['var(--text-2xs)', { lineHeight: '1.4' }],
        '11': ['var(--text-11)', { lineHeight: '1.4' }],
      },
      letterSpacing: { code: 'var(--tracking-code)' },
      transitionDuration: { '120': 'var(--duration-fast)' },
      spacing: { 'issue-sidebar': 'var(--issue-sidebar-width)' },
      boxShadow: { card: 'var(--card-shadow)' },
    },
  },
};
```

São **seis** entradas de extensão além das cores: os cinco valores que a
escala nativa do Tailwind não cobre (10px, 11px, `.5em`, 120ms, 260px) mais
`boxShadow.card`, que existe porque `colors.css` define `--card-shadow` por
tema.

Não há `ringColor`: o DS troca **só a cor da borda** no foco, sem ring
(`readme.md`, "Foco"). Use `focus:border-border-focus`. O `--focus-ring` do
pacote é 1px, e o `ring` default do Tailwind é 3px — registrá-lo como
ringColor renderizaria a espessura errada.

---

## 3. Equivalências sem extensão de config

Estes tokens do DS já batem valor a valor com a escala nativa do Tailwind —
use a classe nativa e não declare nada.

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
| `--text-xs`…`--text-2xl` | 12/14/16/18/20/24px | `text-xs`/`sm`/`base`/`lg`/`xl`/`2xl` |
| `--leading-none` / `--leading-snug` / `--leading-normal` | 1 / 1.375 / 1.5 | `leading-none` / `leading-snug` / `leading-normal` |
| `--tracking-wide` / `--tracking-wider` | .025em / .05em | `tracking-wide` / `tracking-wider` |
| `--weight-normal`…`--weight-bold` | 400-700 | `font-normal`/`medium`/`semibold`/`bold` |
| `--font-sans` / `--font-mono` | stack do sistema | `font-sans` / `font-mono` |
| `--duration-base` | 150ms | `duration-150` |
| `--ease-out` / `--ease-in` | cubic-bezier idêntico | `ease-out` / `ease-in` |
| `--opacity-loading` | .6 | `opacity-60` |
| `--animate-pulse` | pulse 2s | `animate-pulse` (+ `@keyframes` nativo) |
| `--border-width` | 1px | `border` |
| `--shadow-none` | none | `shadow-none` |
| escala de espaçamento 0-48 | grid 4px | `p-*`/`m-*`/`gap-*`/`space-*` |

Os papéis compostos de `typography.css` (`--type-page-title`, `--type-body`,
`--type-pill`, `--type-key`, …) são atalhos da shorthand `font:` e não têm
equivalente de classe única: em template, some as classes correspondentes
(ex. `--type-pill` = `text-2xs font-medium leading-snug`).

Sem equivalente e **sem classe** — use direto na folha de estilo, não em
template: `--overlay-scrim` (fundo de modal), `--divider` (atalho de
`border`), `--focus-ring` (documental, o foco real é
`focus:border-border-focus`) e `--elevation-strategy` (puramente
documental).

---

## 4. Regras de uso

**Nunca interpole valor de backend em nome de classe.** Os enums vêm com
underscore (`in_progress`, `action_required`) e os tokens são hifenizados
(`--status-in-progress`), então `bg-status-{{ issue.status }}` gera
`bg-status-in_progress`, que não existe — a classe some sem erro. A cor sai
sempre de um mapa explícito dentro de um macro, como
`_components/data/status_pill.html` já faz. Status de issue precisará do
macro equivalente ao `StatusDot` do DS.

**Erro, aviso e sucesso têm token próprio.** `danger`, `warning` e `success`
(pares `*-bg`/`*-fg`) cobrem mensagem de erro, alerta e confirmação. Não use
`red-*`/`amber-*`/`emerald-*` nativos do Tailwind para isso: eles são fixos, e
os tokens são calibrados por tema — um `bg-emerald-600/20` que funciona no
escuro fica lavado no claro.

**Não aplique opacidade Tailwind sobre esses tokens.** `bg-x/15` só funciona
em cor declarada como função `rgb(<alpha-value> …)`; as nossas são `var()`
simples. As pills translúcidas já vêm com alpha embutido nos pares
`*-bg`/`*-fg` — use o par, não o modificador.

```html
<div class="bg-surface-card border border-border-default rounded-lg p-4">
  <span class="text-text-primary text-sm">...</span>
  <!-- bolinha de status: token sólido -->
  <span class="inline-block w-2 h-2 rounded-full bg-status-done"></span>
  <!-- pill: par -bg/-fg, alpha já no token -->
  <span class="bg-agent-working-bg text-agent-working-fg rounded-full px-2 py-0.5 text-2xs">working</span>
</div>
```

---

## Checklist de execução

Nada disto está feito. Os quatro itens precisam entrar **juntos** — cada um
sozinho regride a UI:

1. **`app.css`**: acrescentar o bloco da seção 1. As 21 classes
   `.ryu-status-*` (7), `.ryu-agent-*` (5), `.ryu-task-*` (6) e `.ryu-sev-*`
   (3) ficam obsoletas, mas **só podem sair depois do item 3** — hoje ainda
   há chamador.
2. **`base.html`**: trocar `<html class="dark">` por `<html data-theme="…">`
   lido do cookie `ryu_theme` ([#10](https://github.com/renatobardi/ryu/issues/10))
   e colar o `tailwind.config` da seção 2. Sem isto o `:root` claro passa a
   valer sob um shell escuro hardcoded — a scrollbar, por exemplo, viraria
   `#c7c7c2` sobre `#0b0b0f`.
3. **Migrar os chamadores das classes antigas**: `dashboard.html:30` (dot de
   status), `:53` (pill de agente), `:86` (pill de task), e
   `agents/index.html:42` (pill de agente), `:68` (pill de task) — via macro
   com mapa explícito, conforme a seção 4. `.ryu-sev-*` não tem chamador e
   pode sair direto.
4. **Migrar as telas** que hoje carregam cor crua (`bg-[#0b0b0f]`,
   `text-zinc-*`, `border-zinc-*`) pras classes semânticas. Enquanto isso
   não terminar, o tema claro não fica de pé: `data-theme` deve ficar fixo
   em `dark` até a última tela migrar.
