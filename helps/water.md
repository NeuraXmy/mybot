# 水群查询服务 (water)

基于 record 服务记录的聊天记录提供查询某条消息是否被人水过的功能

###  用户指令

- [`/water` 查询某条消息是否被水过](#water)

### 管理指令

无

---

## `/water`
```
回复一条消息，查询某条消息是否被水过
对于文本消息采用精确匹配
对于图片消息，使用 PHash 算法 + 图片 HashID 进行匹配
```
- **示例**

    `(回复一条消息) /water`




--- 

[回到帮助目录](./main.md)