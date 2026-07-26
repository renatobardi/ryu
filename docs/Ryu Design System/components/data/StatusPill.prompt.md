Pill de status. O rótulo é o próprio valor cru do backend, em minúsculas (`working`, `completed`, `queued`) — o Ryu não traduz nem capitaliza esses estados.

```jsx
<StatusPill kind="agent" status="working" />
<StatusPill kind="task" status="completed" />
<StatusPill kind="state" status="on">ativo</StatusPill>
```

Todas as pills são fundo translúcido (15–35% de alpha) + texto na versão clara da mesma cor. Nunca fundo sólido.
