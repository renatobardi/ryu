# ACP é o protocolo de integração com os runtimes

A integração com os CLIs de agente era one-shot: um argv montado por provider
(um `elif` cada) e o stdout lido linha a linha, virando mensagens de transcript
sem estrutura. Isso produzia três sintomas independentes — catálogo de modelos
chutado em `KNOWN_MODELS`, transcript ilegível e continuidade de sessão só no
claude — que são todos a mesma causa: o protocolo errado. Decidimos falar
**Agent Client Protocol** (JSON-RPC sobre stdio) com os providers que o
implementam nativamente: `claude --acp`, `devin acp`, `opencode acp`.

## Considered Options

- **Manter one-shot `-p`** — custo zero hoje, mas congela os três sintomas e o
  `elif` por provider cresce a cada runtime novo.
- **ACP para todos e tirar o `agy` do suporte** — o `agy` (Antigravity, que
  substituiu o gemini CLI no nosso fluxo) não tem ACP nativo, só bridges de
  terceiros. Foi pedido explicitamente, então não sai.

## Consequences

- O `agy` fica no caminho legado `-p`. Ele é o único provider sem ACP e também o
  único cujo `-p` trava quando stdout não é TTY (upstream aberto), então todo
  subprocesso do Daemon passa a rodar com `stdin=DEVNULL`.
- O modo é ajustável por máquina via `RYU_<PROVIDER>_MODE=acp|oneshot`, seguindo
  a convenção que já existe (`RYU_<X>_PATH/_MODEL/_ARGS`). **Não há fallback
  automático**: os dois modos produzem transcripts de formatos diferentes, e cair
  de um pro outro em silêncio degradaria a saída sem ninguém perceber.
- O caminho `-p` só sobrevive se for exercitado: o selftest de um Runtime roda
  **nos dois modos**. Em ACP o teste é só o handshake (`initialize` +
  `session/new`) e não consome token; em `-p` é uma inferência real, então fica
  sob demanda.
- `KNOWN_MODELS` desaparece em favor de `session/set_model`; `--resume` vira
  `session/load`; o transcript passa a ser tipado para todos os providers ACP.
- Rejeitamos acoplar o Ryu a estruturas internas não documentadas dos CLIs (o
  workaround conhecido pro `agy` headless lê o SQLite de conversas dele). Mesma
  razão pela qual não checamos credencial por provider: o selftest valida
  autenticação de graça, executando de verdade.
