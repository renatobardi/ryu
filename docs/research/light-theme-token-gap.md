# Levantamento de tokens de tema claro — `docs/Ryu Design System/`

Todos os caminhos abaixo são relativos a `docs/Ryu Design System/`.

## Resposta direta

**O pacote define, sim, valores concretos de tema claro** — mas apenas para o
conjunto de tokens que vive em `tokens/colors.css` (superfícies, escala
`gray-*`, acento `indigo-*`/ciano, status de issue, pills de agent/task/sev/
prio/state, scrollbar, chat). Esse arquivo já é claro-por-padrão
(`:root`) com escuro como override (`[data-theme="dark"]`), e cada token do
`:root` tem contraparte redefinida no bloco dark — não há assimetria dentro
desse arquivo.

O problema real não é "falta claro, só tem escuro". É que **existe um segundo
vocabulário de tokens** (`--zinc-*`, `--violet-*`, `--ryu-base/sidebar/panel/
edge`) usado por `readme.md`, por 4 dos 5 `guidelines/colors-*.card.html`,
por `thumbnail.html`, por `tokens/effects.css` e por 4 componentes `.jsx` —
e esse vocabulário **não está definido em lugar nenhum do pacote, nem claro
nem escuro**. É um resíduo de uma versão anterior do design system (dark-only,
zinc/violet) que não foi atualizado quando `tokens/colors.css` foi reescrito
para a v2 (claro+escuro, gray/ciano). As duas versões coexistem sem se
referenciar uma à outra.

## Verificação: definições, não só usos

A busca inicial por `--zinc-`, `--violet-`, `--ryu-` cobria só `tokens/` e
`styles.css`. Refiz a busca por **definições** (`nome:valor`, não `var(nome)`)
em todo o pacote, incluindo `_ds_bundle.js` (que poderia conter uma cópia
compilada de uma versão anterior de `colors.css`):

```
$ grep -rn -- '--zinc-[0-9]*:\|--violet-[0-9]*:\|--ryu-[a-z]*:' "docs/Ryu Design System/"
(nenhum resultado)
$ grep -o '"name":"--\(zinc\|violet\|ryu\)[^"]*"' "docs/Ryu Design System/_ds_manifest.json"
(nenhum resultado)
$ grep -in "zinc\|violet\|ryu-base\|ryu-sidebar\|ryu-panel\|ryu-edge" "docs/Ryu Design System/_adherence.oxlintrc.json"
(nenhum resultado)
```

Confirmado: `--zinc-*`, `--violet-*` e `--ryu-base/sidebar/panel/edge` não
têm definição em nenhum arquivo do pacote — nem em `_ds_bundle.js`, nem no
manifest de tokens gerado pela ferramenta, nem na config de lint de
aderência. São referências soltas.

## Evidência: `tokens/colors.css` já tem claro completo

- `tokens/colors.css:1-2` — comentário do próprio arquivo: "Ryu v2 — cor.
  Reskin claro/escuro estilo 'assistente de IA' ... Claro é o padrão; escuro
  via `[data-theme="dark"]`."
- `tokens/colors.css:3` — `:root{color-scheme:light;` — bloco claro é o
  `:root`, sem seletor de tema.
- `tokens/colors.css:6-105` — as 117 custom properties de cor do bloco
  `:root` (gray 0-950, indigo 100-700, semânticas cruas, superfícies,
  bordas, texto, accent, status de issue, pills de agent/task/severidade/
  prioridade/estado, scrollbar, chat) têm valor concreto.
