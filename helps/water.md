# 水群查询服务 (water)

提供查询某条消息是否被人水过的功能

###  用户指令

- [`/water` 查询某条消息是否被水过](#water)
- [`/hash` 查询消息中每个片段的hash](#hash)

### 管理指令

- [`/autowater_{类型}_{on|off}` 自动水果开关](#autowater_类型_onoff)
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

## `/autowater_{类型}_{on|off}`
```
开启或关闭当前群组的自动水果功能
支持类型: text, image, stamp, video, forward, json
```
- **示例**

    `/autowater_text_on`

    `/autowater_image_off`

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