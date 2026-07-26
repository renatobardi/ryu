# UI kit — Ryu (app web)

Recriação clicável do workspace do Ryu, montada **com os componentes deste design system** (nada é reimplementado aqui).

Origem: `src/ryu/web/templates/` de [renatobardi/ryu](https://github.com/renatobardi/ryu).

| Tela | Template de origem | Estado |
|---|---|---|
| Login (2 passos) | `login.html` | recriada, interativa |
| Dashboard | `dashboard.html` | recriada |
| Board | `issues/board.html`, `issues/_board_columns.html` | recriada, cria issue de verdade |
| Issue detail | `issues/detail.html`, `issues/_comments.html` | recriada, comenta e edita status |
| Chat | `chat/index.html`, `chat/messages.html` | recriada, envia mensagem com resposta fake |
| Inbox | `inbox/index.html`, `inbox/_items.html` | recriada, marcar como lida |
| Agents | `agents/index.html` | recriada |
| Usage | `inbox/usage.html` | recriada |
| Projects · Autopilots · Squads · Skills · Runtimes · Settings · My Issues · Search | templates correspondentes | **não recriadas** — aparecem como placeholder |

Arquivos: `data.js` (dados fake), `Shell.jsx` (sidebar + topbar + header de página), `Screens.jsx` (board, issue), `Screens2.jsx` (dashboard, chat, inbox, agents, usage), `App.jsx` (login + roteamento).

Divergência conhecida do original: o drag-and-drop do board não foi recriado (no produto é HTML5 nativo + `htmx.ajax`); aqui o card só abre a issue.
