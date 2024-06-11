# Minecraft服务 (mc)

基于服务端卫星地图插件以及 RCON 协议，提供 Minecraft 服务器对接的服务。主要包含以下功能：
- 一个群聊对应一个Minecraft服务器
- 服务器和玩家状态查询，服务器断线上线提醒
- 玩家上下线通知，玩家游玩时间统计
- 服务器聊天和群聊天同步
- 远程执行服务器指令


###  指令列表

- [`/send` 向服务器发送消息](#send-msg)
- [`/info` 获取服务器信息](#info)
- [`/geturl` 获取服务器卫星地图链接](#geturl)
- [`/getrconurl` 获取服务器rcon链接](#getrconurl)
- [`/seturl` 设置服务器卫星地图链接](#seturl-url)
- [`/setinfo` 设置服务器信息](#setinfo-info)
- [`/setrconurl` 设置服务器rcon链接](#setrconurl-url)
- [`/listen` 开关该服务器的监听](#listen)
- [`/opadd` 添加用户为op](#opadd-user)*
- [`/opdel` 删除用户的op](#opdel-user)*
- [`/oplist` 获取op列表](#oplist)
- [`/rcon` 向服务器发送rcon命令](#rcon-cmd)
- [`/playtime` 查询玩家游玩时间](#playtime)
- [`/playtime_clear` 清空玩家游玩时间](#playtime_clear)
- [`/start_game` 切换到新周目](#start_game)

---


## `/send`

向服务器发送消息，服务器中会显示发送者的群名片

- **使用方式**

    `/send <msg>`


## `/info`

获取服务器信息，包括预设的服务器信息以及服务器游戏时间、在线玩家状态

- **使用方式**

    `/info`


## `/geturl`

获取服务器卫星地图链接

- **使用方式**

    `/geturl`


## `/getrconurl`

获取服务器rcon链接

- **使用方式**

    `/getrconurl`


## `/seturl`

设置服务器卫星地图链接，只有超级用户或op可以设置

- **使用方式**

    `/seturl <链接>`


## `/setinfo`

设置服务器信息，只有超级用户或op可以设置

- **使用方式**

    `/setinfo <服务器信息>`


## `/setrconurl`

设置服务器rcon链接，只有超级用户或op可以设置，还需要在bot端手动设置rcon密码

- **使用方式**

    `/setrconurl <链接>`


## `/listen`

开关该服务器的监听，只有超级用户或op可以操作，关闭监听后将不再接收服务器消息，也无法发送消息

- **使用方式**

    `/listen`


## `/opadd`

添加用户为op，一次可以@一个或多个群友

- **使用方式**

    `/opadd @用户`


## `/opdel`

删除用户的op，一次可以@一个或多个群友

- **使用方式**

    `/opdel @用户`


## `/oplist`

获取op列表

- **使用方式**

    `/oplist`


## `/rcon`

向服务器发送rcon命令，只有超级用户或op可以操作

- **使用方式**

    `/rcon <指令>`


## `/playtime`

查询当前周目玩家游玩时间

- **使用方式**

    `/playtime`


## `/playtime_clear`

清空当前周目玩家游玩时间，只有超级用户或op可以操作

- **使用方式**

    `/playtime_clear`


## `/start_game`

切换到新周目，只有超级用户或op可以操作

- **使用方式**

    `/start_game <周目名>`




