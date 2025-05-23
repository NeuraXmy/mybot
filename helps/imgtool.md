# 图片处理服务 (imgtool)

提供一些图片处理功能的服务

###  用户指令

- [`/img` 图片处理](#img)
- [`/img help` 查看操作帮助](#img-help)
- [`/img check` 检查图片属性](#img-check)
- [`/img push` 添加图片到列表](#img-push)
- [`/img pop` 从列表移除一张图片](#img-pop)
- [`/img clear` 清空图片列表](#img-clear)
- [`/img rev` 翻转图片列表](#img-rev)
- [`/scan` 二维码识别](#scan)
- [`/qrcode` 生成二维码](#qrcode)
- [`/saying` 生成群友语录](#saying)
- [`/md` Markdown转图片](#md)
- [`/color` 颜色展示](#color)
- [`/pick` 图片取色](#pick)
- [`/gif` 视频转gif](#gif)

### 管理指令

无

### 图片操作

- [`gif` 图片转gif](#gif)
- [`png` 图片转png](#png)
- [`mirror` 镜像翻转图片](#mirror)
- [`rotate` 旋转图片](#rotate)
- [`back` 反转动图](#back)
- [`speed` 调整动图速度](#speed)
- [`mid` 对称效果](#mid)
- [`resize` 调整图片大小](#resize)
- [`gray` 灰度化](#gray)
- [`invert` 反色](#invert)
- [`flow` 流动效果](#flow)
- [`fan` 旋转效果](#fan)
- [`repeat` 重复效果](#repeat)
- [`concat` 拼接图片](#concat)
- [`stack` 合成动图](#stack)
- [`extract` 提取动图帧](#extract)
- [`mirage` 生成幻影坦克](#mirage)
- [`brighten` 亮度调节](#brighten)
- [`contrast` 对比度调节](#contrast)
- [`sharpen` 锐度调节](#sharpen)
- [`saturate` 饱和度调节](#saturate)
- [`blur` 模糊](#blur)
- [`demirage` 揭露幻影坦克](#demirage)
- [`cutout` 抠图](#cutout)

---

## `/img`
```
单张图片处理：
回复一张图片，进行一系列图片处理操作
使用方式为 (回复一张图片) /img 操作1 参数1 操作2 参数2...
可用的图片操作见后文
操作之间只要输出输出类型对应就可以任意连接

多张图片处理：
1. 可以回复包含多张图片的消息，或者回复包含多张图片的折叠消息
使用方式为 (回复多张图片) /img 操作1 参数1 操作2 参数2...
2. 也可以先使用 /img push 添加图片
然后直接 /img 操作1 参数1 操作2 参数2...
```
- **示例**

    `(回复一张图片) /img rotate 90` 逆时针旋转90度

    `(回复一张图片) /img rotate 90 resize 0.5x` 逆时针旋转90度，再缩小到50%

    `(回复多张图片) /img concat` 将多张图片垂直拼接成一张图片


## `/img help`
```
查看某个图片操作的帮助信息
```
- **示例**

    `/img help rotate` 查看rotate操作的帮助信息


## `/img check`
```
获取图片分辨率等属性
```
- **示例**

    `(回复一张图片) /img check` 


## `/img push`
```
将图片添加到列表，供多张图片处理使用
可以回复带有图片的消息或者带有图片的折叠消息，并且可以翻转顺序
```
- **示例**

    `(回复一张图片) /img push` 

    `(回复多张图片) /img push` 按照图片在消息中的顺序添加到列表

    `(回复多张图片) /img push r` 翻转图片顺序再添加到列表


## `/img pop`
```
从列表移除一张图片
```
- **示例**

    `/img pop` 


## `/img clear`
```
清空图片列表
```
- **示例**

    `/img clear` 

## `/img rev`
```
翻转图片列表
```
- **示例**

    `/img rev` 


## `/scan`
```
识别图片中的二维码
```
- **示例**

    `/scan`


## `/qrcode`
```
生成二维码
```
- **示例**

    `/qrcode https://www.test.com`


## `/saying`
```
生成群友语录
```
- **指令别名**

    `/语录`

- **示例**

    `(回复一条文本消息) /语录`


## `/md`
```
将Markdown文本转换为图片
```
- **指令别名**

    `/markdown`

- **示例**

    `(回复一条Markdown文本消息) /md`


## `/color`
```
展示十六进制rgb、整数rgb、浮点数rgb 或者 hsl格式的颜色
```
- **示例**

    `/color #FF0000` 

    `/color rgb 255 0 0` 

    `/color rgbf 1.0 0.0 0.0` 

    `/color hsl 0 100 50` 


## `/pick`
```
从图片中提取配色
```
- **示例**

    `(回复一张图片) /pick` 默认提取10种颜色

    `(回复一张图片) /pick 5` 5种颜色


## `/gif`
```
视频转gif
```

- **示例**

    `(回复一条视频消息) /gif` 


--- 

## 图片操作

## `gif`
```
将一张静态图片转换为gif图。可以用于制作表情
QQ无法正确显示带有透明部分png格式图片，转换为gif后可以正常显示
注意转换过程中会出现不可避免的质量损失。
默认使用优化算法，可以指定不透明度阈值（默认50%）
```
- **输入输出**

    `静态图 -> 静态图`

- **示例**

    `gif n` 使用普通算法生成GIF

    `gif` 使用优化算法以默认50%不透明度阈值生成GIF

    `gif 0.8` 使用优化算法以80%不透明度阈值生成GIF


## `png`
```
将一张静态图片转换为png图
可用于保存无法qq直接下载的gif图
```

- **输入输出**

    `静态图 -> 静态图`

- **示例**

    `png` 将图片转换为png格式


## `mirror`
```
将图片水平或垂直镜像翻转
```
- **输入输出**

    `任意 -> 任意`

- **示例**

    `mirror` 水平翻转

    `mirror v` 垂直翻转


## `rotate`
```
将图片逆时针旋转指定角度
```
- **输入输出**

    `任意 -> 任意`

- **示例**

    `rotate 90` 逆时针旋转90度


## `back`
```
在时间轴上反转动图
```
- **输入输出**

    `动图 -> 动图`

- **示例**

    `back`


## `speed`
```
调整动图速度
```
- **输入输出**

    `动图 -> 动图`

- **示例**

    `speed 2x` 加速到2倍速

    `speed 0.5x` 减速到50%

    `speed 50` 设置间隔为50（ms）


## `mid`
```
生成对称效果，将图片的一侧镜像黏贴到另一侧
```
- **输入输出**

    `任意 -> 任意`

- **示例**

    `mid` 左边翻转到右边

    `mid r` 右边翻转到左边

    `mid v` 上面翻转到下面

    `mid v r` 下面翻转到上面


## `resize`
```
调整图片大小
```
- **输入输出**

    `任意 -> 任意`

- **示例**

    `resize 0.5x` 缩小到50%

    `resize 100` 保持宽高比缩放到长边为100

    `resize 2x 0.5x` 宽放大2倍，高缩小50%

    `resize 100 100` 调整到长宽为 100x100


## `gray`
```
将图片灰度化
```
- **输入输出**

    `任意 -> 任意`

- **示例**

    `gray`


## `invert`
```
将图片颜色反转
```
- **输入输出**

    `任意 -> 任意`

- **示例**

    `invert`


## `flow`
```
生成流动效果
```
- **输入输出**

    `任意 -> 动图`

- **示例**

    `flow` 从左到右流动

    `flow v` 从上到下流动

    `flow r` 从右到左流动

    `flow v r` 从下到上流动

    `flow v r 2x` 从下到上流动，速度为2倍


## `fan`
```
生成旋转效果
```
- **输入输出**

    `任意 -> 动图`

- **示例**

    `fan` 逆时针旋转

    `fan r` 顺时针旋转

    `fan 2x` 逆时针2倍速旋转


## `repeat`
```
生成重复效果
```
- **输入输出**

    `任意 -> 任意`

- **示例**

    `repeat 1 2` 横向重复1次，纵向重复2次

    `repeat 2 3` 横向重复2次，纵向重复3次


## `concat`    
```
将多张图片拼接成一张图片
```
- **输入输出**

    `多张图片 -> 静态图`

- **示例**

    `concat` 将多张图片垂直拼接成一张图片

    `concat h` 将多张图片水平拼接成一张图片

    `concat g` 将多张图片网格拼接


## `stack`
```
将多张图片合成动图
```
- **输入输出**

    `多张图片 -> 动图`

- **示例**

    `stack` 将多张图片合成fps为20的动图

    `stack 10` 将多张图片合成fps为10的动图


## `extract`
```
提取出动图的帧
```
- **输入输出**

    `动图 -> 多张图片`

- **示例**

    `extract` 提取出动图的帧，帧数量过多时会自动抽掉部分帧

    `extract 2` 以2帧为间隔提取出动图的帧


## `mirage`
```
生成幻影坦克
```

- **输入输出**

    `多张图片 -> 静态图`

- **示例**

    `mirage` 使用图片列表倒数第二张作为表面图，倒数第一张作为隐藏图

    `mirage r` 使用图片列表倒数第一张作为表面图，倒数第二张作为隐藏图


## `brighten`
```
调整图片的亮度
参数0对应全黑图片，参数1对应原图
``` 
- **输入输出**

    `任意 -> 任意`

- **示例**

    `brighten 0.5` 降低图片亮度50%

    `brighten 1.5` 提高图片亮度50%


## `contrast`
```
调整图片的对比度
参数0对应全灰图片，参数1对应原图
``` 
- **输入输出**

    `任意 -> 任意`

- **示例**

    `contrast 0.5` 降低图片对比度50%

    `contrast 1.5` 提高图片对比度50%


## `sharpen`
```
调整图片的锐度
参数0对应无锐化图片，参数1对应原图，参数2对应锐化图片
``` 
- **输入输出**

    `任意 -> 任意`

- **示例**

    `sharpen 0.5` 降低图片锐度50%
    `sharpen 1.5` 提高图片锐度50%


## `saturate`
```
调整图片的饱和度
参数0对应黑白图片，参数1对应原图
```
- **输入输出**

    `任意 -> 任意`

- **示例**

    `saturate 0.5` 降低图片饱和度50%

    `saturate 1.5` 提高图片饱和度50%


## `blur`
```
对图片应用高斯模糊
```
- **输入输出**

    `任意 -> 任意`

- **示例**

    `blur` 应用默认半径为3的高斯模糊

    `blur 5` 应用半径为5的高斯模糊


## `crop`
```
裁剪图片
参数中使用实数（带有小数点）或者百分比则对应比例，使用整数则对应像素
```
- **输入输出**

    `任意 -> 任意`

- **示例**

    `crop 100x100` 裁剪图片100x100中间部分

    `crop 0.5x0.5` 裁剪图片中心长宽为原来50%的部分

    `crop 50%x100` 裁剪图片中心长为原来50%，宽为100px的部分

    `crop 100x100 l` 裁剪图片100x100左边部分(lrtb:左右上下)

    `crop 100x100 lt` 裁剪图片100x100左上角部分

    `crop 100x100 50x50` 裁剪图片100x100，相对左上角偏移(50,50)px

    `crop l0.1 t0.2` 裁剪掉图片左边10%，上边20%部分
    

## `demirage`
```
将幻影坦克图的表面图和隐藏图还原
```
- **输入输出**

    `静态图 -> 多张图片`

- **示例**

    `demirage`


## `cutout`
```
抠图，可用抠图方法:  
floodfill（默认）: 洪水算法抠图，用于移除纯色背景  
ai: ai抠图   
洪水算法抠图时可以指定容差，默认为20  
```

- **输入输出**

    `任意 -> 任意`

- **示例**

    `cutout` 使用洪水算法抠图，容差为默认20

    `cutout 50` 使用洪水算法抠图，容差为50

    `cutout ai` 使用AI模型抠图


--- 

[回到帮助目录](./main.md)