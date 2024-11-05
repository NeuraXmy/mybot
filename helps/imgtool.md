# 图片处理服务 (imgtool)

提供一些图片处理功能的服务

- **该服务中对图片进行处理的指令均需要回复一张图片**

- **大部分图片变换指令都同时支持动图和静态图**

###  用户指令

- [`/img check` 检查图片属性](#img-check)
- [`/img gif` 图片转gif](#img-gif)
- [`/img mirror` 镜像翻转图片](#img-mirror)
- [`/img rotate` 旋转图片](#img-rotate)
- [`/img back` 反转动图](#img-back)
- [`/img speed` 调整动图速度](#img-speed)
- [`/img mid` 对称效果](#img-mid)
- [`/img resize` 调整图片大小](#img-resize)
- [`/img gray` 灰度化](#img-gray)
- [`/img revcolor` 反色](#img-revcolor)
- [`/img flow` 流动效果](#img-flow)
- [`/img fan` 旋转效果](#img-fan)
- [`/img repeat` 重复效果](#img-repeat)
- [`/scan` 二维码识别](#scan)
- [`/qrcode` 生成二维码](#qrcode)
- [`/saying` 生成群友语录](#saying)

### 管理指令

无

---

## `/img check`
```
获取图片分辨率等属性
```
- **示例**

    `/img check` 


## `/img gif`
```
将一张静态图片转换为gif图。可以用于制作表情
QQ无法正确显示带有透明部分png格式图片，转换为gif后可以正常显示
注意转换过程中会出现不可避免的质量损失。
```
- **示例**

    `/img gif`


## `/img mirror`
```
将图片水平或垂直镜像翻转
```
- **示例**

    `/img mirror` 水平翻转

    `/img mirror v` 垂直翻转


## `/img rotate`
```
将图片逆时针旋转指定角度
```

- **示例**

    `/img rotate 90` 逆时针旋转90度


## `/img back`
```
在时间轴上反转动图
```
- **示例**

    `/img back`


## `/img speed`
```
调整动图速度
```

- **示例**

    `/img speed 2x` 加速到2倍速

    `/img speed 0.5x` 减速到50%

    `/img speed 50` 设置间隔为50（ms）


## `/img mid`
```
生成对称效果，将图片的一侧镜像黏贴到另一侧
```
- **示例**

    `/img mid` 左边翻转到右边

    `/img mid r` 右边翻转到左边

    `/img mid v` 上面翻转到下面

    `/img mid v r` 下面翻转到上面


## `/img resize`
```
调整图片大小
```

- **示例**

    `/img resize 0.5x` 缩小到50%

    `/img resize 100` 保持宽高比缩放到长边为100

    `/img resize 2x 0.5x` 宽放大2倍，高缩小50%

    `/img resize 100 100` 调整到长宽为 100x100


## `/img gray`
```
将图片灰度化
```
- **示例**

    `/img gray`


## `/img revcolor`
```
将图片颜色反转
```
- **示例**

    `/img revcolor`


## `/img flow`
```
生成流动效果
```
- **示例**

    `/img flow` 从左到右流动

    `/img flow v` 从上到下流动

    `/img flow r` 从右到左流动

    `/img flow v r` 从下到上流动

    `/img flow v r 2x` 从下到上流动，速度为2倍


## `/img fan`
```
生成旋转效果
```
- **示例**

    `/img fan` 逆时针旋转

    `/img fan r` 顺时针旋转

    `/img fan 2x` 逆时针2倍速旋转


## `/img repeat`
```
生成重复效果
```
- **示例**

    `/img repeat 2 3` 重复2列3行


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

--- 

[回到帮助目录](./main.md)