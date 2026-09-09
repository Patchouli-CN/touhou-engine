"""LZSS 解压(纯函数, 位宽参数化, 不认容器头)。"""

from __future__ import annotations

# 匹配长度偏置: 实际长度 = 编码值 + MIN_MATCH
MIN_MATCH = 3

# 8 个 9bit 字面量组的 flag 位掩码(快径全 1 判定用)
_LIT8_FLAGS = sum(1 << (8 + 9 * k) for k in range(8))


def lzss_decompress(
    src: bytes,
    out_len: int | None = None,
    *,
    dict_bits: int = 13,
    len_bits: int = 4,
) -> bytes:
    """把 LZSS 压缩字节流解成原字节。

    环形字典不显式维护: 它逐字节镜像输出流(写头偏移 1), 匹配 = 输出流上
    距离 d0 的自复制。token 布局: 首 9bit = flag(1) + 字面量/offset 高 8 位;
    flag=0 时再读 ``dict_bits + len_bits - 8`` bit = offset 余位 + 长度。
    """
    # 逐位语义出处 old/touhou/schema/archive/lzss.py(已与原实现逐字节比对一致)
    if dict_bits < 8:
        raise ValueError(f"dict_bits 至少 8 位(token 布局要求), 收到 {dict_bits}")
    dict_size = 1 << dict_bits
    mask = dict_size - 1
    read2 = dict_bits + len_bits - 8
    len_mask = (1 << len_bits) - 1
    out = bytearray()
    pos = 0
    buf = 0  # 位缓冲, 下一位在 MSB 侧
    cnt = 0  # 缓冲有效位数
    while True:
        while cnt < 72:
            take = src[pos : pos + 9]
            pos += len(take)
            if take:
                buf = (buf << (8 * len(take))) | int.from_bytes(take, "big")
                cnt += 8 * len(take)
            else:
                buf <<= 8
                cnt += 8
        buf &= (1 << cnt) - 1  # 截断陈旧高位, 防 bigint 膨胀
        chunk = (buf >> (cnt - 72)) & ((1 << 72) - 1)
        if (chunk & _LIT8_FLAGS) == _LIT8_FLAGS:
            # 快径: 8 个连续字面量 (flag=1 + 8bit, 共 72bit)
            cnt -= 72
            out += bytes((chunk >> (9 * k)) & 0xFF for k in range(7, -1, -1))
        else:
            cnt -= 9
            tok = (buf >> cnt) & 0x1FF
            if tok & 0x100:
                out.append(tok & 0xFF)
            else:
                # 匹配: flag=0 已随高 9bit 读出(offset 高 8 位),
                # 再取 read2 bit = offset 余位 + 长度位
                cnt -= read2
                tok2 = (buf >> cnt) & ((1 << read2) - 1)
                off = ((tok & 0xFF) << (read2 - len_bits)) | (tok2 >> len_bits)
                if off == 0:  # EOD
                    break
                run = (tok2 & len_mask) + MIN_MATCH
                w = len(out)
                # 环读位置 off 对应的输出流距离(写头 = w%dict_size+1);
                # d0=0 即整环; 首 dict_size 字节内引用未写区 → 零填充
                d0 = ((w % dict_size) + 1 - off) & mask
                if d0 == 0:
                    d0 = dict_size
                if d0 > w:
                    pat = b"\x00" * (d0 - w) + bytes(out)
                else:
                    pat = bytes(out[w - d0 :])
                out += (pat * (run // d0 + 1))[:run]
        if out_len is not None and len(out) >= out_len:
            break
    return bytes(out)
