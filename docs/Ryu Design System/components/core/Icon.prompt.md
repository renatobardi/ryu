Ícone de linha, minimalista, sem cor própria — herda a cor do texto ao redor (estilo sidebar do ChatGPT). Requer o script do Lucide na página.

```html
<script src="https://unpkg.com/lucide@latest"></script>
```
```jsx
<Icon name="inbox" size={16} />
<Icon name="bot" size={14} style={{ color: 'var(--text-accent)' }} />
```

Nomes usados no Ryu: `inbox`, `message-circle`, `user`, `layout-grid`, `folder`, `zap`, `bot`, `users`, `bar-chart-2`, `puzzle`, `book-open`, `settings`, `plus`, `search`, `star`, `archive`, `arrow-left`, `moon`, `sun`, `circle`. Veja a lista completa em [lucide.dev/icons](https://lucide.dev/icons).
