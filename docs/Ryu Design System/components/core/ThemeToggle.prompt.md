Botão de 36px que troca `document.documentElement.dataset.theme` entre `light` (padrão, sem atributo) e `dark`.

```jsx
const [theme, setTheme] = React.useState('light');
React.useEffect(() => { document.documentElement.dataset.theme = theme === 'dark' ? 'dark' : ''; }, [theme]);
<ThemeToggle theme={theme} onChange={setTheme} />
```

Costuma ficar no canto da TopBar ou no rodapé da Sidebar.
