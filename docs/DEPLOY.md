# Deploy do Ryu

Guia de deploy e operações do Ryu como container Docker, usando a imagem publicada no GitHub Container Registry (GHCR).

- [Pré-requisitos](#pr%C3%A9-requisitos)
- [Instalação em uma máquina nova](#instala%C3%A7%C3%A3o-em-uma-m%C3%A1quina-nova)
- [Atualizar de versão](#atualizar-de-vers%C3%A3o)
- [Backup e restore](#backup-e-restore)
- [Postgres](#postgres)
- [Publicar uma release](#publicar-uma-release)
- [Troubleshooting](#troubleshooting)

## Pré-requisitos

- Docker instalado e rodando.
- Acesso à internet para baixar `ryu-up.sh` e a imagem `ghcr.io/renatobardi/ryu`.

## Instalação em uma máquina nova

Na pasta onde você quer manter o `ryu.env` (opcional):

```bash
curl -fsSL https://raw.githubusercontent.com/renatobardi/ryu/main/deploy/ryu-up.sh -o ryu-up.sh
bash ryu-up.sh
```

O script:

- gera um `RYU_JWT_SECRET` aleatório e persiste em `~/.config/ryu/secret`;
- cria o volume `ryu_data` e monta em `/data`;
- expõe o app em `http://127.0.0.1:8800`.

Para usar outra porta, tag ou volume:

```bash
bash ryu-up.sh --port 8080 --tag v0.2.0 --data-volume ryu_data --env-file ./ryu.env
```

Veja `deploy/ryu.env.example` para todas as variáveis disponíveis.

## Atualizar de versão

Re-execute o script com a tag desejada. O volume é reaproveitado, então dados e uploads são preservados:

```bash
bash ryu-up.sh --tag v0.2.1
```

Para voltar a uma versão anterior, passe a tag antiga. Para usar `latest`, deixe `--tag` omitido.

## Backup e restore

O volume padrão chama-se `ryu_data` e armazena SQLite, workspaces e uploads.

**Backup:**

```bash
docker run --rm \
  -v ryu_data:/data \
  -v "$(pwd):/backup" \
  alpine tar czf /backup/ryu-backup.tar.gz -C /data .
```

**Restore** (sobrescreve o volume atual):

```bash
docker run --rm \
  -v ryu_data:/data \
  -v "$(pwd):/backup" \
  alpine sh -c 'cd /data && tar xzf /backup/ryu-backup.tar.gz'
```

> Atenção: o restore apaga o estado atual do volume. Pare o container Ryu antes de restaurar.

## Postgres

Crie o banco e o usuário antes de subir o container. Exemplo com `postgresql+asyncpg`:

```bash
# ryu.env
RYU_DATABASE_URL=postgresql+asyncpg://ryu:senha@host.do.postgres/ryu
```

```bash
bash ryu-up.sh --env-file ryu.env
```

O Ryu cria as tabelas automaticamente no startup. O driver `asyncpg` já está na imagem.

## Publicar uma release

**Automático.** Todo merge na `main` publica uma imagem. O workflow `release.yml` lê a última tag `vX.Y.Z`, sobe o **último número** (`v0.4.7` → `v0.4.8`), builda, publica como `ghcr.io/renatobardi/ryu:<tag>` e `ghcr.io/renatobardi/ryu:latest`, e só então cria a tag no repositório.

Não é preciso fazer nada — nem tag, nem comando. A tag é criada pelo próprio workflow com o `GITHUB_TOKEN`, e tag criada assim não re-dispara workflow (o GitHub bloqueia recursão de propósito), então não há risco de loop.

O último número é um contador: sobe a cada merge, seja uma correção de uma linha ou uma migração inteira. Os dois primeiros ficam parados até alguém criar uma tag à mão.

Duas garantias que valem saber:

- **A tag só nasce se o build passar.** Ela é criada depois da publicação, então um build quebrado não consome o número nem deixa tag apontando para um commit sem imagem.
- **Publicações são serializadas** (`concurrency`). Dois merges próximos não disputam a mesma versão: o segundo espera e recalcula.

Só tags no formato exato `vX.Y.Z` entram na conta. Uma `v1.0.0-rc1` ou `v0.4.7.1` é ignorada pelo cálculo — sem isso, a aritmética quebraria ou o número andaria para trás.

### Publicar fora do fluxo

Duas saídas quando você precisa de uma versão específica:

- **Tag à mão** — crie e empurre uma tag `v*`. O workflow a usa como está, sem calcular nada. É assim que se muda um dos dois primeiros números (`v0.5.0`, `v1.0.0`); a partir dela o contador continua.
- **Actions → Release → Run workflow** — publica a imagem com o nome que você digitar, **sem** criar tag no repositório. O workflow recusa se você selecionar outro ref que não a `main`: como toda publicação também move a `:latest` — que é o que o `ryu-up.sh` puxa —, subir de um branch qualquer contaminaria quem está em produção.

Nos dois casos o que se publica é uma imagem e (no fluxo automático) uma tag git. Nenhum dos caminhos cria uma *Release* do GitHub.

## Troubleshooting

### Porta ocupada

Se `--port` já estiver em uso, o `docker run` falhará. Escolha outra porta:

```bash
bash ryu-up.sh --port 8081
```

### Ver logs

```bash
docker logs -f ryu
```

O primeiro login sem e-mail configurado imprime o código no log:

```
[ryu-auth] verification code for voce@exemplo.com: 123456
```

### Reset de senha / secret

- Para ver/trocar o `RYU_JWT_SECRET` gerado pelo script:

  ```bash
  cat ~/.config/ryu/secret
  # edite se necessário, depois:
  bash ryu-up.sh
  ```

- Se você se desconectou e perdeu acesso, pare o container, altere o secret e reinicie. Sessões antigas serão invalidadas.

### Healthcheck falha

O script espera até 30s por `http://127.0.0.1:<port>/healthz`. Se falhar, ele imprime as últimas 30 linhas do log. Verifique:

- Docker está rodando.
- A tag existe no GHCR.
- A porta não está ocupada.
- `RYU_DATABASE_URL` está acessível (se usar Postgres).
