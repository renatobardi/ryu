Tabela de tasks, uso e runtimes.

```jsx
<DataTable
  columns={[{key:'agent',label:'Agente'},{key:'kind',label:'Tipo',muted:true},{key:'status',label:'Status'}]}
  rows={[{agent:'Codebot',kind:'issue_work',status:<StatusPill kind="task" status="running" />}]}
  empty="Nenhuma task executada ainda." />
```

Sem zebra, sem hover forte — no máximo `zinc-900/40` na linha. Datas em `dd/MM HH:mm`.
