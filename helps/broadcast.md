# 广播服务 (broadcast)

该服务能够将特定群聊或用户添加到广播组，并发送广播消息

### 用户指令

- [`/bc list` 列出所有广播组](#bc-list)
- [`/bc sub` 订阅广播组](#bc-sub)
- [`/bc unsub` 取消订阅广播组](#bc-unsub)
- [`/bc unsuball` 取消订阅所有广播组](#bc-unsuball)
- [`/bc sublist` 列出已订阅的广播组](#bc-sublist)

###  管理指令

- [`/bc add` 添加广播组](#bc-add)
- [`/bc del` 删除广播组](#bc-del)
- [`/bc send` 发送广播消息](#bc-send)
- [`/bc listsub` 列出广播组的订阅者](#bc-listsub)

--- 

##  `/bc list`
```
列出所有广播组
```
- **示例**

    `/bc list`


## `/bc sub`
```
在群聊或者私聊中订阅广播组
在群聊中需要超级管理员才能订阅
```
- **示例**

    `/bc sub xxx` 订阅广播组 `xxx`


## `/bc unsub`
```
在群聊或者私聊中取消订阅广播组
在群聊中需要超级管理员才能取消订阅
```
- **示例**

    `/bc unsub xxx` 取消订阅广播组 `xxx`


## `/bc unsuball`
```
在群聊或者私聊中取消订阅所有广播组
在群聊中需要超级管理员才能取消订阅
```
- **示例**

    `/bc unsuball` 取消订阅所有广播组


## `/bc sublist`
```
列出已订阅的广播组
```
- **示例**

    `/bc sublist`

---

## `/bc add`
```
添加广播组
```
- **示例**

    `/bc add xxx` 添加广播组 `xxx`


## `/bc del`
```
删除广播组
```
- **示例**

    `/bc del xxx` 删除广播组 `xxx`


## `/bc send`
```
发送广播消息
```
- **示例**

    `/bc send xxx abc` 发送广播消息 `abc` 到广播组 `xxx`

    `(回复一条消息) /bc send xxx` 发送回复的那条消息到广播组 `xxx`


## `/bc listsub`
```
列出广播组的订阅者
```
- **示例**

    `/bc listsub xxx` 列出广播组 `xxx` 的订阅者


--- 

[回到帮助目录](./main.md)