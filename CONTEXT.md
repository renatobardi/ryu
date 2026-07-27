# Ryu

Issue tracker onde agentes de IA são membros da equipe: humanos e agentes convivem
no mesmo board, chat e inbox de um workspace.

## Language

### Runtimes

**Runtime**:
Um par *dispositivo + CLI de agente* capaz de reivindicar e executar tasks — ex.:
"claude no macbook do Renato". O CLI sozinho não é um Runtime; a máquina sozinha
também não.
_Avoid_: Provider (é só o CLI), CLI (é só o binário), Executor

**Provider**:
A família de CLI de agente que um Runtime expõe — claude, devin, agy,
opencode. Um agente escolhe o provider; o Ryu escolhe em qual Runtime rodar.
_Avoid_: Runtime (é o par dispositivo+CLI), Vendor, Modelo

**Daemon**:
O processo do Ryu que roda na máquina do usuário, publica os Runtimes dela e é
o único que executa tasks. O binário `ryu` também é client da API — "client"
sozinho não distingue os dois.
_Avoid_: Client, Runner (é o scheduler do servidor), Worker, Agent Host

**Device**:
A máquina onde um Daemon roda. Um Device tem zero ou mais Runtimes — um por
Provider instalado — e um Provider ausente também é informação: é o que falta
instalar ali.
_Avoid_: Machine, Host, Node

### Configuração

**Workspace settings**:
Configuração que pertence ao workspace e vale para todos os seus membros — nome do
workspace, prefixo de issue. Vive no nav, seção Configure.
_Avoid_: Settings (sozinho, ambíguo), Preferences

**Profile**:
A conta do usuário e o que é dele em qualquer workspace — e-mail, nome, tema,
Personal Access Tokens, sessão. Alcançado pelo rodapé de usuário da sidebar.
_Avoid_: Account, My settings, User settings

**Personal Access Token (PAT)**:
Credencial `ryu_*` emitida para um usuário, não para um workspace; autentica CLI e
integrações no lugar do cookie de sessão.
_Avoid_: API key, token de workspace
