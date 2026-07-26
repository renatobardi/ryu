Botão padrão do Ryu — use `primary` para a ação principal de cada tela (criar issue, enviar, salvar) e `link`/`danger` para ações inline dentro de listas.

```jsx
<Button variant="primary">Criar</Button>
<Button variant="secondary" size="sm">Marcar todas como lidas</Button>
<Button variant="link">rodar agora</Button>
<Button variant="danger">excluir</Button>
```

Variantes: `primary` (violet-600 → violet-500 no hover), `secondary` (zinc-800 → zinc-700), `outline` (input escuro com borda), `ghost`, `link` (12px violet-400) e `danger` (12px zinc-500 → red-400). Tamanhos `sm`/`md`/`lg`; `full` para largura total. Nunca há sombra — só troca de cor.
