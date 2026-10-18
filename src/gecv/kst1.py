# -*- coding: utf-8 -*-
"""
kst1 —— 引擎的键值数据库格式（key-value store）。
kst1 -- the engine's key-value database format.

全部结论来自 IDA 反汇编 + 18 个真实文件验证，详见 `docs/formats/kst1.md`。
All conclusions come from IDA disassembly plus validation on 18 real files;
see docs/formats/kst1.md.

与 qpck / PRES / BLZ4 的关系 / Relation to the other formats
----------------------------------------------------------
    qpck 归档        : 平铺的 (CRC64 -> 字节块) 表
    PRES 资源树      : 登记资源路径与引用关系
    BLZ4 压缩        : 可选包装层（.kst.blz 就是 kst1 被 BLZ4 包了一层）
    **kst1（本模块）**: 真正的游戏数据表（任务、文本、角色数据）

用法 / Usage::

    from gecv import blz4, kst1
    data = blz4.decompress(raw) if blz4.is_blz4(raw) else raw
    db = kst1.Kst1(data)
    for i in range(db.numrecord):
        print(db.strings_of_record(i))
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Iterator

__all__ = [
    "MAGIC",
    "Kst1",
    "Kst1Error",
    "NotKst1Error",
    "TruncatedError",
    "read_kst_string",
    "find_string_columns",
    "looks_like_text",
]

MAGIC = b"kst1"

# 头部字段偏移（相对文件起始）/ Header field offsets (relative to file start)
HDR_MAGIC = 0x00
HDR_VERSION = 0x04
HDR_STRIDE = 0x08
HDR_NUMRECORD = 0x0C
HDR_INDEX_OFF = 0x10
HDR_RECORD_OFF = 0x14

# 索引表结构常数 / Index table constants
IDX_NUMBLOCKS = 0x00
IDX_MAXKEY = 0x04
IDX_BLOCKS = 0x08
BLOCK_SIZE = 36          # 每块 36 字节 = base(4) + bitmap(8*4=32)
BLOCK_KEYS = 256         # 每块覆盖 256 个 key


class Kst1Error(Exception):
    """kst1 相关异常基类。Base class for kst1 errors."""


class NotKst1Error(Kst1Error):
    """magic 不是 kst1。Magic is not kst1."""


class TruncatedError(Kst1Error):
    """文件不足以容纳声明的结构。File too short for the declared structure."""


# --------------------------------------------------------------------------
# 编码探测 / Encoding detection
# --------------------------------------------------------------------------
# 引擎文档与实测都表明文本以 UTF-8 为主，但俄语版出现异常字节
# （详见 docs/formats/kst1.md §5.6）。因此这里按顺序尝试多种编码，
# 取"可打印字符最多"的那个结果。
# Text is predominantly UTF-8, but the Russian build shows anomalous bytes
# (see docs §5.6), so we try several encodings and pick the most printable.
_ENCODINGS = ("utf-8", "cp1251", "cp932", "shift_jis", "latin-1")


def _printability(s: str) -> float:
    """返回可打印字符比例（0..1）。Fraction of printable characters."""
    if not s:
        return 0.0
    ok = sum(1 for ch in s if ch.isprintable() or ch in "\n\r\t")
    return ok / len(s)


def looks_like_text(s: str | None, min_len: int = 2) -> bool:
    """判断字符串是否像真实的人类可读文本。Whether a string looks like real text.

    判据 / Criteria:
        - 长度 >= min_len
        - 可打印字符占比 >= 95%
        - 控制字符（除换行/制表）比例不过高
    """
    if s is None or len(s) < min_len:
        return False
    if _printability(s) < 0.95:
        return False
    bad = sum(1 for ch in s if ord(ch) < 32 and ch not in "\n\r\t")
    return bad <= max(1, len(s) // 20)


def decode_best(raw: bytes) -> str:
    """解码字节为文本，UTF-8 优先。Decode bytes to text, preferring UTF-8.

    为什么不能只按"可打印率最高"挑编码 / Why not just pick the most printable encoding
    ------------------------------------------------------------------------------
    UTF-8 的字节序列几乎总能被 cp1251 / latin-1 等单字节编码"成功"解码，
    而且结果往往也可打印（只是变成无意义的西里尔/拉丁乱码）。
    实测：`R:GERショート_切` 的 UTF-8 字节用 cp1251 解出
    `R:GERг‚·гѓ§гѓјгѓ€_е€‡`，可打印率同样是 1.0 —— 平局。

    因此正确顺序是：
        1. 先试 UTF-8。能严格解码就**直接采用**（引擎本身以 UTF-8 为主）。
        2. UTF-8 失败时，才在其它编码里挑可打印率最高的。
        3. 全都不可打印时，回退到 errors="replace" 的 UTF-8，保证不丢数据。

    UTF-8 byte sequences almost always "succeed" under single-byte encodings such as
    cp1251/latin-1, and the result is printable too (just meaningless). So UTF-8 must be
    tried first and accepted outright; only on failure do we fall back to scoring.
    """
    # (1) UTF-8 严格解码优先 / strict UTF-8 first
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass

    # (2) 退而求其次：在其它编码中挑可打印率最高的 / fall back to best-scoring
    best = ""
    best_score = -1.0
    for enc in _ENCODINGS[1:]:
        try:
            s = raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        score = _printability(s)
        if score > best_score:
            best, best_score = s, score

    # (3) 兜底：带替换的 UTF-8，保证总有输出 / last resort: UTF-8 with replacement
    if best_score < 0.5:
        return raw.decode("utf-8", "replace")
    return best


def read_kst_string(data: bytes, at: int, max_len: int = 0x2000) -> str | None:
    """按 `kstGetString` 的结构读取一条字符串。Read one string per kstGetString.

    结构 / Layout（来自反汇编 sub_19A0B64）::

        [u16 length][length 字节内容，最后一个字节必须是 0x00]

    :returns: 解出的文本；结构不合法时返回 None。
    """
    if at <= 0 or at + 2 > len(data):
        return None
    n = struct.unpack_from("<H", data, at)[0]
    if n == 0 or n > max_len or at + 2 + n > len(data):
        return None
    body = data[at + 2:at + 2 + n]
    if body[-1:] != b"\x00":          # 断言 buf[length-1] == '\0'
        return None
    return decode_best(body[:-1])


def find_string_columns(
    data: bytes,
    rec_off: int,
    stride: int,
    numrecord: int,
    probe: int = 300,
    threshold: float = 0.90,
) -> list[int]:
    """自动发现哪些 dword 列存放字符串偏移。Discover which columns hold string offsets.

    三条约束 / Three constraints（见 docs §5.5）:
        1. 非常量列（唯一值 > 1）
        2. 偏移 >= 记录表末尾（文本区在记录区之后）
        3. 解出的内容必须像真实文本（可打印率 >= 95%）

    :returns: 命中的列号列表（dword 索引），升序。
    """
    tail_start = rec_off + numrecord * stride
    n_probe = min(numrecord, probe)
    if n_probe <= 0:
        return []

    cols: list[int] = []
    for pos in range(stride // 4):
        vals = [struct.unpack_from("<I", data, rec_off + r * stride + pos * 4)[0]
                for r in range(n_probe)]
        if len(set(vals)) <= 1:                 # 常量列
            continue
        if min(vals) < tail_start:              # 偏移必须落在文本区
            continue
        good = sum(1 for v in vals if looks_like_text(read_kst_string(data, v)))
        if good >= n_probe * threshold:
            cols.append(pos)
    return cols


@dataclass
class Kst1:
    """一个 kst1 数据库的只读视图。Read-only view of a kst1 database."""

    data: bytes
    version: int = 0
    stride: int = 0
    numrecord: int = 0
    index_off: int = 0
    record_off: int = 0
    numblocks: int = 0
    maxkey: int = 0
    _string_columns: list[int] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        d = self.data
        if len(d) < HDR_RECORD_OFF + 4:
            raise TruncatedError(
                f"kst1 数据仅 {len(d)} 字节，不足 0x18 头部 / too small: {len(d)}B"
            )
        if d[:4] != MAGIC:
            raise NotKst1Error(
                f"kst1 magic 应为 {MAGIC!r}，实际 {d[:4]!r} / bad magic"
            )
        (self.version, self.stride, self.numrecord,
         self.index_off, self.record_off) = struct.unpack_from("<5I", d, HDR_VERSION)

        if self.stride <= 0 or self.stride % 4 != 0:
            raise Kst1Error(f"stride={self.stride} 非法（应为正且 4 的倍数）")
        if self.numrecord < 0:
            raise Kst1Error(f"numrecord={self.numrecord} 为负")

        rec_end = self.record_off + self.numrecord * self.stride
        if rec_end > len(d):
            raise TruncatedError(
                f"记录表结束于 {rec_end}，超出文件大小 {len(d)}"
            )

        if self.index_off + 8 > len(d):
            raise TruncatedError(f"索引表偏移 {self.index_off} 越界")
        self.numblocks, self.maxkey = struct.unpack_from("<2I", d, self.index_off)

        tail = self.index_off + IDX_BLOCKS + self.numblocks * BLOCK_SIZE
        if tail > len(d):
            raise TruncatedError(f"索引块超出文件（需要到 {tail}，文件 {len(d)}）")

    # ---- 记录访问 --------------------------------------------------------
    def record_bytes(self, i: int) -> bytes:
        """取第 i 条记录的原始字节。Raw bytes of record i."""
        if not (0 <= i < self.numrecord):
            raise IndexError(f"记录索引 {i} 越界（共 {self.numrecord}）")
        off = self.record_off + i * self.stride
        return self.data[off:off + self.stride]

    def dword(self, i: int, pos: int) -> int:
        """取第 i 条记录、第 pos 个 dword。Dword `pos` of record i."""
        off = self.record_off + i * self.stride + pos * 4
        return struct.unpack_from("<I", self.data, off)[0]

    # ---- 字符串列 --------------------------------------------------------
    @property
    def string_columns(self) -> list[int]:
        """字符串偏移列（自动探测，结果缓存）。String-offset columns (cached)."""
        if self._string_columns is None:
            self._string_columns = find_string_columns(
                self.data, self.record_off, self.stride, self.numrecord
            )
        return self._string_columns

    def strings_of_record(self, i: int) -> dict[int, str]:
        """取一条记录里所有字符串列的内容。{列号: 文本}"""
        out: dict[int, str] = {}
        for pos in self.string_columns:
            t = read_kst_string(self.data, self.dword(i, pos))
            if t is not None:
                out[pos] = t
        return out

    def iter_records(self) -> Iterator[dict]:
        """遍历全部记录，产出 {index, dwords, strings}。Iterate all records."""
        for i in range(self.numrecord):
            yield {
                "index": i,
                "dwords": [self.dword(i, p) for p in range(self.stride // 4)],
                "strings": self.strings_of_record(i),
            }

    # ---- key 索引 --------------------------------------------------------
    def _block_offset(self, block: int) -> int:
        """第 block 个索引块的字节偏移。Byte offset of index block `block`.

        反汇编里是 `&a1[8*b + 2 + b]`，a1 是 dword 指针，
        因此字节偏移 = 4*(8b + 2 + b) = 36b + 8。
        """
        return self.index_off + IDX_BLOCKS + block * BLOCK_SIZE

    def resolve_key(self, key: int) -> int | None:
        """把 key 映射为记录序号；不存在返回 None。Map a key to a record index.

        算法来自反汇编（sub_19A0CC7 / sub_19A0C67 / sub_19A09C5）:
            block = key // 256; k = key % 256
            bitmap 判存在（MSB-first）；记录号 = base + popcount(bitmap[0..k-1])
        """
        if key < 0 or key > self.maxkey:
            return None
        block, k = divmod(key, BLOCK_KEYS)
        if block >= self.numblocks:
            return None
        off = self._block_offset(block)
        base = struct.unpack_from("<I", self.data, off)[0]
        bitmap = struct.unpack_from("<8I", self.data, off + 4)

        word, bit = divmod(k, 32)
        if not (bitmap[word] >> (31 - bit)) & 1:      # MSB-first
            return None

        total = 0
        for w in range(word):
            total += bin(bitmap[w]).count("1")
        rem = k % 32
        if rem:
            mask = (0xFFFFFFFF << (32 - rem)) & 0xFFFFFFFF
            total += bin(bitmap[word] & mask).count("1")
        return base + total

    def record_by_key(self, key: int) -> dict | None:
        """按 key 取记录。Fetch a record by key."""
        idx = self.resolve_key(key)
        if idx is None or idx >= self.numrecord:
            return None
        return {
            "index": idx,
            "key": key,
            "dwords": [self.dword(idx, p) for p in range(self.stride // 4)],
            "strings": self.strings_of_record(idx),
        }

    # ---- 统计 ------------------------------------------------------------
    def count_present_keys(self) -> int:
        """索引中标记为存在的 key 总数（应等于 numrecord）。"""
        total = 0
        for b in range(self.numblocks):
            off = self._block_offset(b)
            bitmap = struct.unpack_from("<8I", self.data, off + 4)
            total += sum(bin(w).count("1") for w in bitmap)
        return total
