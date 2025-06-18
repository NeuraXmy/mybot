# 连接检测服务 (alive)

> 该服务检测bot当前连接情况，当bot断线或恢复时发送邮件提醒。

### 用户指令

- [`/alive` 测试连接](#alive)

###  管理指令

- [`/killbot` 关闭bot](#killbot)
- [`@bot /status` 查看bot状态](#bot-status)
- [`/status_notify_{on|off}` 开启或关闭状态通知](#status-notify-onoff)

--- 

##  `/alive`

> 测试bot连接

- **示例**

    `/alive`

--- 

##  `/killbot`

> 关闭bot

- **示例**

    `/killbot`

## `@bot /status`

> 查看服务器状态，需要@bot使用

- **指令别名**

    `/状态`

- **示例**

    `@bot /status`

## `/status_notify_{on|off}`

> 开启或关闭群聊内状态通知，开启后每天18:00将推送一次bot状态图

- **示例**

    `/status_notify_on`

    `/status_notify_off`

---

[回到帮助目录](./main.md)