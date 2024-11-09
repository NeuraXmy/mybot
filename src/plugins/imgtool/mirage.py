from ..utils import *


def generate_mirage(up_img: Image.Image, hide_img: Image.Image) -> Image.Image:
    max_size = (max(up_img.size[0], hide_img.size[0]), 0)
    up_img = up_img.resize((max_size[0], int(up_img.size[1] * (max_size[0] / up_img.size[0]))))
    hide_img = hide_img.resize((max_size[0], int(hide_img.size[1] * (max_size[0] / hide_img.size[0]))))
    max_size = (max_size[0], max(up_img.size[1], hide_img.size[1]))
    
    if hide_img.size[1] == up_img.size[1]:
        up_img = up_img.convert('L')
        hide_img = hide_img.convert('L')
    elif max_size[1] == hide_img.size[1]:
        up_img_temp = Image.new('RGBA',(max_size),(255,255,255,255))
        up_img_temp.paste(up_img,(0, (max_size[1] - up_img.size[1]) // 2))
        up_img = up_img_temp.convert('L')
        hide_img = hide_img.convert('L')
    elif max_size[1] == up_img.size[1]:
        hide_img_temp = Image.new('RGBA',(max_size),(0,0,0,255))
        hide_img_temp.paste(hide_img,(0, (max_size[1] - hide_img.size[1]) // 2))
        up_img = up_img.convert('L')
        hide_img = hide_img_temp.convert('L')

    
    out = Image.new('RGBA',(max_size),(255,255,255,255)) 
    for i in range(up_img.size[0]):
        for k in range(up_img.size[1]): 
            La = (up_img.getpixel((i,k)) / 512) + 0.5 
            Lb = hide_img.getpixel((i,k)) / 512       
            R = int((255 * Lb) / (1 - (La - Lb)))
            a = int((1 - (La - Lb)) * 255)
            out.putpixel((i, k), (R,R,R,a)) 

    return out