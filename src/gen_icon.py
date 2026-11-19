# -*- coding: utf-8 -*-
"""生成工具图标 icon.ico（纯 Python，无依赖）"""
import struct
import zlib

S = 256
px = bytearray(S * S * 4)


def rounded(x, y, r):
    # 是否在圆角矩形内
    cx = min(max(x, r), S - 1 - r)
    cy = min(max(y, r), S - 1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def lerp(a, b, t):
    return int(a + (b - a) * t)


for y in range(S):
    for x in range(S):
        i = (y * S + x) * 4
        # 圆角背景 + 渐变
        if rounded(x, y, 52):
            t = y / (S - 1)
            r = lerp(59, 30, t)    # 3b82f6 -> 1e40af
            g = lerp(130, 64, t)
            b = lerp(246, 175, t)
            px[i:i + 4] = bytes((r, g, b, 255))

        # 机身：白色圆角竖条
        bx0, by0, bx1, by1, br = 88, 40, 168, 216, 22
        if bx0 <= x < bx1 and by0 <= y < by1 and rounded(x - bx0, y - by0, br) and \
           rounded(x - bx0 - (bx1 - bx0 - 2 * br), y - by0, br) and \
           rounded(x - bx0, y - by0 - (by1 - by0 - 2 * br), br) and \
           rounded(x - bx0 - (bx1 - bx0 - 2 * br), y - by0 - (by1 - by0 - 2 * br), br):
            # 顶部听筒横条（挖空成蓝色）
            if 66 <= y < 82 and 106 <= x < 150:
                continue
            # 底部圆点（挖空）
            if (x - 128) ** 2 + (y - 186) ** 2 <= 8 ** 2:
                continue
            px[i:i + 4] = bytes((255, 255, 255, 255))

raw = bytes(px)


def chunk(tag, data):
    c = struct.pack(">I", len(data)) + tag + data
    return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


png = (b"\x89PNG\r\n\x1a\n"
       + chunk(b"IHDR", struct.pack(">IIBBBBB", S, S, 8, 6, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(raw, 9))
       + chunk(b"IEND", b""))

ico = struct.pack("<HHH", 0, 1, 1)
ico += struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22)
with open("icon.ico", "wb") as f:
    f.write(ico + png)
print("icon.ico", len(ico + png), "bytes")
