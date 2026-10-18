# -*- coding: utf-8 -*-
"""
BLZ4 —— 游戏使用的压缩包装容器（基于标准 zlib）。
BLZ4 -- the game's compression wrapper container (built on standard zlib).

为什么要先看懂它 / Why this matters
----------------------------------
上一阶段 PRES 名字表导出时，发现名字表里有 4418 个 `.blz` / `.gnf.blz` 后缀的资源。
这些是被 BLZ4 包装过的，我们的递归遍历遇到它们会跳过 —— 因此 BLZ4 是
**继续提高名字表覆盖率的必要前置**。
While exporting the PRES name map we found 4418 resources ending in .blz / .gnf.blz.
Those are BLZ4-wrapped and our recursive walk skips them, so BLZ4 is a prerequisite for
raising name-map coverage.

格式要点 / Key facts
-------------------
头部 32 字节 / 32-byte header:

    偏移 0x00  u32 LE  magic = 0x347A6C62   (即字节 "blz4")
    偏移 0x04  u32 LE  解压后总长度 length
    偏移 0x08  u32 LE  reserved（未解读）
    偏移 0x10  16 字节  解压结果的 MD5

之后跟着若干个"块"，每块 = [u16 LE 压缩长度][标准 zlib 流]。
Then come blocks: each is [u16 LE compressed length][standard zlib stream].

!!! 最容易看错的一点：块顺序是**旋转过的** !!!
!!! The single easiest thing to get wrong: the block ORDER is ROTATED !!!

这不是简单的"顺序拼接"。参考实现里的输出位置计算是：
Blocks are NOT simply concatenated in order. The reference computes output positions as:

    if blockCount == 1 or i == 1:  out_pos = 0
    elif i == 0:                   out_pos = length - BlockSize      # 第 0 块写到末尾！
    else:                          out_pos = headSize + (i-2)*BlockSize

也就是说：**文件中的第 0 个块，实际解压到输出缓冲区的最后位置**；而第 1 个块解压
到偏移 0。这个"旋转 1"的排列必须在解压时反向还原，否则结果前半段正确、后半段错乱，
而 MD5 校验会失败并给出一个非常有误导性的错误。
That is: block #0 in the file expands to the LAST position of the output buffer, while
block #1 expands to offset 0. This rotate-by-1 permutation must be reversed on decompress;
otherwise the first part looks correct while the tail is garbage, and the MD5 check fails
with a very misleading error.

BlockSize = 0x10000 (64 KiB)；headSize = length - (blockCount-1)*BlockSize，
即最后一块的实际长度（可能不足 64 KiB）。

关于"必须字节级一致"这句话的真实含义 / What "byte-identical" really means here
------------------------------------------------------------------------------
本项目**不追求** reproduce 与参考实现逐字节相同的压缩输出（那是没必要的）。
唯一硬约束是：**我们压出来的东西必须能被标准 zlib 的 inflate 解开**，
因为游戏引擎那一侧只会调 inflate。任何符合 RFC1950 的 zlib 流都满足这条。
This project does NOT aim to reproduce byte-identical compressed output. The ONLY hard
constraint is that what we emit must be inflatable by standard zlib, because the engine
only ever calls inflate. Any RFC1950-conformant zlib stream satisfies that.

这条约束带来一个实际收益：我们可以使用压缩率更好的后端（例如 Zopfli），
只要它输出标准 zlib 流即可 —— 游戏照样能读，而且文件更小。压缩慢只在离线
打包时付代价，运行时解压不受影响。
Practical upside: we may use a better compressor (e.g. Zopfli) as long as it emits standard
zlib streams -- the game still reads it and the file is smaller. Slower compression is only
paid offline at pack time; runtime decompression is unaffected.

引擎侧背景（待验证）：参考实现的 README 称"引擎内置 zlib 1.2.8 解压但无压缩"。
这句话我们**没有独立验证过**（可能是第三方中间层而非 exe 本身）。
Engine-side background (UNVERIFIED): the reference README claims the engine embeds
zlib 1.2.8 for inflate but has no deflate. We have NOT independently verified this.

来源与授权 / Provenance
----------------------
规格移植自他人分享的 C# 参考实现 `_temp/202609131828/src/Blz4.cs`。
!!! 该目录不可提交进本仓库；本文件是独立重写，不含其原始代码文本。
Spec ported from the shared C# reference `_temp/202609131828/src/Blz4.cs`.
!!! That directory must NOT be committed; this file is an independent rewrite.
"""

