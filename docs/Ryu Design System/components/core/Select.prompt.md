Select nativo do Ryu, usado para status, prioridade, agente e filtros de inbox.

```jsx
<Select defaultValue="todo">
  <option value="backlog">Backlog</option>
  <option value="todo">Todo</option>
</Select>
```

Texto zinc-300 (mais apagado que o Input, que é zinc-100). Em filtros o produto usa `onchange="this.form.submit()"` — sem botão de aplicar.
