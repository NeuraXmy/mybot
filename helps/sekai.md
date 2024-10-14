# 世界计划服务 (sekai)

Project Sekai（世界计划）日服游戏相关服务


###  用户指令

- [`/pjsk bind` 绑定账号](#pjsk-bind)
- [`/pjsk info` 查询个人信息](#pjsk-info)
- [`/pjsk hide` 隐藏抓包数据](#pjsk-hide)
- [`/pjsk live` 获取当前虚拟live信息](#pjsk-live)
- [`/pjsk {sub|unsub} {提醒类型}` 订阅/取消订阅at提醒](#pjsk-subunsub-提醒类型)
- [`/pjsk stamp` 获取或制作表情](#pjsk-stamp)
- [`/pjsk chart` 谱面查询](#pjsk-chart)
- [`/pjsk note num` 物量查询](#pjsk-note-num)
- [`/pjsk card` 卡牌查询](#pjsk-card)
- [`/pjsk card img` 卡面查询](#pjsk-card-img)
- [`/pjsk diff board` 难度排行查询](#pjsk-diff-board)

### 管理指令

- [`/pjsk_notify_{提醒类型}_{on|off}` 开关提醒](#pjsk_notify_提醒类型_onoff)
- [`/pjsk update` 手动更新数据](#pjsk-update)

---

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
```
- **指令别名**

    `/个人信息`

- **示例**

    `/pjsk info`


## `/pjsk hide`
```
隐藏抓包数据，再次使用取消隐藏
```
- **示例**

    `/pjsk hide`


## `/pjsk live`

```
获取近期游戏内虚拟Live信息
```

- **示例**

    `/pjsk live`


## `/pjsk {sub|unsub} {提醒类型}`

```
订阅/取消订阅当前群聊的提醒，当提醒发送时会@所有订阅成员
使用 sub 进行订阅， unsub 进行取消订阅
可以订阅的项目有: live 虚拟Live提醒 song 新曲上线提醒
```

- **示例**

    `/pjsk sub live` 订阅虚拟Live提醒

    `/pjsk unsub song` 取消订阅新曲上线提醒


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

    
    
## `/pjsk chart`

```
按照曲名获取谱面预览，推荐使用日服或台服全名进行搜索
查询特定难度可以加上难度全称或者缩写，例如 master 或者 ma
```

- **指令别名**

    `/谱面查询` `/谱面预览` `/谱面`

- **示例**

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
```

- **指令别名**

    `/查卡面` `/卡面`

- **示例**

    `/查卡面 123` 查询 ID 为 123 的卡面信息


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


## `/pjsk diff board`
```
查询某个难度歌曲列表
支持按等级筛选
```
- **指令别名**

    `/难度排行`
    
- **示例**

    `/难度排行 ma` 查询 Master 难度歌曲列表
    `/难度排行 ma 30` 查询 Master 30歌曲列表
    `/难度排行 ma 30 32` 查询 Master 30~32歌曲列表


--- 

[回到帮助目录](./main.md)