from __future__ import annotations

import hashlib
import zlib

__all__ = [
    "MAGIC",
    "HEADER_SIZE",
    "BLOCK_SIZE",
    "Blz4Error",
    "BadMagicError",
    "Md5MismatchError",
    "decompress",
    "compress",
    "is_blz4",
]

MAGIC = 0x347A6C62  # 字节 b"blz4" / the ASCII bytes "blz4"
HEADER_SIZE = 0x20
BLOCK_SIZE = 0x10000


class Blz4Error(Exception):
    """BLZ4 相关异常的基类。Base class for BLZ4 errors."""


class BadMagicError(Blz4Error):
    """magic 不匹配。Magic mismatch."""


class Md5MismatchError(Blz4Error):
    """解压结果的 MD5 与头部记录不符。Decompressed MD5 disagrees with the header."""


def is_blz4(data: bytes) -> bool:
    """判断一段数据是否为 BLZ4（只看 magic，足够廉价）。True if it looks like BLZ4."""
    return len(data) >= 4 and int.from_bytes(data[:4], "little") == MAGIC


def decompress(data: bytes, *, verify_md5: bool = True) -> bytes:
    """解压 BLZ4 数据。Decompress a BLZ4 blob.

    伪代码 / Pseudocode:

        assert u32(data,0) == 0x347A6C62             # magic
        length   = u32(data, 4)                      # 解压后总长
        md5_head = bytes(data, 0x10, 16)             # 期望的 MD5
        result   = bytearray(length)                 # 预分配输出缓冲

        blockCount = ceil(length / 0x10000)
        headSize   = length - (blockCount-1)*0x10000  # 最后一块的长度
        inOffset   = 0x20                             # 跳过头部

        for i in 0 .. blockCount-1:
            count = u16(data, inOffset)              # 本块压缩数据长度
            zlib_stream = data[inOffset+2 : inOffset+2+count]

            # ↓↓ 旋转还原：决定这块解压到输出缓冲的哪个位置 ↓↓
            if blockCount == 1 or i == 1:  outOffset = 0
            elif i == 0:                   outOffset = length - BLOCK_SIZE
            else:                          outOffset = headSize + (i-2)*BLOCK_SIZE

            outSize = headSize if (blockCount == 1 or i == 1) else BLOCK_SIZE

            result[outOffset:outOffset+outSize] = zlib.decompress(zlib_stream)
            inOffset += 2 + count

        assert md5(result) == md5_head
        return result

    :raises Md5MismatchError: MD5 不符。这通常意味着**旋转位置算错了**或字节错位，
        而不是"文件损坏" —— 遇到这个错误请优先怀疑上面的 outOffset 逻辑。
        This usually means the rotation math is wrong, not that the file is corrupt:
        suspect the outOffset logic above first.
    """
    if len(data) < HEADER_SIZE:
        raise Blz4Error(
            f"BLZ4 数据仅 {len(data)} 字节，不足 {HEADER_SIZE} 字节头部 / "
            f"BLZ4 too short: {len(data)}B < {HEADER_SIZE}B"
        )

    magic = int.from_bytes(data[:4], "little")
    if magic != MAGIC:
        raise BadMagicError(
            f"BLZ4 magic 应为 / expected 0x{MAGIC:08X}，实际 / got 0x{magic:08X}"
        )

    declared_len = int.from_bytes(data[4:8], "little")
    stored_md5 = data[0x10:0x20]

    if declared_len == 0:
        result = b""
        if verify_md5 and stored_md5 != hashlib.md5(result).digest():
            raise Md5MismatchError("BLZ4 MD5 校验失败 / MD5 verification failed")
        return result

    block_count = (declared_len + BLOCK_SIZE - 1) // BLOCK_SIZE
    head_size = declared_len - (block_count - 1) * BLOCK_SIZE

    result = bytearray(declared_len)
    in_offset = HEADER_SIZE

    for i in range(block_count):
        if in_offset + 2 > len(data):
            raise Blz4Error(
                f"第 {i} 块的 u16 长度前缀越界（偏移 {in_offset}，数据长 {len(data)}）/ "
                f"block {i} length prefix out of bounds"
            )
        count = int.from_bytes(data[in_offset:in_offset + 2], "little")
        chunk = data[in_offset + 2:in_offset + 2 + count]
        if len(chunk) != count:
            raise Blz4Error(
                f"第 {i} 块声明 {count} 字节但只剩 {len(chunk)} 字节 / "
                f"block {i} declared {count}B but only {len(chunk)}B remain"
            )

        # 旋转还原 —— 整个格式里最反直觉的一段。See the module docstring.
        # Rotate back -- the most counter-intuitive part of the whole format.
        if block_count == 1 or i == 1:
            out_offset = 0
            out_size = head_size
        elif i == 0:
            out_offset = declared_len - BLOCK_SIZE
            out_size = BLOCK_SIZE
        else:
            out_offset = head_size + (i - 2) * BLOCK_SIZE
            out_size = BLOCK_SIZE

        try:
            inflated = zlib.decompress(chunk)
        except zlib.error as exc:
            raise Blz4Error(f"第 {i} 块 zlib 解压失败 / zlib inflate failed at block {i}: {exc}") from exc

        if len(inflated) != out_size:
            raise Blz4Error(
                f"第 {i} 块解压出 {len(inflated)} 字节，但目标位置需要 {out_size} 字节。"
                f"这几乎肯定是旋转位置算错了 / block {i} inflated to {len(inflated)}B but "
                f"{out_size}B expected; the rotation math is almost certainly wrong"
            )
        result[out_offset:out_offset + out_size] = inflated
        in_offset += 2 + count

    out = bytes(result)
    if verify_md5:
        actual = hashlib.md5(out).digest()
        if actual != stored_md5:
            raise Md5MismatchError(
                f"BLZ4 MD5 不符 / mismatch\n"
                f"  头部记录 / header : {stored_md5.hex()}\n"
                f"  实际计算 / actual : {actual.hex()}\n"
                f"  （最常见原因：旋转的 outOffset 逻辑有误，而非文件损坏）/ "
                f"  (most often caused by wrong rotation math, not corruption)"
            )
    return out


