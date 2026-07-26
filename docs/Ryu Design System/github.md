repo: renatobardi/ryu
branch: main
path: src/ryu

## Last sync
date: 2026-07-26T01:55:00Z

### Updated in this project
- Tokens extraídos de `app.css` e do `tailwind.config` inline do `base.html`.
- 22 componentes React derivados dos templates Jinja (core, data, app).
- UI kit clicável do workspace com 8 telas recriadas.
- Guia de conteúdo, fundações visuais e iconografia escritos a partir dos templates.

## Screen map
| Tela do projeto | Arquivos do repositório |
|---|---|
| ui_kits/ryu-app — Login | src/ryu/web/templates/login.html |
| ui_kits/ryu-app — Dashboard | src/ryu/web/templates/dashboard.html |
| ui_kits/ryu-app — Board | src/ryu/web/templates/issues/board.html, issues/_board_columns.html |
| ui_kits/ryu-app — Issue detail | src/ryu/web/templates/issues/detail.html, issues/_comments.html |
| ui_kits/ryu-app — Chat | src/ryu/web/templates/chat/index.html, chat/messages.html |
| ui_kits/ryu-app — Inbox | src/ryu/web/templates/inbox/index.html, inbox/_items.html |
| ui_kits/ryu-app — Agents | src/ryu/web/templates/agents/index.html |
| ui_kits/ryu-app — Usage | src/ryu/web/templates/inbox/usage.html |
| Shell (sidebar + topbar) | src/ryu/web/templates/base.html |
| tokens/*.css | src/ryu/web/static/app.css, src/ryu/web/templates/base.html |
