# 水群查询服务 (water)

提供查询某条消息是否被人水过的功能

###  用户指令

- [`/water` 查询某条消息是否被水过](#water)
- [`/hash` 查询消息中每个片段的hash](#hash)

### 管理指令

- [`/autowater` 自动水果设置](#autowater)
- [`/water_exclude` 自动水果排除特定hash](#water_exclude)

---


## `/water`
```
回复一条消息，查询某条消息是否被水过
```
- **指令别名**

    `/水果` `/watered`

- **示例**

    `(回复一条消息) /water`


## `/hash`
```
查询消息中每个片段的hash
```
- **示例**

    `(回复一条消息) /hash`

---

## `/autowater`
```
设置当前群自动水果检测的消息类型
支持类型: text, image, stamp, video, forward, json
支持类型集合: 
none = 关闭自动水果检测
low = forward + json
high = image + video + forward + json
all = text + image + stamp + video + forward + json
```
- **示例**

    `/autowater text image`

    `/autowater all`


## `/water_exclude`
```
指定回复消息中的hash不被自动水果检测
```
- **指令别名**

    `/水果排除`

- **示例**

    `(回复一条消息) /water_exclude`

--- 

[回到帮助目录](./main.md)