# Pesquisa: Integração Lucide + HTMX

Ticket: #9 — o caminho original (`.scratch/ryu-design-system/issues/04-lucide-htmx-integration.md`) nunca entrou no repo.
Status: investigação concluída — nenhuma decisão tomada aqui.

## 1. Como o Lucide renderiza `<i data-lucide="...">`

Fonte primária (código-fonte, não apenas docs): `packages/lucide/src/createIcons.ts` e
`packages/lucide/src/replaceElement.ts` em
https://github.com/lucide-icons/lucide/tree/main/packages/lucide/src

```ts
export interface CreateIconsOptions {
  icons?: Icons;
  nameAttr?: string;
  attrs?: SVGProps;
  root?: Element | Document | DocumentFragment;
  inTemplates?: boolean;
}

const createIcons = ({
  icons = {},
  nameAttr = 'data-lucide',
  attrs = {},
  root = document,        // <-- default é o document inteiro
  inTemplates,
}: CreateIconsOptions = {}) => {
  ...
  const elementsToReplace = Array.from(root.querySelectorAll(`[${nameAttr}]`));
  elementsToReplace.forEach((element) => replaceElement(element, { nameAttr, icons, attrs }));
  ...
};
```

`replaceElement.ts`:

```ts
const svgElement = createElement(iconNode, iconAttrs);
return element.parentNode?.replaceChild(svgElement, element);
```

Fatos confirmados:

- `createIcons()` varre `root.querySelectorAll('[data-lucide]')` (nameAttr configurável) e
  **substitui** (`replaceChild`) cada elemento casado por um `<svg>` novo. Não é "hidratação"
  in-place; o `<i data-lucide="...">` original é removido do DOM e trocado pelo SVG.
