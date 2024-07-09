# 世界计划服务 (pjsk)

Project Sekai（世界计划）游戏相关服务
- 打开提醒后，虚拟live开始、结束前，新曲上线时会在群聊中触发提醒
- 游戏数据来源：sekai.best （每天自动更新）
- 玩家数据来源：Unibot


###  指令列表

- [`/pjsk live` 获取当前虚拟live信息](#pjsk-live)
- [`/pjsk_notify_{on|off}` 开关提醒](#pjsk_notify_onoff)*
- [`/pjsk {sub|unsub}` 订阅/取消订阅vlive提醒](#pjsk-sub)
- [`/pjsk sub_list` 查看vlive提醒订阅成员列表](#pjsk-sub_list)
- [`/pjsk bind` 绑定游戏ID](#pjsk-bind)
- [`/pjsk id` 查询绑定的游戏ID](#pjsk-id)
- [`/pjsk mine` 查询剩余矿产统计](#pjsk-mine)
- [`/pjsk stamp` 获取表情](#pjsk-stamp)
- [`/pjsk makestamp` 制作表情](#pjsk-makestamp)
- [`/pjsk update` 手动更新数据](#pjsk-update)*
- [`/pjsk charastory` 搜索包含指定角色的活动剧情](#pjsk-charastory)

---


## `/pjsk live`

获取近期的vlive信息

- **使用方式**

    `/pjsk live`


## `/pjsk_notify_{on|off}`

开关当前群聊的vlive和其他提醒

- **使用方式**

    `/pjsk_notify_on` 

    `/pjsk_notify_off`


## `/pjsk {sub|unsub}`

订阅/取消订阅当前群聊的vlive提醒，当提醒发送时会@所有订阅成员

- **使用方式**

    `/pjsk sub` 

    `/pjsk unsub`


## `/pjsk sub_list`

查看当前群聊vlive提醒订阅成员列表

- **使用方式**

    `/pjsk sub_list`



## `/pjsk bind`

绑定pjsk游戏ID，会自动校验ID是否有效

- **使用方式**

    `/pjsk bind <ID>`


## `/pjsk id`

查询绑定的pjsk游戏ID

- **使用方式**

    `/pjsk id`


## `/pjsk mine`

查询绑定的游戏账号中剩余能挖的石头等资源数量，需要将抓包数据上传到Unibot，并且上传时选择**公开可读**

- **使用方式**

    `/pjsk mine`


## `/pjsk stamp`

获取游戏内表情贴纸，支持根据ID获取表情、获取角色所有表情、搜索指定角色表情，目前只包含了单人表情贴纸

- **使用方式**

    `/pjsk stamp <ID>` 

    `/pjsk stamp <角色简称> <文本>`

    `/pjsk stamp <角色简称>`

- **示例**

    `/pjsk stamp 1001` 获取 ID 为 1001 的表情

    `/pjsk stamp ena 再见` 获取 ena 的再见表情

    `/pjsk stamp ena` 获取 ena 的所有表情


## `/pjsk makestamp`

制作表情，可以先通过`/pjsk stamp <角色简称>`获得能够制作的表情ID

- **使用方式**

    `/pjsk makestamp <ID> <文本>`

- **示例**

    `/pjsk makestamp 26 再见` 制作 ID 为 26 的表情，文本为再见


## `/pjsk update`

手动更新数据

- **使用方式**

    `/pjsk update`


## `/pjsk charastory`

搜索包含指定角色的活动剧情对话

- **使用方式**

    `/pjsk charastory [角色名1] [角色名2] ...`

- **示例**

    `/pjsk charastory mnr mzk` 搜索同时包含 mnr 和 mzk 的活动剧情对话