- `tokens/colors.css:108-188` — bloco `[data-theme="dark"]{color-scheme:dark;`
  redefine 101 dessas properties com valores escuros. Extraí os nomes de
  ambos os blocos (`awk`+`grep`+`sort` linha a linha) e comparei com `comm`:
  a diferença (117 − 101 = 16) é exatamente `--emerald-600/500/400`,
  `--green-500/400`, `--red-600/500/400`, `--amber-500/400`,
  `--yellow-500/400`, `--orange-500/400`, `--blue-500/400` — as semânticas
  cruas de `tokens/colors.css:14-20`, que o comentário em
  `tokens/colors.css:13` já diz serem "mesmas nos dois temas". Não há
  nenhuma property do `:root` sem contraparte dark além dessas 16
  intencionais, e nenhuma property existe só no bloco dark.
- `docs/Ryu Design System/_ds_manifest.json` (catálogo gerado pela própria
  ferramenta) lista cada token de `tokens/colors.css` duas vezes — uma sem
  `"scope"` (= claro, do `:root`) e uma com `"scope":"[data-theme=\"dark\"]"`
  — confirmando que todo token de `colors.css` tem as duas variantes.
  Exemplo: `--surface-app` aparece com `"value":"var(--gray-0)"` sem scope
  (claro) e de novo com o mesmo valor mas `--gray-0` resolvendo diferente
  por tema.
- `Cyan Theme Check.html:11-16` — demo lado a lado hardcoda valores de claro
  (`background:#fff`, `border:1px solid #e5e5e3`, botão `background:#0891b2`,
  link `color:#0891b2`, pill `background:rgba(8,145,178,.12)` `color:#0891b2`)
  que batem exatamente com os tokens claros de `tokens/colors.css`
  (`--gray-0:#ffffff` linha 8, `--gray-200:#e5e5e3` linha 7, `--indigo-600:
  #0891b2` linha 11). Corrobora que o claro documentado ali é o mesmo de
  `colors.css`, não um terceiro esquema.
- `ui_kits/ryu-app/App.jsx:44-45` (idêntico em `templates/ryu-app/App.jsx:
  44-45`) — o toggle real só faz
  `document.documentElement.setAttribute('data-theme','dark')` ou remove o
  atributo; sem atributo cai no `:root` (claro). Confirma que `colors.css` é
  a fonte de verdade ativa do produto, não um arquivo órfão.
- `components/core/ThemeToggle.jsx:4` — `theme = 'light'` é o default do
  componente, consistente com "claro é o padrão" do comentário em
  `tokens/colors.css:1-2`.
- `Blue Options.html:6,11-16` — outro mock de exploração de accent (paridade
  com `Cyan Theme Check.html`), com frame `background:#fff`/
  `border:1px solid #e5e5e3` (claro) hardcoded, comparando 6 candidatos de
  cor de accent sobre fundo claro; a opção 6 (`#0891b2`, "ciano-azulado",
  linha 16) é exatamente o `--indigo-600` claro definido em
  `tokens/colors.css:11`. Corrobora que o accent ciano de `colors.css` veio
  desse exercício de exploração, não é acidente.

## O que está de fato quebrado/faltando: tokens `zinc-*`/`violet-*`/`ryu-*` indefinidos (em qualquer tema)

Busquei `--zinc-`, `--violet-` e `--ryu-` em todo `tokens/*.css` e
`styles.css` — nenhuma dessas properties é declarada:

```
$ grep -rn -- "--zinc-\|--violet-\|--ryu-base\|--ryu-sidebar\|--ryu-panel\|--ryu-edge" tokens/ styles.css
(nenhum resultado)
```

`docs/Ryu Design System/_ds_manifest.json` (campo `"tokens"`, gerado pela
própria ferramenta de bundling do pacote) também não lista nenhum
`--zinc-*`, `--violet-*` ou `--ryu-*` entre os tokens definidos — só
`gray-*`, `indigo-*`, `emerald/green/red/amber/yellow/orange/blue`,
`surface-*`, `border-*`, `text-*`, `status-*`, `agent-*`, `task-*`, `sev-*`,
`prio-*`, `state-*`, `scrollbar-*`, `chat-*` (de `colors.css`) mais os
tokens de `typography.css`, `spacing.css`, `radius.css`, `effects.css`,
`motion.css`.

