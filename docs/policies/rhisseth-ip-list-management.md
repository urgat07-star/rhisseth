# Управление IP-списками Rhisseth

Скрипты предназначены для запуска на VDS от `root`:

```bash
/opt/rhisseth/repository/deploy/native/rhisseth-ip-whitelist-add.sh 185.216.87.44
/opt/rhisseth/repository/deploy/native/rhisseth-ip-blacklist-add.sh 203.0.113.10
/opt/rhisseth/repository/deploy/native/rhisseth-ip-bans-list.sh
/opt/rhisseth/repository/deploy/native/rhisseth-ip-whitelist-list.sh
```

Whitelist сохраняется в `/etc/fail2ban/jail.d/rhisseth-manual.local` и не
попадает под fail2ban. При добавлении IP в whitelist он удаляется из
`/etc/rhisseth-blacklist` и снимается из активного jail `rhisseth-auth`.
Blacklist сохраняется в `/etc/rhisseth-blacklist` и немедленно передаётся в
jail `rhisseth-auth`. Список whitelist выводит `rhisseth-ip-whitelist-list.sh`,
а список банов и blacklist — `rhisseth-ip-bans-list.sh`.

Перед ручным добавлением адреса необходимо проверить его по audit-log: ошибочно
заблокированный адрес администратора удаляется отдельной операцией
`fail2ban-client set <jail> unbanip <ip>`, а запись удаляется из соответствующего
файла.
