# 基础指令

### 用户指令
- [`/help` 获取帮助](#help)

### 管理指令
- [`/enable` 开启群聊](#enable)
- [`/disable` 关闭群聊](#disable)
- [`/group_status` 查看群聊状态](#group_status)
- [`/{服务名}_{on|off}` 在群聊中开启/关闭服务](#服务名_onoff)
- [`/{服务名}_status` 查看当前群聊某个服务状态](#服务名_status)
- [`/service` 查看当前群聊所有服务状态或查询服务在哪些群聊开启](#service)
- [`/blacklist_add` 添加黑名单](#blacklist_add)
- [`/blacklist_del` 删除黑名单](#blacklist_del)
- [`/send_count` 获取当日消息发送数量](#send_count)

---

##  `/help`
```
获取帮助
```
- **示例**

    `@bot /help` 获取帮助

    `@bot /help alive` 获取alive服务的帮助


--- 


## `/enable`
```
开启群聊，开启后才能响应指令，默认为关闭状态
```
- **示例**

    `@bot /enable` 开启当前群聊

    `@bot /enable 123456` 开启群聊123456


## `/disable`
```
关闭群聊，关闭后不再响应指令，默认为关闭状态
```
- **示例**

    `/disable` 关闭当前群聊

    `/disable 123456` 关闭群聊123456


## `/group_status`
```
查看所有群聊开启状态
```
- **示例**

    `/group_status` 查看所有群聊开启状态


## `/{服务名}_{on|off}`
```
在群聊中开启或关闭服务
```
- **示例**

    `/alive_on` 开启alive服务

    `/alive_off` 关闭alive服务


## `/{服务名}_status`
```
查看当前群聊某个服务状态
```
- **示例**

    `/alive_status` 查看alive服务状态


## `/service`
```
查看当前群聊所有服务状态或查询服务在哪些群聊开启
```
- **示例**

    `/service` 查看当前群聊所有服务状态

    `/service alive` 查询alive服务在哪些群聊开启


## `/blacklist_add`
```
添加黑名单，黑名单中的用户将无法使用指令
```

- **示例**

    `/blacklist_add 123456` 将用户123456添加到黑名单


## `/blacklist_del`
```
删除黑名单
```
- **示例**

    `/blacklist_del 123456` 将用户123456从黑名单中删除


## `/send_count`
```
获取当日消息发送数量
```
- **示例**

    `/send_count` 获取当日消息发送数量

--- 

[回到帮助目录](./main.md)