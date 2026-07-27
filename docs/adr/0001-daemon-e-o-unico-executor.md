# O Daemon é o único executor de tasks

O Ryu roda em Docker (local ou remoto), onde não existe nenhum CLI de agente
autenticado — mas o servidor tinha um executor in-process (`runner/loop.py`) que
reivindicava tasks e, sem CLI disponível, caía num *stub executor* que marcava a
task como `completed` e comentava na issue. Na prática, sempre que o daemon
estivesse offline o Ryu fingia que o agente havia trabalhado. Decidimos que a
execução acontece exclusivamente no Daemon, na máquina do usuário; o servidor
mantém apenas o que é responsabilidade dele — scheduler, sweeper de lease, TTL
de fila, retry e GC de work_dir.

## Considered Options

- **`runner_mode=off` como default do deploy** — resolvia o sintoma com uma
  variável de ambiente, mas deixava dois executores no código. Como o Ryu vai
  falar ACP (ver ADR-0002), manter os dois significa implementar ACP duas vezes,
  sendo que a segunda implementação nunca rodaria em produção.
- **Manter `auto` e fazer o stub falhar** em vez de completar — mantém os dois
  executores e ainda adiciona um estado novo.

## Consequences

- `_execute` e `_execute_stub` saem de `runner/loop.py`; sweeper, retry, TTL e GC
  ficam. Sem daemon online, a task permanece `queued` — estado honesto.
- O Dockerfile perde `nodejs`, `npm` e o `npm install -g` dos CLIs de agente:
  eram resíduo do executor server-side.
- Desenvolvimento local passa a ser `ryu serve` + `ryu daemon start` lado a lado.
- Como o Daemon roda na máquina do usuário e executa prompts que outros membros
  do workspace podem ter escrito, o registro do Device é **opt-in por workspace**
  (`ryu daemon enable <ws>`), e o Daemon é supervisionado pelo SO (launchd no
  macOS, Task Scheduler no Windows) — um agente só existe enquanto o Daemon da
  máquina dele estiver de pé.
