# 世界计划服务 (sekai)

Project Sekai（世界计划）日服游戏相关服务

部分需要抓包的指令请参考抓包指南: `https://bot.teaphenby.com/public/tutorial/tutorial.html`

数据来源
- ```sekai.best```（大部分图片资源及MasterData）
- ```MiddleRed/pjsk-mysekai-xray``` (MySekai俯视图)
- ```自建抓包工具``` & ```Haruki工具箱``` （抓包数据）

###  用户指令

- 基础指令
    - [`/pjsk bind` 绑定账号](#pjsk-bind)
    - [`/pjsk info` 查询个人信息](#pjsk-info)
    - [`/pjsk hide` 隐藏抓包数据](#pjsk-hide)
    - [`/pjsk check service` 查询抓包服务状态](#pjsk-check-service)
    - [`/pjsk {sub|unsub} {提醒类型}` 订阅/取消订阅at提醒](#pjsk-subunsub-提醒类型)
    - [`/pjsk reg time` 注册时间查询](#pjsk-reg-time)

- 活动
    - [`/pjsk events` 活动列表查询](#pjsk-events)
    - [`/pjsk event` 活动详情查询](#pjsk-event)
    - [`/pjsk event story` 活动剧情查询(AI总结)](#pjsk-event-story)

- 虚拟Live
    - [`/pjsk live` 获取当前虚拟live信息](#pjsk-live)

- 表情
    - [`/pjsk stamp` 获取或制作表情](#pjsk-stamp)

- 歌曲谱面
    - [`/pjsk song` 歌曲查询](#pjsk-song)
    - [`/pjsk song list` 歌曲列表查询](#pjsk-diff-board)
    - [`/pjsk chart` 谱面查询](#pjsk-chart)
    - [`/pjsk alias` 歌曲别名查询](#pjsk-alias)
    - [`/pjsk note num` 物量查询](#pjsk-note-num)
    - [`/pjsk alias add` 添加歌曲别名](#pjsk-alias-set)
    - [`/pjsk alias cancel` 取消上次别名添加](#pjsk-alias-cancel)

- 卡牌
    - [`/pjsk card` 卡牌查询](#pjsk-card)
    - [`/pjsk card img` 卡面查询](#pjsk-card-img)
    - [`/pjsk box` 保有卡组查询](#pjsk-box)
    - [`/pjsk event card` 活动组卡计算](#pjsk-event-card)
    - [`/pjsk challenge card` 挑战组卡计算](#pjsk-challenge-card)
    - [`/pjsk card story` 卡牌剧情查询](#pjsk-card-story)

- 榜线
    - [`/pjsk sk` 榜线预测查询](#pjsk-sk)

- 烤森
    - [`/pjsk mysekai res` 烤森资源查询](#pjsk-mysekai-res)
    - [`/pjsk mysekai blueprint` 烤森蓝图查询](#pjsk-mysekai-blueprint)
    - [`/pjsk mysekai furniture` 烤森家具查询](#pjsk-mysekai-furniture)
    - [`/pjsk mysekai photo` 烤森照片查询](#pjsk-mysekai-photo)

### 管理指令

- [`/pjsk_notify_{提醒类型}_{on|off}` 开关提醒](#pjsk_notify_提醒类型_onoff)
- [`/pjsk update` 手动更新数据](#pjsk-update)
- [`/pjsk alias del` 删除歌曲别名](#pjsk-alias-del)

---

# 基础指令

## `/pjsk bind`
```
绑定游戏ID
```
- **指令别名**

    `/绑定`

- **示例**

    `/pjsk bind 123456789`


## `/pjsk info`
```
查询个人信息
附上ID可以查询ID对应的账号信息
```
- **指令别名**

    `/个人信息`

- **示例**

    `/个人信息`

    `/个人信息 123456789`


## `/pjsk hide`
```
隐藏抓包数据，再次使用取消隐藏
隐藏后，查询会展示抓包数据的指令时不会显示出自己的抓包数据
```

- **示例**

    `/pjsk hide`


## `/pjsk check service`
```
查询抓包服务状态
```

- **指令别名**

    `/pcs`

- **示例**

    `/pcs`


## `/pjsk {sub|unsub} {提醒类型}`

```
订阅/取消订阅当前群聊的提醒，当提醒发送时会@所有订阅成员
使用 sub 进行订阅， unsub 进行取消订阅
可以订阅的项目有: 
* live: 虚拟Live提醒 
* music: 新曲上线提醒
* msr: Mysekai资源刷新自动推送
```

- **示例**

    `/pjsk sub live` 订阅虚拟Live提醒

    `/pjsk unsub music` 取消订阅新曲上线提醒


## `/pjsk reg time`
```
查询游戏账号注册时间
需要上传抓包数据
```
- **指令别名**

    `/注册时间`

- **示例**

    `/注册时间`

---

# 活动

## `/pjsk events`

```
获取所有活动列表
```

- **指令别名**

    `/活动列表`

- **示例**

    `/活动列表`

## `/pjsk event`

```
获取某个活动详情，目前只是给出sekai.best的链接
1. 用活动id查询
2. 用负数索引查询，例如 -1 代表最新活动, -2 代表上一次活动
3. 箱活可以用角色昵称+序号查询，例如"mnr1"
```

- **指令别名**

    `/活动`

- **示例**

    `/活动 123` 查询 ID 为 123 的活动详情

    `/活动 -1` 查询最新活动详情

    `/活动 mnr1` 查询 mnr 第一个箱活详情

## `/pjsk event story`

```
获取AI总结的翻译+省流版活动剧情
1. 用活动id查询
2. 用负数索引查询，例如 -1 代表最新活动, -2 代表上一次活动
3. 箱活可以用角色昵称+序号查询，例如"mnr1"
加上refresh参数能够刷新AI生成的总结
```

- **指令别名**

    `/活动剧情`

- **示例**

    `/活动剧情 123` 查询 ID 为 123 的活动剧情

    `/活动剧情 -1` 查询最新活动剧情

    `/活动剧情 mnr1` 查询 mnr 第一个箱活剧情

    `/活动剧情 123 refresh` 查询 ID 为 123 的活动剧情，并刷新AI生成的总结

---

# 虚拟Live

## `/pjsk live`

```
获取近期游戏内虚拟Live信息
```

- **示例**

    `/pjsk live`

---

# 表情

## `/pjsk stamp`

```
获取或制作游戏内表情贴纸，目前只包含单人表情贴纸
支持 1.根据ID获取表情 2.获取角色所有表情 3.搜索指定角色表情
支持 根据ID和自定义文本自制表情
自制表情前可以先使用"获取角色所有表情"查看哪些表情支持制作
```

- **示例**

    `/pjsk stamp 123` 获取 ID 为 123 的表情

    `/pjsk stamp ena` 获取 ena 的所有表情

    `/pjsk stamp ena 再见` 搜索 ena:再见 的表情

    `/pjsk stamp 123 再见` 用 123 号表情进行制作，文本为再见

---

# 歌曲铺面

## `/pjsk song`

```
按照曲名或ID获取歌曲
```

- **指令别名**

    `/pjsk music` `/查曲`

- **示例**

    `/pjsk song id112` 查询 ID 为 112 的歌曲

    `/pjsk song 热风` 查询标题为热风的歌曲信息


## `/pjsk song list`
```
查询某个难度歌曲列表
支持按等级筛选
```
- **指令别名**

    `/pjsk music list` `/歌曲列表`
    
- **示例**

    `/歌曲列表 ma` 查询 Master 难度歌曲列表
    `/歌曲列表 ma 30` 查询 Master 30歌曲列表
    `/歌曲列表 ma 30 32` 查询 Master 30~32歌曲列表
    `/歌曲列表 ma 31 id` 查询 Master 31歌曲列表，并显示歌曲ID


## `/pjsk chart`

```
按照曲名或歌曲ID获取谱面预览
查询特定难度可以加上难度全称或者缩写，例如 master 或者 ma
```

- **指令别名**

    `/谱面查询` `/谱面预览` `/谱面`

- **示例**

    `/谱面查询 id123` 查询 ID 为 123 的谱面预览

    `/谱面查询 热风` 查询热风的 Master 谱面

    `/谱面查询 热风 apd` 查询热风的 Append 谱面



## `/pjsk note num`

```
根据物量查询谱面
```

- **指令别名**

    `/物量` `/查物量` `/pjsk note count` 

- **示例**

    `/物量 1000` 查询物量为 1000 的谱面


## `/pjsk alias`

```
按照歌曲ID查询歌曲别名
```

- **示例**

    `/pjsk alias 112` 


## `/pjsk alias add`

```
添加歌曲别名，多个别名逗号分割
```

- **示例**

    `/pjsk alias add 123 别名1，别名2...`


## `/pjsk alias cancel`

```
取消自己的上次别名添加
```

- **示例**

    `/pjsk alias cancel`


--- 
# 卡牌


## `/pjsk card`

```
搜索某个角色的卡牌信息，支持用星级、属性、技能类型、限定类型、时间、box过滤
星级示例：四星 4星 生日
属性示例：粉花 粉 花 
技能类型示例：奶 奶卡
限定类型示例：限定 期间限定 fes限 非限
时间示例：今年 去年 2024
加上"box"后可以只显示自己账户有的卡牌（需要绑定并上传抓包数据）
```

- **指令别名**

    `/查卡`

- **示例**

    `/查卡 knd` 查询 knd 的所有卡牌

    `/查卡 knd 四星 粉花 奶卡 限定 今年` 查询 knd 今年的四星粉花奶卡限定卡牌

    `/查卡 123` 查询 ID 为 123 的卡牌详情，目前该功能未实现


## `/pjsk card img`

```
根据ID获取某个角色的卡面图片，包含花前花后
1. 按照ID查询
2. 按照角色昵称+序号查询，例如"mnr1"代表mnr的第一张卡，"mnr-1"代表mnr的最后一张卡
```

- **指令别名**

    `/查卡面` `/卡面`

- **示例**

    `/查卡面 123` 查询 ID 为 123 的卡面信息

    `/查卡面 mnr1` 查询 mnr 的第一张卡面信息

    `/查卡面 mnr-1` 查询 mnr 的最后一张（最新的）卡面信息


## `/pjsk event card`
```
自动进行当期活动组卡计算（需要抓包）
Live类型可选: 协力、单人、auto
```

- **指令别名**

    `/活动组卡` `/活动组队`

- **示例**

    `/活动组卡` 使用默认歌曲和难度进行协力Live组卡

    `/活动组卡 单人` 使用默认歌曲和难度进行单人Live组卡

    `/活动组卡 123` 使用ID为123的歌曲master难度进行协力Live组卡

    `/活动组卡 123 hard` 使用ID为123的歌曲hard难度进行协力Live组卡


## `/pjsk challenge card`
```
自动进行每日挑战Live组卡计算（需要抓包）
```

- **指令别名**

    `/挑战组卡` `/挑战组队`

- **示例**

    `/挑战组卡 miku` 使用默认歌曲和难度进行miku的挑战Live组卡

    `/挑战组卡 miku 123` 使用ID为123的歌曲master难度进行miku的挑战Live组卡

    `/挑战组卡 miku 123 hard` 使用ID为123的歌曲hard难度进行miku的挑战Live组卡



## `/pjsk box`

```
查询自己的卡牌box信息，需要绑定并上传抓包数据
支持用星级、属性、技能类型、限定类型、时间过滤
星级示例：四星 4星 生日
属性示例：粉花 粉 花 
技能类型示例：奶 奶卡
限定类型示例：限定 期间限定 fes限 非限
时间示例：今年 去年 2024
```

- **示例**

    `/pjsk box` 查询所有卡牌

    `/pjsk box 四星 粉花 奶卡 限定 今年` 查询今年的四星粉花奶卡限定卡牌

    `/pjsk box box` 仅查询自己有的卡牌


## `/pjsk card story`

```
根据ID获取某个角色的卡面剧情（AI总结），包含前后篇
1. 按照ID查询
2. 按照角色昵称+序号查询，例如"mnr1"代表mnr的第一张卡，"mnr-1"代表mnr的最后一张卡
加上refresh参数能够刷新AI生成的总结
```

- **指令别名**

    `/卡牌剧情` `/卡面剧情` `/卡剧情`

- **示例**

    `/卡牌剧情 123` 查询 ID 为 123 的卡面剧情

    `/卡牌剧情 mnr1` 查询 mnr 的第一张卡面剧情

    `/卡牌剧情 123 refresh` 查询 ID 为 123 的卡面剧情，并刷新AI生成的总结

---
# 榜线

## `/pjsk sk`

```
查询榜线预测，数据来自3-3.dev
```

- **指令别名**

    `/sk预测` `/pjsk sk predict`

- **示例**

    `/sk预测`


---
# 烤森

## `/pjsk mysekai res`

```
查询烤森资源，需要绑定并上传抓包数据
使用 /pjsk sub msr 订阅推送后，每次资源刷新后第一次上传抓包数据时会在群中自动推送
```

- **指令别名**

    `/msr`

- **示例**

    `/msr`


## `/pjsk mysekai blueprint`
```
查询自己已经获得的烤森蓝图，需要绑定并上传抓包数据
加上id参数可以展示家具id
```

- **指令别名**

    `/msb`

- **示例**

    `/msb`
    
    `/msb id`

## `/pjsk mysekai furniture`
```
查询烤森家具列表，默认显示家具ID
加上id参数可以展示家具详情
```

- **指令别名**

    `/msf`

- **示例**

    `/msf` 查询家具列表

    `/msf 123 234` 查询ID=123和ID=234的家具详情


## `/pjsk mysekai photo`
```
获取烤森照片和拍摄时间，编号从1开始
```

- **指令别名**

    `/msp`

- **示例**

    `/msp 1` 获取第1张烤森照片

--- 


## `/pjsk_notify_{提醒类型}_{on|off}`

```
开关当前群聊的提醒
```

- **示例**

    `/pjsk_notify_live_on` 开启虚拟Live提醒

    `/pjsk_notify_song_off` 关闭新曲上线提醒


## `/pjsk update`

```
手动更新数据
```

- **示例**

    `/pjsk update`


## `/pjsk alias del`

```
删除歌曲别名
```

- **示例**

    `/pjsk alias del 123 别名1 别名2...`


--- 

[回到帮助目录](./main.md)