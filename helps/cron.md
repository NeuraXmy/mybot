# 定时提醒服务 (cron)

提供类似于 Linux crontab 的定时提醒功能，并且使用 GPT 聊天的方式智能创建提醒。

###  用户指令
- [`/cron_add` 添加定时提醒](#cron_add)
- [`/cron_del` 删除定时提醒](#cron_del)
- [`/cron_list` 查看定时提醒列表](#cron_list)
- [`/cron_{sub|unsub}` 订阅/取消订阅提醒](#cron_subunsub)
- [`/cron_sublist` 查看订阅成员列表](#cron_sublist)
- [`/cron_unsuball` 取消所有订阅](#cron_unsuball)
- [`/cron_{mute|unmute}` 关闭/开启提醒](#cron_muteunmute)
- [`/cron_mysub` 查看自己订阅的提醒](#cron_mysub)
- [`/cron_edit` 修改定时提醒](#cron_edit)

### 管理指令
- [`/cron_clear` 清空定时提醒列表](#cron_clear)
- [`/cron_muteall` 关闭所有提醒](#cron_muteall)

---

## `/cron_add`
```
添加定时提醒，使用聊天指示智能创建提醒，并且自动为创建者订阅该提醒
```
- **示例**

    `/cron_add 每天早上7点叫我起床`

    `/cron_add 今天下午3点提醒我去开会`


## `/cron_del`
```
根据 ID 删除定时提醒，只有提醒创建者或超级用户可以删除
```
- **示例**

    `/cron_del 1`


## `/cron_list`
```
查看当前群组的定时提醒列表
```
- **示例**

    `/cron_list`



## `/cron_{sub|unsub}`
```
为自己添加/取消某个提醒的订阅，提醒时会自动 @ 订阅者
如果附加 @用户 则可以为指定用户订阅提醒
只有提醒创建者或超级用户可以为他人添加订阅或取消订阅
```
- **示例**

    `/cron_sub 1` 为自己添加提醒 1 的订阅

    `/cron_unsub 1` 为自己取消提醒 1 的订阅

    `/cron_sub 1 @用户` 为用户添加提醒 1 的订阅

    `/cron_unsub 1 @用户` 为用户取消提醒 1 的订阅



## `/cron_sublist`
```
查看某个提醒的订阅成员列表
```
- **示例**

    `/cron_sublist 1`


## `/cron_unsuball`
```
取消某个提醒的所有订阅，只有提醒创建者或超级用户可以取消所有订阅
```
- **使用方式**

    `/cron_unsuball 1`


## `/cron_{mute|unmute}`
```
关闭/开启某个提醒，只有提醒创建者或超级用户可以关闭提醒
```
- **示例**

    `/cron_mute 1`

    `/cron_unmute 1`

## `/cron_mysub`
```
查看自己订阅的提醒
```
- **示例**

    `/cron_mysub`


## `/cron_edit`
```
修改某个定时提醒，只有提醒创建者或超级用户可以修改
```
- **示例**

    `/cron_edit 1 每天早上7点叫我起床`


---

## `/cron_clear`
```
清空当前群组的定时提醒列表
```
- **示例**

    `/cron_clear`

## `/cron_muteall`
```
关闭当前群组的所有提醒
```
- **示例**

    `/cron_muteall`

--- 

[回到帮助目录](./main.md)