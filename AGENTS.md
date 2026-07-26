# Ryu — notas para agentes

## Como rodar os testes

O pacote `ryu` não está instalado no `.venv` como editable, então o `pytest` precisa do `PYTHONPATH` apontando para `src`:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
```

Para checagem rápida de lint:

```bash
.venv/bin/python -m ruff check src tests
```