Tokens ausentes, precisos:

- `--zinc-950`, `--zinc-900`, `--zinc-800`, `--zinc-700`, `--zinc-600`,
  `--zinc-500`, `--zinc-400`, `--zinc-300`, `--zinc-200`, `--zinc-100`
- `--violet-600`, `--violet-500`, `--violet-400`, `--violet-300`
- `--ryu-base`, `--ryu-sidebar`, `--ryu-panel`, `--ryu-edge`

Onde são referenciados (todos indefinidos, não é "falta variante clara" —
falta o token inteiro):

- `guidelines/colors-surfaces.card.html:6` — `var(--ryu-base)`,
  `var(--ryu-sidebar)`, `var(--ryu-panel)`, `var(--zinc-900)`,
  `var(--zinc-950)`, `var(--ryu-edge)`.
- `guidelines/colors-neutrals.card.html:6` — escala inteira
  `var(--zinc-950)` … `var(--zinc-100)` (10 swatches); os `<div>` de valor
  hex ao lado de cada swatch estão vazios (`font-family:var(--font-mono)`
  sem texto), então nem documentação textual do hex existe ali.
- `guidelines/colors-accent.card.html:6` — `var(--violet-600)`,
  `var(--violet-500)`, `var(--violet-400)`, `var(--violet-300)`.
- `guidelines/elevation.card.html:5` — `var(--ryu-base)`.
- `thumbnail.html:3` — `var(--ryu-base)`; linha 7 (não citada acima) usa
  `var(--violet-400)` e `var(--violet-600)`.
- `tokens/effects.css:7` — `--focus-ring:0 0 0 1px var(--violet-500)`: o
  próprio token de foco do design system aponta para uma cor indefinida,
  em vez de `--border-focus` (que existe e já é claro+escuro em
  `tokens/colors.css:39` e `:131`).
- `components/core/Button.jsx:5` — variante `secondary`:
  `background: 'var(--zinc-800)'`.
- `components/core/Button.jsx:12` — `secondary: 'var(--zinc-700)'`,
  `outline: 'var(--zinc-800)'` (mapa de cor de hover).
- `components/core/Button.jsx:15` — `link: 'var(--violet-300)'` (cor de
  hover do botão link).
- `components/data/CountBadge.jsx:10` — fallback não-accent:
  `'var(--zinc-800)'`.
- `components/app/InboxItem.jsx:3` — severidade `info`:
  `'var(--zinc-500)'`.
- `components/data/StatusPill.jsx:28` — fallback quando o par de tokens não
  é reconhecido: `'var(--zinc-800)'`.
- `ui_kits/ryu-app/Screens2.jsx:131,136` e `templates/ryu-app/Screens2.jsx:
  131,136` — `background:'var(--zinc-800)'` em inputs/selects de exemplo.
- Bloco `<style>` repetido em quase todo `guidelines/*.card.html` e em
  `components/{core,data}/{core,data}.card.html` — regra
  `a:hover{color:var(--violet-300)}` (afeta só o hover de link nesses
  cards de documentação, cosmético).

Como essas properties não existem em nenhuma folha de estilo do pacote,
`var(--zinc-800)` etc. resolvem para o valor inicial da propriedade CSS
(ex.: `background` cai pra `transparent`) em qualquer tema — claro ou
escuro. Não é um "gap de claro"; é um gap total, herdado de uma versão do
design system anterior à reescrita `colors.css` v2.

## `--overlay-scrim`: token de valor único, sem variante de tema

`tokens/effects.css:8` — `--overlay-scrim:rgb(11 11 15 / .8)`. Diferente de
`--card-shadow` (que tem valor claro em `tokens/colors.css:55` — `0 1px 2px
rgb(0 0 0 / .04)` — e valor escuro redefinido em `tokens/colors.css:145` —
`none`), `--overlay-scrim` é declarado uma única vez em `tokens/effects.css`,
fora de `colors.css`, sem seletor de tema, e nenhum outro arquivo o
redefine. O valor `rgb(11 11 15 / .8)` corresponde ao `#0b0b0f` citado como
base do esquema dark-only antigo em `readme.md:39`. Não há um valor
alternativo de claro documentado em lugar nenhum do pacote para este token.

