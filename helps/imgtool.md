# 图片处理服务 (imgtool)

提供一些图片处理功能的服务

- **该服务中对图片进行处理的指令均需要回复一张图片**

- **大部分图片变换指令都同时支持动图和静态图**

###  指令列表

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

---

## `/img check`

获取图片分辨率等属性

- **使用方式**

    `/img check` 


## `/img gif`

将一张静态图片转换为gif图。可以用于制作表情（QQ无法正确显示带有透明部分png、jpg格式图片，转换为gif后可以正常显示），注意转换过程中会出现不可避免的质量损失。

- **使用方式**

    `/img gif`


## `/img mirror`

将图片水平或垂直镜像翻转

- **使用方式**

    `/img mirror` 水平翻转

    `/img mirror v` 垂直翻转


## `/img rotate`

将图片逆时针旋转指定角度

- **使用方式**

    `/img rotate <角度>` 

- **示例**

    `/img rotate 90` 逆时针旋转90度


## `/img back`

在时间轴上反转动图

- **使用方式**

    `/img back`


## `/img speed`

调整动图速度，动图最快只能为间隔20ms（50fps）

- **使用方式**

    `/img speed <倍速>x`

    `/img speed <间隔>`

- **示例**

    `/img speed 2x` 加速到2倍速

    `/img speed 50` 设置间隔为50（ms）


## `/img mid`

生成对称效果，将图片的一侧镜像黏贴到另一侧

- **使用方式**

    `/img mid` 左边翻转到右边

    `/img mid r` 右边翻转到左边

    `/img mid v` 上面翻转到下面

    `/img mid v r` 下面翻转到上面


## `/img resize`

调整图片大小

- **使用方式**

    `/img resize <倍数>x` 缩放

    `/img resize <宽> <高>` 调整到指定宽高

    `/img resize <宽>` 保持宽高比，缩放到长边为指定宽

- **示例**

    `/img resize 0.5x` 缩小到50%

    `/img resize 100x100` 调整到100x100

    `/img resize 100` 保持宽高比缩放到长边为100


## `/img gray`

将图片灰度化

- **使用方式**

    `/img gray`


## `/img revcolor`

将图片颜色反转

- **使用方式**

    `/img revcolor`


## `/img flow`

生成流动效果

- **使用方式**

    `/img flow` 从左到右流动

    `/img flow v` 从上到下流动

    `/img flow r` 从右到左流动

    `/img flow v r` 从下到上流动

    `/img flow <倍速>x` 指定速度流动


- **示例**

    `/img flow v r 2x` 从下到上以2倍速流动


## `/img fan`

生成旋转效果

- **使用方式**

    `/img fan` 逆时针旋转

    `/img fan r` 顺时针旋转

    `/img fan <倍速>x` 指定速度旋转


- **示例**

    `/img fan 2x` 2倍速旋转


## `/img repeat`

生成重复效果

- **使用方式**

    `/img repeat <列数> <行数>` 重复指定次数

- **示例**

    `/img repeat 2 3` 重复2列3行


## `/scan`

识别图片中的二维码

- **使用方式**

    `/scan`


## `/qrcode`

生成二维码

- **使用方式**

    `/qrcode <文本>`

- **示例**

    `/qrcode https://www.test.com`




