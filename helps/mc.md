# Minecraft服务 (mc)

基于 服务端卫星地图插件或日志监听服务 以及 RCON 协议，提供 Minecraft 服务器对接的服务。主要包含以下功能：
- 一个群聊对应一个Minecraft服务器
- 服务器和玩家状态查询，服务器断线上线提醒
- 玩家上下线通知，玩家游玩时间统计
- 服务器聊天和群聊天同步
- 远程执行服务器指令

监听模式分为卫星地图和日志两种
- 卫星地图模式通过dynamic map插件获取服务器信息和聊天记录、发送消息
- 日志模式通过日志文件获取聊天记录，通过rcon获取服务器信息和发送消息


###  用户指令

- [`/listen` 设置或查询监听模式](#listen)
- [`/send` 向服务器发送消息](#send)
- [`/info` 获取服务器信息](#info)
- [`/geturl` 获取服务器卫星地图链接](#geturl)
- [`/getrconurl` 获取服务器rcon链接](#getrconurl)
- [`/seturl` 设置服务器卫星地图链接](#seturl)
- [`/setinfo` 设置服务器信息](#setinfo)
- [`/setrconurl` 设置服务器rcon链接](#setrconurl)
- [`/setrconpw` 设置服务器rcon密码](#setrconpw)
- [`/oplist` 获取op列表](#oplist)
- [`/rcon` 向服务器发送rcon命令](#rcon)
- [`/playtime` 查询玩家游玩时间](#playtime)
- [`/playtime_clear` 清空玩家游玩时间](#playtime_clear)
- [`/start_game` 切换到新周目](#start_game)
- [`/setoffset` 设置请求时间偏移](#setoffset)
- [`/getoffset` 获取请求时间偏移](#getoffset)
- [`/setchatprefix` 设置聊天前缀](#setchatprefix)
- [`/getchatprefix` 获取聊天前缀](#getchatprefix)
- [`/connect_notify_{on|off}` 开启/关闭服务器连线断线通知](#connect_notify_onoff)

### 管理指令

- [`/opadd` 添加用户为op](#opadd)
- [`/opdel` 删除用户的op](#opdel)

---

## `/listen`
```
设置或查询群聊中服务器的监听模式，只有超级用户或op可以设置
可用的模式:
off: 关闭监听
dynamicmap: 通过卫星地图监听
log: 通过日志文件服务端监听
```
- **示例**

    `/listen` 查询监听模式

    `/listen dynamicmap` 设置监听模式为卫星地图


## `/send`
```
向服务器发送消息，服务器中会显示发送者的群名片
```
- **示例**

    `/send 你好`


## `/info`
```
获取服务器信息，包括预设的服务器信息以及服务器游戏时间、在线玩家状态
```
- **示例**

    `/info`


## `/geturl`
```
获取服务器监听链接
```
- **示例**

    `/geturl`


## `/getrconurl`
```
获取服务器rcon链接
```
- **示例**

    `/getrconurl`


## `/seturl`
```
设置服务器监听链接，只有超级用户或op可以设置
```
- **示例**

    `/seturl http://x.x.x.x:xxxx`


## `/setinfo`
```
设置服务器信息，只有超级用户或op可以设置
```
- **使用方式**

    `/setinfo 服务器信息`


## `/setrconurl`
```
设置服务器rcon链接，只有超级用户或op可以设置
```
- **示例**

    `/setrconurl http://x.x.x.x:xxxx`


## `/setrconpw`
```
设置服务器rcon密码，只有超级用户或op可以设置
需要在私聊中使用
```

- **示例**

    `/setrconpw 123456 pw` 设置群聊 123456 的 rcon 密码为 pw


## `/oplist`
```
获取op列表
```
- **示例**

    `/oplist`


## `/rcon`
```
向服务器发送rcon命令，只有超级用户或op可以操作
```
- **示例**

    `/rcon /list`


## `/playtime`
```
查询当前周目玩家游玩时间
```
- **示例**

    `/playtime`


## `/playtime_clear`
```
清空当前周目玩家游玩时间，只有超级用户或op可以操作
```
- **示例**

    `/playtime_clear`


## `/start_game`
```
切换到新周目，只有超级用户或op可以操作
```
- **示例**

    `/start_game 周目名`


## `/setoffset`
```
设置请求时间偏移，只有超级用户或op可以操作
```
- **示例**

    `/setoffset 100` 设置偏移量为100ms


## `/getoffset`
```
获取请求时间偏移
```
- **示例**

    `/getoffset`


## `/setchatprefix`

设置聊天前缀，只有超级用户或op可以操作
只有游戏中以前缀开头的消息以及/send发送的消息会被转发到群内

- **示例**

    `/setchatprefix` 设置聊天前缀为空

    `/setchatprefix ##` 设置聊天前缀为##


## `/getchatprefix`
```
获取聊天前缀
```
- **示例**

    `/getchatprefix`


## `/connect_notify_{on|off}`
```
开启/关闭服务器连线断线通知，只有超级用户或op可以操作
```
- **示例**

    `/connect_notify_on`

    `/connect_notify_off`

---


## `/opadd`
```
添加用户为op，一次可以@一个或多个群友
```
- **示例**

    `/opadd @用户1 @用户2`


## `/opdel`
```
删除用户的op，一次可以@一个或多个群友
```
- **示例**

    `/opdel @用户1 @用户2`


--- 

[回到帮助目录](./main.md)