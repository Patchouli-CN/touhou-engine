"""3D 背景光栅化器: BgFrame → 384x448 uint8 帧缓冲。

合成全走 PIL C 实现: 逐 quad 射影映射用 PERSPECTIVE transform(屏幕 quad ↔
纹理 quad 同是 3D 平面的射影像, 单应即精确透视矫正, 等价 D3D 光栅化);
雾渐变用线性渐变图做 AFFINE 采样(D3D 线性雾因子是屏空间仿射场);
着色 multiply / alpha 合成 paste+mask / 加算 ImageChops.add。
深度: 不透明远→近无条件覆写(等价 zbuffer 近者胜), 半透明/加算远→近
画家算法(被不透明部分遮挡时可能误盖, 实测各关不明显——旧 d3dx_render
同结构)。轴对齐 quad 走 crop+resize 快路径(无单应求解)。
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw

from ..snapshot import GAME_H, GAME_W
from .bg3d_scene import BgFrame, QuadCmd

_NEAREST = Image.Resampling.NEAREST
_PERSPECTIVE = Image.Transform.PERSPECTIVE
_AFFINE = Image.Transform.AFFINE
_FLIP_LR = Image.Transpose.FLIP_LEFT_RIGHT
_FLIP_TB = Image.Transpose.FLIP_TOP_BOTTOM


def _homography(pts: tuple[float, ...], uv: tuple[float, ...]) -> tuple[float, ...]:
    """4 点对应解单应(屏幕 → texel), 返回 PIL PERSPECTIVE 8 系数。"""
    a = np.zeros((8, 8))
    b = np.zeros(8)
    for i in range(4):
        x, y = pts[2 * i], pts[2 * i + 1]
        u, v = uv[2 * i], uv[2 * i + 1]
        a[2 * i] = (x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y)
        b[2 * i] = u
        a[2 * i + 1] = (0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y)
        b[2 * i + 1] = v
    h = np.linalg.solve(a, b)
    return tuple(float(v) for v in h)


class BgRaster:
    """BgFrame 的软件光栅化器: 持有平铺纹理画布与帧缓冲(PIL Image)。"""

    def __init__(self, textures: list[np.ndarray]) -> None:
        # 2x2 平铺画布: WRAP 寻址(D3D 默认)下 uv+滚动 ∈ [0,2) 一次采样到位
        self._tex = [
            Image.fromarray(np.tile(t, (2, 2, 1))) if t.size else None for t in textures
        ]
        self._fb = Image.new("RGB", (GAME_W, GAME_H))
        # 雾渐变源: ±2 倍饱和 padding 的 0→255 斜坡(仿射外推出 [0,1] 时
        # 采样落在 padding 区即夹取, 解决单端 fillcolor 无法双向夹取)
        ramp = np.zeros((1280, 256), dtype=np.uint8)
        ramp[512:768] = np.arange(256, dtype=np.uint8)[:, None]
        ramp[768:] = 255
        self._grad = Image.fromarray(ramp)
        self._alpha_tabs: dict[int, list[int]] = {}
        self._fog_rgb = (0, 0, 0)

    def render(self, frame: BgFrame) -> np.ndarray:
        """渲染一帧 → (GAME_H, GAME_W, 3) uint8 RGB(新数组, 调用方所有)。"""
        fb = Image.new("RGB", (GAME_W, GAME_H), frame.fog_rgb)  # 雾色打底
        self._fog_rgb = frame.fog_rgb
        # vm1/vm2(2D 全屏 quad, 画在 3D 之前, OnDrawHighPrio:575-588)
        for cmd in frame.quads:
            if cmd.pass_idx != -1:
                break
            self._draw_quad(fb, cmd, opaque=False)
        # 清屏色(opcode 13; C: color!=0 → Clear TARGET, 盖掉 vm1/vm2)
        if frame.clear_color:
            c = frame.clear_color
            fb.paste(((c >> 16) & 255, (c >> 8) & 255, c & 255), (0, 0, GAME_W, GAME_H))
        for pass_idx in (0, 1):
            self._render_pass(fb, frame.quads, pass_idx)
        return np.asarray(fb)

    def _render_pass(self, fb: Image.Image, quads: tuple[QuadCmd, ...], p: int) -> None:
        """单 pass(z_level 0/1 → 2/3): 不透明远→近, 然后半透明远→近。"""
        opaque: list[QuadCmd] = []
        trans: list[QuadCmd] = []
        for cmd in quads:
            if cmd.pass_idx != p:
                continue
            if (
                cmd.blend == 0
                and cmd.color[3] == 255
                and cmd.tex_opaque
                and not cmd.zwrite_disable
            ):
                opaque.append(cmd)
            else:
                trans.append(cmd)
        opaque.sort(key=lambda c: -c.sort_z)
        trans.sort(key=lambda c: -c.sort_z)
        for cmd in opaque:
            self._draw_quad(fb, cmd, opaque=True)
        for cmd in trans:
            self._draw_quad(fb, cmd, opaque=False)

    # ---- 单 quad ----
    def _draw_quad(self, fb: Image.Image, cmd: QuadCmd, *, opaque: bool) -> None:
        pts = cmd.pts
        x0 = max(0, int(math.floor(min(pts[0::2]))))
        x1 = min(GAME_W, int(math.ceil(max(pts[0::2]))))
        y0 = max(0, int(math.floor(min(pts[1::2]))))
        y1 = min(GAME_H, int(math.ceil(max(pts[1::2]))))
        if x1 <= x0 or y1 <= y0:
            return
        # 全雾快捷: 输出即雾色; 不透明填矩形, 其余贡献不可测直接跳
        if max(cmd.fog) <= 0.004:
            if opaque:
                fb.paste(self._fog_rgb, (x0, y0, x1, y1))
            return
        if self._is_rect(pts):
            piece = self._rect_piece(cmd, x0, y0, x1, y1)
            mask = None
        else:
            piece, mask = self._persp_piece(cmd, x0, y0, x1, y1)
        if piece is None:
            return
        self._shade_paste(fb, piece, mask, cmd, x0, y0, opaque=opaque)

    @staticmethod
    def _is_rect(pts: tuple[float, ...]) -> bool:
        """轴对齐矩形(角点序局部 (-hw,-hh)..(hw,hh): 左/右/上/下边各自水平)。"""
        return (
            abs(pts[0] - pts[4]) < 0.02
            and abs(pts[2] - pts[6]) < 0.02
            and abs(pts[1] - pts[3]) < 0.02
            and abs(pts[5] - pts[7]) < 0.02
        )

    def _rect_piece(
        self, cmd: QuadCmd, x0: int, y0: int, x1: int, y1: int
    ) -> Image.Image | None:
        """轴对齐 quad 的贴图片(crop + 最近邻 resize, 镜像近似处理翻转)。"""
        pts, uv = cmd.pts, cmd.uv
        flip_x = pts[0] > pts[6]
        flip_y = pts[1] > pts[7]
        ua, ub = (uv[6], uv[0]) if flip_x else (uv[0], uv[6])
        va, vb = (uv[7], uv[1]) if flip_y else (uv[1], uv[7])
        tex = self._tex[cmd.tex_id]
        if tex is None:
            return None
        tw, th = tex.size
        # uv 已在平铺画布坐标([0,2tw)x[0,2th)), 直接裁剪无需回绕
        su, sv = max(0, int(ua)), max(0, int(va))
        sw = max(1, min(tw - su, int(math.ceil(ub)) - su))
        sh = max(1, min(th - sv, int(math.ceil(vb)) - sv))
        piece = tex.crop((su, sv, su + sw, sv + sh))
        bw, bh = x1 - x0, y1 - y0
        if (sw, sh) != (bw, bh):
            piece = piece.resize((bw, bh), _NEAREST)
        if flip_x:
            piece = piece.transpose(_FLIP_LR)
        if flip_y:
            piece = piece.transpose(_FLIP_TB)
        return piece

    def _persp_piece(
        self, cmd: QuadCmd, x0: int, y0: int, x1: int, y1: int
    ) -> tuple[Image.Image | None, Image.Image]:
        """一般 quad: PIL PERSPECTIVE 射影映射 + 多边形 mask。

        系数以 quad 中心为原点并归一分母: 大常数相消(近地平线 quad 的
        e*y+f 抵消到个位数)会击穿 PIL 内部定点精度, 原点取中心量级最稳。
        """
        tex = self._tex[cmd.tex_id]
        bw, bh = x1 - x0, y1 - y0
        if tex is None:
            return None, Image.new("L", (bw, bh), 0)
        try:
            h = _homography(cmd.pts, cmd.uv)
        except np.linalg.LinAlgError:
            return None, Image.new("L", (bw, bh), 0)
        a, b_, c, d, e, f, g, h_ = h
        pts = cmd.pts
        xr = (pts[0] + pts[2] + pts[4] + pts[6]) / 4.0
        yr = (pts[1] + pts[3] + pts[5] + pts[7]) / 4.0
        w = g * xr + h_ * yr + 1.0
        if abs(w) < 1e-12:
            return None, Image.new("L", (bw, bh), 0)
        a, b_, d, e, g, h_ = a / w, b_ / w, d / w, e / w, g / w, h_ / w
        c = (c + h[0] * xr + h[1] * yr) / w
        f = (f + h[3] * xr + h[4] * yr) / w
        # PIL tile 像素 (dx,dy) → 屏 (x0+dx, y0+dy) → 局部 (X-xr, Y-yr)
        sx, sy = x0 - xr, y0 - yr
        coeffs = (a, b_, a * sx + b_ * sy + c, d, e, d * sx + e * sy + f, g, h_)
        piece = tex.transform((bw, bh), _PERSPECTIVE, coeffs, _NEAREST, fillcolor=0)
        mask = Image.new("L", (bw, bh), 0)
        dr = ImageDraw.Draw(mask)
        dr.polygon(
            [
                (pts[0] - x0, pts[1] - y0),
                (pts[2] - x0, pts[3] - y0),
                (pts[6] - x0, pts[7] - y0),
                (pts[4] - x0, pts[5] - y0),
            ],
            fill=255,
        )
        return piece, mask

    def _shade_paste(
        self,
        fb: Image.Image,
        piece: Image.Image,
        mask: Image.Image | None,
        cmd: QuadCmd,
        x0: int,
        y0: int,
        *,
        opaque: bool,
    ) -> None:
        """着色(雾/颜色) + 合成(不透明覆写 / alpha / 加算)。"""
        bw, bh = piece.size
        fog = cmd.fog
        r, g, b, a = cmd.color
        need_rgb = min(fog) < 0.996 or (r, g, b) != (255, 255, 255)
        rgb = piece.convert("RGB") if need_rgb else piece
        # 雾: 渐变场 AFFINE 采样(斜坡 y 值 = 雾因子×255 + 512 偏移)
        if min(fog) < 0.996:
            fa, fb_, fc = self._fog_affine(cmd)
            fg_l = self._grad.transform(
                (bw, bh),
                _AFFINE,
                (0.0, 0.0, 0.0, fa * 255.0, fb_ * 255.0, fc * 255.0 + 512.0),
                _NEAREST,
                fillcolor=128,
            )
            fog_img = Image.new("RGB", (bw, bh), self._fog_rgb)
            rgb = Image.composite(rgb, fog_img, fg_l)
        if (r, g, b) != (255, 255, 255):
            rgb = ImageChops.multiply(rgb, Image.new("RGB", (bw, bh), (r, g, b)))
        if opaque:
            fb.paste(rgb, (x0, y0))
            return
        # alpha = 贴图 A × color.a(× 多边形 mask)
        if a == 255 and mask is None and not piece.has_transparency_data:
            an = None
        else:
            an = piece.getchannel("A")
            if mask is not None:
                an = ImageChops.multiply(an, mask)
            if a != 255:
                an = an.point(self._alpha_tab(a))
        if cmd.blend == 1:  # DESTBLEND ONE(加算, AnmManager.cpp:712-714)
            region = fb.crop((x0, y0, x0 + bw, y0 + bh))
            if rgb.mode != "RGB":
                rgb = rgb.convert("RGB")  # ImageChops 要求同 mode
            if an is not None:
                rgb = ImageChops.multiply(rgb, an.convert("RGB"))
            fb.paste(ImageChops.add(region, rgb), (x0, y0))
        elif an is not None:
            fb.paste(rgb, (x0, y0), an)
        else:
            fb.paste(rgb, (x0, y0))

    def _fog_affine(self, cmd: QuadCmd) -> tuple[float, float, float]:
        """雾因子屏空间仿射系数(过 0/1/2 三顶点拟合; D3D 逐像素雾的近似)。"""
        fog = cmd.fog
        pts = cmd.pts
        xa, ya = pts[0], pts[1]
        xb, yb = pts[2], pts[3]
        xc, yc = pts[4], pts[5]
        d = (yb - yc) * (xa - xc) + (xc - xb) * (ya - yc)
        if abs(d) < 1e-9:
            return 0.0, 0.0, fog[0]
        a0, b0 = (yb - yc) / d, (xc - xb) / d
        a1, b1 = (yc - ya) / d, (xa - xc) / d
        g0, g1, g2 = fog[0] - fog[2], fog[1] - fog[2], fog[2]
        fa = a0 * g0 + a1 * g1
        fb_ = b0 * g0 + b1 * g1
        return fa, fb_, g2 - fa * xc - fb_ * yc

    def _alpha_tab(self, a: int) -> list[int]:
        """Alpha 常量倍率的 point 查表(缓存)。"""
        tab = self._alpha_tabs.get(a)
        if tab is None:
            tab = [i * a // 255 for i in range(256)]
            self._alpha_tabs[a] = tab
        return tab
