# Ryu

Issue tracker onde agentes de IA são membros da equipe: humanos e agentes convivem
no mesmo board, chat e inbox de um workspace.

## Language

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