## Inconsistência adicional: `guidelines/colors-status.card.html` hardcoda valores que não batem com `tokens/colors.css`

`guidelines/colors-status.card.html:5` hardcoda hex direto (não usa
`var()`) para as 7 bolinhas de status: `#52525b` (backlog), `#a1a1aa`
(todo), `#eab308` (in_progress), `#8b5cf6` (in_review), `#22c55e` (done),
`#ef4444` (blocked), `#3f3f46` (cancelled). Esses valores não correspondem
aos tokens `--status-*` atuais de `tokens/colors.css` — por exemplo
`--status-in-review:var(--indigo-600)` (`tokens/colors.css:61`) resolve pra
`#0891b2` no claro / `#5fc3dd` no escuro, não `#8b5cf6` (que é a cor
`violet-500` do esquema órfão). Esse card renderiza (não usa var indefinida),
mas documenta uma paleta que já não é a paleta ativa do produto — em
nenhum dos dois temas.

## Contradição de prosa: `readme.md`

- `readme.md:39` — "**Dark-only.** Não existe tema claro; `color-scheme: dark`
  é declarado globalmente e a paleta parte de `#0b0b0f`."
- `readme.md:41` — descreve a paleta como zinc + accent violet
  (`violet-600`/`violet-500`/`violet-400`), batendo com o vocabulário órfão
  acima, não com `gray-*`/`indigo-*` de `tokens/colors.css`.
- `readme.md:94` — índice descreve `tokens/colors.css` como "197 tokens:
  superfícies, zinc, neutral, violet, status, pills" — também descreve o
  vocabulário zinc/violet, não o gray/indigo real do arquivo.

Ou seja, `readme.md` está descrevendo a versão anterior (zinc/violet,
dark-only) do design system, desatualizada em relação ao `tokens/colors.css`
atual (gray/indigo, claro+escuro). O readme não é uma fonte confiável do
estado real dos tokens.

## Resumo para o ticket "Definir tokens de tema claro"

1. Os 117 tokens de cor do bloco `:root` de `tokens/colors.css` já têm
   valor claro concreto, com contraparte escura para todos exceto as 16
   semânticas cruas intencionalmente compartilhadas (item verificado
   mecanicamente, não por inspeção).
2. `--zinc-950..100` (10 tons), `--violet-600/500/400/300` e
   `--ryu-base/sidebar/panel/edge` não têm valor definido em nenhum arquivo
   do pacote, em nenhum tema. São referenciados por
   `guidelines/colors-surfaces.card.html`, `guidelines/colors-neutrals.card.html`,
   `guidelines/colors-accent.card.html`, `guidelines/elevation.card.html`,
   `thumbnail.html`, `tokens/effects.css` (`--focus-ring`), e pelos
   componentes `Button.jsx`, `CountBadge.jsx`, `InboxItem.jsx`,
   `StatusPill.jsx` e `Screens2.jsx` (ambas as cópias).
3. `--overlay-scrim` (`tokens/effects.css:8`) tem um único valor, sem
   variante por tema, herdado do esquema dark-only antigo (`#0b0b0f`).
4. `readme.md` (linhas 39, 41, 94) e os cards de `guidelines/colors-*`
   descrevem uma paleta (zinc/violet, dark-only) que não é a paleta ativa
   de `tokens/colors.css` (gray/indigo-ciano, claro+escuro) — a prosa do
   pacote está desatualizada em relação ao arquivo de tokens real.
5. `guidelines/colors-status.card.html` hardcoda 7 hex que também não
   batem com os `--status-*` atuais de `tokens/colors.css`.
