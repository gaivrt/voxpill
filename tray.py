"""系统托盘图标 —— 无框后台模式下右键退出的入口。

只负责画图标（idle / 录音两态）；图标的生命周期与菜单在 main.py 里管，
因为 pystray.Icon 必须跑在主线程。配色取自盖尔的 design system：
平时用 Blue #6a9ccd（信息性强调），录音用 Terracotta #d97757（唯一的高亮色）。
"""
from PIL import Image, ImageDraw

IDLE = (106, 156, 205, 255)      # #6a9ccd
ACTIVE = (217, 119, 87, 255)     # #d97757


def make_image(active=False):
    """画一个麦克风托盘图标。active=True（录音中）用赤陶橙，否则用蓝。"""
    color = ACTIVE if active else IDLE
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((26, 10, 38, 36), radius=6, fill=color)     # 话筒头
    d.arc((20, 20, 44, 44), start=0, end=180, fill=color, width=3)  # 支架弧
    d.line((32, 44, 32, 52), fill=color, width=3)                  # 杆
    d.line((24, 52, 40, 52), fill=color, width=3)                  # 底座
    return img