- `root` **é parametrizável** (`Element | Document | DocumentFragment`) e por padrão é
  `document` (a página inteira). Passar um elemento específico limita a busca
  (`querySelectorAll`) ao subtree desse elemento — confirmado também na doc oficial
  "Shadow DOM" (https://lucide.dev/guide/lucide/advanced/shadow-dom), que documenta esse uso:
  ```js
  createIcons({ root: shadowRoot, icons: { TreePalm, Volleyball, Waves } });
  ```
  (exemplo usa shadow root, mas o parâmetro aceita qualquer `Element`/`Document`/`DocumentFragment`).
- **Importante — `querySelectorAll` não inclui o próprio nó-raiz.** Se `root` for passado como um
  elemento que *ele mesmo* tem `data-lucide` (em vez de ser um wrapper que contém ícones como
  descendentes), esse ícone específico **não será encontrado** e ficará com o texto cru
  `data-lucide="..."` sem virar SVG. Isso é relevante para o hook de HTMX abaixo, onde o `elt`
  passado pode ser exatamente o nó de topo do fragmento trocado.
- O SVG gerado por `replaceElement` **mantém o atributo `data-lucide="<nome>"`** (hardcoded em
  `iconAttrs`, independente do `nameAttr` configurado). Isso significa que um SVG já renderizado
  também casa com o seletor `[data-lucide]` numa chamada futura de `createIcons()`. Rodar
  `createIcons()` de novo sobre um subtree que já contém SVGs renderizados **não duplica** o ícone
  (o `replaceChild` troca 1-por-1 por um SVG novo funcionalmente idêntico) — mas é trabalho
  redundante, e destrói/recria o nó SVG (perdendo qualquer listener/estado JS que tivesse sido
  anexado a ele). Por isso a doc de Shadow DOM recomenda `root` explicitamente para "manipular
  pequenas seções de um DOM grande" em vez de rodar em `document` inteiro toda vez.
- Build via CDN/unpkg (`https://unpkg.com/lucide@latest` ou `.../dist/umd/lucide.min.js`, doc:
  https://lucide.dev/guide/lucide/getting-started) expõe o global `lucide` com `createIcons()`
  já ligado a todos os ícones — no bundle UMD o parâmetro `icons = {}` é substituído em build-time
  por `icons = iconAndAliases` (ver `packages/lucide/rollup.config.mjs`, plugin `@rollup/plugin-replace`
  aplicado só no formato `umd`). Ou seja, via CDN basta `lucide.createIcons()` (sem args) ou
  `lucide.createIcons({ root: ... })` — não é preciso passar `icons` manualmente.

## 2. Eventos do HTMX 1.9.x em torno de um swap

Fonte primária: código-fonte de `htmx.js` na tag `v1.9.12`
(https://github.com/bigskysoftware/htmx/blob/v1.9.12/src/htmx.js) e docs de eventos na mesma tag
(https://github.com/bigskysoftware/htmx/blob/v1.9.12/www/content/events.md).

Ordem confirmada no código (`processResponseInfo`, por volta da linha ~3650 do `htmx.js@1.9.12`):

```js
forEach(settleInfo.elts, function (elt) {
    elt.classList.add(htmx.config.settlingClass);
    triggerEvent(elt, 'htmx:afterSwap', responseInfo);   // 1) logo após o swap no DOM
});
...
var doSettle = function () {
    forEach(settleInfo.tasks, function (task) { task.call(); });  // 2) tasks de settle, inclui htmx:load por nó
    forEach(settleInfo.elts, function (elt) {
        elt.classList.remove(htmx.config.settlingClass);
        triggerEvent(elt, 'htmx:afterSettle', responseInfo);      // 3) depois das settle tasks
    });
    ...
};
```

`htmx:load` por nó é disparado via `makeAjaxLoadTask`, empilhado em `settleInfo.tasks` **para
cada filho de topo do fragmento inserido** (ver `insertNodesBefore`, usado por
`swapInnerHTML`/`swapOuterHTML`):

```js
function makeAjaxLoadTask(child) {
    return function () {
        removeClassFromElement(child, htmx.config.addedClass);
        processNode(child);
        processScripts(child);
        processFocus(child)
        triggerEvent(child, 'htmx:load');   // <- detail.elt = child (o nó novo)
    };
}
```

Ou seja: **`htmx:afterSwap` dispara antes de `htmx:load`**, e `htmx:load` dispara antes de
`htmx:afterSettle`, um evento por nó de topo inserido (não um único evento pro fragmento todo).

`htmx:load` também dispara na inicialização da página inteira, com `document.body` como alvo —
confirmado no código de bootstrap do htmx 1.9.12:

```js
ready(function () {
    ...
    processNode(body);
    ...
    setTimeout(function () {
        triggerEvent(body, 'htmx:load', {}); // dá tempo dos ready handlers carregarem antes de disparar
    }, 0);
})
```

(Nota: a doc de eventos da tag `v1.9.12` ainda não menciona esse comportamento de boot — o texto
"this event is also triggered when htmx is first initialized, with the document body as target"
só aparece em versões mais recentes da doc — mas o comportamento já existe no código-fonte do
1.9.12, então vale pra esse projeto.)

### `htmx:load` tem um delay (`settleDelay`), `htmx:afterSwap` não

No htmx 1.9.12, `htmx.config.defaultSettleDelay = 20` (linha 55 de `htmx.js`). O `doSettle()`
(onde `htmx:load` é disparado por nó) roda via `setTimeout(doSettle, swapSpec.settleDelay)`
quando `settleDelay > 0`, e só cai pra chamada síncrona se for explicitamente zerado
(`hx-swap="... settle:0s"` ou config global). Ou seja, por padrão em 1.9.x:

- `htmx:afterSwap` dispara **síncrono**, logo após o swap no DOM — mas só uma vez por elemento de
  `settleInfo.elts` (não um evento por nó novo inserido), e não dispara no load inicial da página.
- `htmx:load` dispara **~20ms depois**, um evento por nó de topo inserido, e também cobre o load
  inicial da página inteira (`document.body`).

Isso é o trade-off real da escolha do hook: usar `htmx:load`/`htmx.onLoad` significa que o ícone
aparece ~20ms depois do fragmento ficar visível (imperceptível visualmente, mas não é "instantâneo"),
em troca de granularidade por nó + cobertura do boot inicial, que `htmx:afterSwap` não dá de graça
(teria que reimplementar a lógica de "iterar os elts do swap" na mão).

### Cobertura confirmada em outros caminhos de swap (OOB e history-restore)

- **OOB swaps** (`hx-swap-oob`): `oobSwap()` (linha 817 de `htmx.js@1.9.12`) chama
  `swap(swapStyle, target, target, fragment, settleInfo)` reaproveitando o **mesmo objeto
  `settleInfo`** da requisição principal — logo as mesmas `makeAjaxLoadTask` são empilhadas em
  `settleInfo.tasks` e disparam `htmx:load` junto com o resto do swap, com o mesmo delay.
- **Restore de histórico** (botão voltar/avançar com cache do htmx): `restoreHistory()` (linha 2421)
  monta seu próprio `settleInfo`, chama `swapInnerHTML(...)` e então
  `settleImmediately(settleInfo.tasks)` (linha 2378) — que roda as tasks **sincronamente** (sem
  `setTimeout`). Ou seja, `htmx:load` também dispara nesse caminho (imediato, sem o delay de 20ms),
  mas note que esse caminho **não** dispara `htmx:afterSwap`/`htmx:afterSettle` (só
  `htmx:historyRestore`) — outro motivo pra preferir `htmx:load` como hook único, já que ele é o
  único evento comum a todos os caminhos de swap observados no código (swap normal, OOB, history
  restore, boot inicial).

### Padrão recomendado pela própria doc do HTMX pra libs de terceiros

Doc oficial (https://htmx.org/docs/, seção de integração com JS de terceiros) recomenda
explicitamente `htmx.onLoad()` em vez de rodar a lib sobre o documento inteiro a cada swap:

> "In htmx, you would instead use the `htmx.onLoad` function, and you would select only from the
> newly loaded content, rather than the entire document"

```js
htmx.onLoad(function(content) {
    var sortables = content.querySelectorAll(".sortable");
    for (var i = 0; i < sortables.length; i++) {
        new Sortable(sortables[i], { animation: 150, ghostClass: 'blue-background-class' });
    }
})
```

`htmx.onLoad(callback)` (https://htmx.org/api/#onLoad) é só um atalho pra `htmx.on('htmx:load', ...)`
que já extrai `evt.detail.elt`:

```js
function onLoadHelper(callback) {
    var value = htmx.on("htmx:load", function(evt) {
        callback(evt.detail.elt);
    });
    return value;
}
```

## 3. Hook/local proposto (fato levantado, não decisão)

Combinando os dois pontos acima, o hook que o próprio padrão documentado do HTMX indica pra esse
caso — análogo ao exemplo oficial com Sortable.js — é:

```js
htmx.onLoad(function (content) {
  lucide.createIcons({ root: content });
});
```

Colocado uma vez, globalmente, em `base.html` (depois dos `<script>` do htmx e do lucide, na
mesma região onde hoje já existe o listener de `htmx:configRequest` em
`src/ryu/web/templates/base.html:124`).

Por que isso evita os dois problemas citados no ticket:

- **Não deixa `data-lucide` cru**: `htmx:load` dispara pra cada nó de topo inserido em *qualquer*
  swap (inclusive parcial via HTMX), então todo fragmento novo passa por `createIcons()` — e
  também cobre o load inicial da página (`htmx:load` disparado com `document.body` no boot).
- **Não duplica/desperdiça**: escopar com `root: content` (em vez do default `document`) limita
  `querySelectorAll('[data-lucide]')` ao subtree recém-inserido, evitando reprocessar/recriar SVGs
  já renderizados em outras partes da página a cada swap.

Ressalva levantada (não resolvida aqui): como `querySelectorAll` não inclui o próprio nó raiz,
se o **elemento de topo** do fragmento trocado por HTMX for ele mesmo um `<i data-lucide="...">`
(em vez de um wrapper com ícones dentro), `root: content` não vai achá-lo. Como o Lucide ainda não
foi adotado no projeto (confirmado: `src/ryu/web/templates/base.html` não tem nenhum `data-lucide`
ainda), não há fragmentos existentes pra auditar — mas isso já dá uma restrição de markup concreta
pra quando a convenção de ícones for definida (território do ticket 06): **todo `<i data-lucide>`
precisa estar dentro de um elemento wrapper num fragmento HTMX-trocável, nunca ser o nó de topo do
próprio fragmento.**

### Correção de premissa do ticket

O ticket descreve o modo de falha como "ícones quebrados (texto do `data-lucide` cru)". Isso não é
literalmente possível: `data-lucide` é um **atributo**, não conteúdo de texto. Um
`<i data-lucide="check"></i>` não convertido é um elemento inline vazio — invisível, sem
dimensão (a menos que tenha CSS explícito de tamanho). O modo de falha real após um swap parcial
sem reprocessar o Lucide é **ícone ausente / layout colapsado** (espaço vazio onde o ícone deveria
estar), não "texto cru aparecendo na tela". Vale ajustar a expectativa de QA pra isso.

### Ordem de carregamento dos scripts

O registro do listener (`htmx.onLoad(...)`) só precisa de `window.htmx` disponível no momento em
que o `<script>` que registra o hook é parseado. Mas o **callback em si** só precisa de
`window.lucide` existir na primeira vez que `htmx:load` disparar — que já acontece no boot da
página (ver acima), então, na prática, `window.lucide` precisa estar pronto antes do primeiro
`htmx:load` do ciclo de vida da página. Um `<script src=".../lucide">` sem `defer`/`async` em
qualquer lugar do documento (parser-blocking, ordem de execução garantida) atende isso; com
`defer`/`async` a ordem de execução relativa ao `ready()`/boot do htmx não é garantida e precisaria
ser verificada à parte.

## Fontes

- Lucide — código-fonte `createIcons`: https://github.com/lucide-icons/lucide/blob/main/packages/lucide/src/createIcons.ts
- Lucide — código-fonte `replaceElement`: https://github.com/lucide-icons/lucide/blob/main/packages/lucide/src/replaceElement.ts
- Lucide — Shadow DOM guide (uso de `root`): https://lucide.dev/guide/lucide/advanced/shadow-dom
- Lucide — Getting started (CDN/unpkg): https://lucide.dev/guide/lucide/getting-started
- Lucide — build UMD com todos os ícones: https://github.com/lucide-icons/lucide/blob/main/packages/lucide/rollup.config.mjs
- HTMX — Events reference (tag v1.9.12): https://github.com/bigskysoftware/htmx/blob/v1.9.12/www/content/events.md
- HTMX — código-fonte `htmx.js` (tag v1.9.12): https://github.com/bigskysoftware/htmx/blob/v1.9.12/src/htmx.js
- HTMX — docs gerais, seção de integração com libs de terceiros: https://htmx.org/docs/
- HTMX — API reference `onLoad`: https://htmx.org/api/#onLoad