def compress(data: bytes, *, level: int = 9) -> bytes:
    """把原始数据打包成 BLZ4。Wrap raw data into a BLZ4 container.

    会同时处理好那个"旋转 1"的写入顺序，使输出能被 decompress() 正确还原。
    Handles the rotate-by-1 write order so the output round-trips through decompress().

    :param level: zlib 压缩级别 0-9。默认 9（最高压缩率，离线打包可接受）_
        zlib level 0-9. Defaults to 9 (best ratio; acceptable offline).

    注意：本函数**不**保证输出与参考实现逐字节相同，也**不**需要 ——
    只要能被标准 zlib inflate 解开，游戏就能读。详见模块文档顶部。
    Note: output is NOT byte-identical to the reference and does NOT need to be -- it only
    has to be standard-inflatable for the game to read it. See module docstring.
    """
    length = len(data)
    block_count = (length + BLOCK_SIZE - 1) // BLOCK_SIZE if length else 1
    head_size = length - (block_count - 1) * BLOCK_SIZE if length else 0

    chunks: list[bytes] = []
    if not data:
        body = b""
    else:
        for i in range(block_count):
            if block_count == 1 or i == 1:
                in_offset = 0
                in_size = head_size
            elif i == 0:
                in_offset = length - BLOCK_SIZE
                in_size = BLOCK_SIZE
            else:
                in_offset = head_size + (i - 2) * BLOCK_SIZE
                in_size = BLOCK_SIZE

            piece = data[in_offset:in_offset + in_size]
            comp = zlib.compress(piece, level)
            if len(comp) > 0xFFFF:
                raise Blz4Error(
                    f"第 {i} 块压缩后 {len(comp)} 字节，超出 u16 长度前缀上限 65535 / "
                    f"block {i} compressed to {len(comp)}B, exceeds the u16 prefix limit"
                )
            chunks.append(len(comp).to_bytes(2, "little") + comp)
        body = b"".join(chunks)

    header = bytearray(HEADER_SIZE)
    header[0:4] = MAGIC.to_bytes(4, "little")
    header[4:8] = length.to_bytes(4, "little")
    header[0x10:0x20] = hashlib.md5(data).digest()
    return bytes(header) + body
