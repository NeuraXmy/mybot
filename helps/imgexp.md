# 搜图服务 (imgexp)

使用 Google Lens 和 SauceNAO 搜索图片来源

###  用户指令

- [`/search` 搜图](#search)
- [`/ytdlp` 网页视频下载](#ytdlp)
- [`/ximg` X图片下载](#ximg)

### 管理指令

无

---


## `/search`
```
回复一张图片来搜图
```
- **示例**

    `(回复一张图片) /search`



## `/ytdlp`
```
获取网页视频信息，可用参数：
-i --info 仅返回视频信息不下载
-g --gif 转换视频为 GIF
-l --low-quality 下载低质量视频
```

- **示例**

    `/ytdlp https://www.youtube.com/watch?v=video_id` 下载视频，以mp4格式发送

    `/ytdlp https://www.youtube.com/watch?v=video_id -g` 下载视频，以gif格式发送

    `/ytdlp https://www.youtube.com/watch?v=video_id -i` 获取视频信息

 
 
## `/ximg`
```
获取指定X文章的图片并拼图，可用参数：
--vertical -V 垂直拼图 
--horizontal -H 水平拼图 
--grid -G 网格拼图 
--fold -f 折叠回复
如果不加拼图参数，则默认各个图片分开发送
```

- **示例**

    `/ximg https://x.com/xxx/status/12345` 下载链接中的图片，将各个图片分开发送

    `/ximg https://x.com/xxx/status/12345 -G` 下载链接中的图片，并以网格形式拼图发送 


--- 

[回到帮助目录](./main.md)