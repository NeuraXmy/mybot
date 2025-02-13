# 大模型聊天服务 (chat)

提供大模型聊天服务。

### 用户指令

- [`聊天` AI聊天](#聊天)
- [`/chat_model_list` 查询支持的聊天模型](#chat_model_list)
- [`/tts` 文本转语音](#tts)

### 管理指令

- [`/chat_model` 查询或修改聊天模型](#chat_model)

---

##  `聊天`

```
进行AI聊天
触发方式：在发言或者回复中 @bot 并且文本不为空
支持多轮对话：回复bot先前的对话即可继续
支持图片对话：在消息中包含图片或者回复带有图片的消息
支持Python程序调用：在询问中明确指出让GPT立刻运行代码
干净模式：在询问中添加 cleanchat 或 cleanmode 关键字，聊天将不使用预设的提示
自定义模型：在询问中添加 model:{model_name} 注意之后需要有一个空格
自定义模型在群聊中需要超级用户权限
```

- **示例**

    `@bot 你好` 普通询问

    `(回复一张图片) @bot 请翻译图片中的文字` 图片询问

    `@bot 第100个质数是什么？请你编写Python代码并立刻执行来告诉我答案。` 调用Python的询问

    `@bot cleanmode 你好` 干净模式询问

    `@bot model:gpt-4o 你好` 指定模型询问


## `/chat_model_list`

```
显示支持的聊天模型
```

- **示例**

    `/chat_model_list`


## `/tts`

```
文本转语音
```

- **示例**

    `/tts 文本`


---

## `/chat_model`

```
查询或修改当前私聊或群聊使用的聊天模型，在群聊中需要超级用户权限
默认修改文本+多模态模型，加上text/mm/tool参数可单独修改文本/多模态/工具模型
```

- **示例**

    `/chat_model` 查询聊天模型

    `/chat_model gpt-4o` 修改文本和多模态模型为 gpt-4o

    `/chat_model text o1-mini` 只修改文本模型为 o1-mini


--- 

[回到帮助目录](./main.md)
