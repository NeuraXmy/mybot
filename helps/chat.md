# GPT聊天服务 (chat)

提供基于 OpenAI ChatGPT 的聊天服务。
目前使用模型的版本为 gpt-4o

###  指令列表

- [`聊天`](#聊天)
- [`/chat_usage 查看GPT额度使用情况`](#chat_usage)*
- [`/autochat_{on|off} 开启关闭自动聊天`](#autochat_onoff)*
- [`/chat_mimic 开启关闭模仿聊天`](#chat_mimic)*
- [`/chat_trigger 立刻触发自动聊天`](#chat_trigger)*
- [`/chat_emo 设置或查看自动聊天情绪值`](#chat_emo)*

---

##  聊天

进行GPT聊天

触发方式：在发言或者回复中 @bot 并且文本不为空

支持多轮对话：回复bot先前的对话即可继续

支持图片对话：在消息中包含图片或者回复带有图片的消息

- 使用方式

    在消息中 @bot 并且文本不为空

- 示例

    `@bot 你好`

    `(回复一张图片) @bot 请翻译图片中的文字`


## `/chat_usage`

查看GPT额度使用情况

- 使用方式

    `/chat_usage [日期=today]` 查询指定日期(默认当天)或全部的额度使用情况

- 示例

    `/chat_usage` 查询当天的额度使用情况

    `/chat_usage 2022-01-01` 查询指定日期的额度使用情况

    `/chat_usage all` 查询全部的额度使用情况


## `/autochat_{on|off}`

开启关闭自动聊天

- 使用方式

    `/autochat_on` 开启自动聊天

    `/autochat_off` 关闭自动聊天



## `/chat_mimic`

开启关闭模仿聊天

- 使用方式

    `/chat_mimic @群友` 开启模仿指定群友的聊天

    `/chat_mimic` 关闭模仿聊天



## `/chat_trigger`

立刻触发自动聊天

- 使用方式

    `/chat_trigger` 立刻触发自动聊天



## `/chat_emo`

设置或查看自动聊天情绪值，越高越积极，越低越消极

- 使用方式

    `/chat_emo` 查看当前自动聊天情绪值

    `/chat_emo [value]` 设置自动聊天情绪值，范围为0-100

    `/chat_emo daynight` 设置情绪值随时间变化，晚上消极，白天积极

    `/chat_emo random` 设置每次自动聊天使用随机情绪




