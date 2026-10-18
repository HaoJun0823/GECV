# -*- coding: utf-8 -*-
"""
PRES —— 资源引用树（resource tree）。这是整个工程里**最重要**的一个格式。
PRES -- resource reference tree. This is the single MOST important format in this project.

为什么它最重要 / Why it matters most
-----------------------------------
qpck 归档**只存 CRC64 哈希，不存文件名**（见 qpck 模块文档）。而 PRES 里存着
完整的路径字符串。因此 PRES 是把"哈希"翻译成"文件名"的唯一钥匙：

    PRES 树里的路径字符串 --CRC64--> qpck 的 TOC 哈希

没有它，解包出来的文件只能叫 `_unnamed/<HEX>.bin`，而且我们**无法打包出游戏认的**
包（算不出正确的哈希）。有了它，整条链路才真正可用。
The qpck archive stores ONLY CRC64 hashes -- no filenames. PRES stores the full path
strings. Therefore PRES is the key that translates hashes back into names.

来源与授权 / Provenance and licensing
-------------------------------------
规格移植自一份他人分享的 C# 参考实现（`_temp/202609131828/src/Pres.cs`）。
!!! 那份 C# 代码属于他人分享物，**不可提交进本仓库**；本文件是**独立重写**，
    不含其原始代码文本。
The spec is ported from a shared C# reference (`_temp/202609131828/src/Pres.cs`).
!!! That C# code must NOT be committed here; this file is an INDEPENDENT rewrite
    containing none of its source text.

我们将该参考实现的规格视为"待验证假设"，并用真实游戏数据验证：目前已在
GER 与 GE2RB 的入口 PRES 上通过（能读出合理路径字符串，详见 tests/）。
We treat that reference as a hypothesis to verify against real data: it has been
validated on the entry PRES of both GER and GE2RB (real path strings decode cleanly).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Iterable, Iterator

from .crc64 import hash_path

__all__ = [
    "MAGIC",
    "HEADER_SIZE",
    "PAIR_SLOT_SIZE",
    "PAIR_COUNT",
    "ENTRY_HEADER_SIZE",
    "TYPE_REFERENCE",
    "TYPE_DATA",
    "PresError",
    "BadMagicError",
    "InvalidStructureError",
    "PresEntry",
    "PresPair",
    "PresSet",
    "Pres",
    "parse",
    "iter_paths",
    "build_name_map",
]

MAGIC = 0x73657250  # b"Pres" 的字节序互换结果 / bytes b"Pres" read little-endian

HEADER_SIZE = 32
PAIR_SLOT_SIZE = 8
PAIR_COUNT = 8
ENTRY_HEADER_SIZE = 32

# 地址字段打包方式：低 28 位是数据区地址，高 4 位是类型。
# Address packing: low 28 bits hold the payload address, high 4 bits hold the type.
ADDRESS_MASK = 0x0FFFFFFF
TYPE_SHIFT = 28

TYPE_REFERENCE = 0x0B  # 引用型：数据地址处是一条路径字符串
TYPE_DATA = 0x0F       # 数据型：数据区里嵌着内容，或指向尾部共享区

# names[] 里各槽位的语义（用于取实际路径名）
# Meaning of each slot in names[] (used to extract the real path name)
NAME_SLOT_KEY = 3     # 资源名（也是我们在 qpck 里查找用的名字）/ resource name
NAME_SLOT_EXISTS = 4  # 该槽位为 _EXISTS= 时表示这是一个存在性标记条目

# 用于 PRES 内部：表示这是引用链而非实体数据
EXISTS_MARKER = "_EXISTS="

_NAME_SLOT_INDEX = 1  # names[1] 存扩展名（如 "res"）/ names[1] holds the extension


class PresError(Exception):
    """PRES 相关异常的基类。Base class for PRES errors."""


class BadMagicError(PresError):
    """magic 不匹配。Magic mismatch."""


class InvalidStructureError(PresError):
    """结构不合法（例如偏移越界、setCount 不支持）。Malformed structure."""


def align16(value: int) -> int:
    """16 字节向上对齐。Round up to a 16-byte boundary."""
    return (value + 15) & ~15


def _u16(data: bytes, at: int) -> int:
    return struct.unpack_from("<H", data, at)[0]


def _u32(data: bytes, at: int) -> int:
    return struct.unpack_from("<I", data, at)[0]


def _i32(data: bytes, at: int) -> int:
    return struct.unpack_from("<i", data, at)[0]


def read_cstring(data: bytes, at: int) -> str:
    """从 at 处读一条以 NUL 结尾的 ASCII 字符串。Read a NUL-terminated ASCII string.

    PRES 里所有名字都是这种格式：一串 ASCII 字符 + 一个 0x00 结尾。
    All PRES names are stored this way: ASCII bytes followed by a 0x00 terminator.
    """
    end = data.find(b"\x00", at)
    if end < 0:
        raise InvalidStructureError(
            f"偏移 {at} 处的字符串没有 NUL 结尾（读到文件尾也没找到 0x00）/ "
            f"unterminated C string at offset {at}"
        )
    return data[at:end].decode("ascii")


@dataclass
class PresEntry:
    """PRES 中的一个条目（节点）。One entry (node) inside a PRES.

    每个条目代表一个资源节点，可能带若干"名字槽"，以及指向真实数据的方式。
    Each entry is a resource node carrying name slots and a way to reach the real data.

    字段 / Fields:
        type:        0x0B=引用型（RefPath 是另一条路径），0x0F=数据型（本地嵌数据或共享区）
        names:       名字槽数组；names[3] 是资源名，names[1] 是扩展名
        data_size:   数据大小
        decomp_size: 解压后大小（若数据被压缩）
        ref_path:    引用型条目指向的路径（type==0x0B 时有效）
        data:        数据型条目内嵌的字节内容
        exists_bitmap: _EXISTS= 条目的位图，用于判断某个子资源是否存在
    """
    type: int
    names: list[str] = field(default_factory=list)
    data_size: int = 0
    decomp_size: int = 0
    ref_path: str | None = None
    data: bytes | None = None
    exists_bitmap: bytes | None = None

    @property
    def resource_name(self) -> str | None:
        """该条目代表的资源名（names[3]），没有则返回 None。Resource name from names[3]."""
        if len(self.names) > NAME_SLOT_KEY:
            return self.names[NAME_SLOT_KEY]
        return None

    @property
    def extension(self) -> str | None:
        """扩展名（names[1]），没有则返回 None。Extension from names[1]."""
        if len(self.names) > _NAME_SLOT_INDEX:
            return self.names[_NAME_SLOT_INDEX]
        return None

    @property
    def is_reference(self) -> bool:
        """是否为引用型条目（指向另一条路径）。Whether this is a reference entry."""
        return self.type == TYPE_REFERENCE


@dataclass
class PresPair:
    """8 组 pair 中的一组。One of the 8 pairs in a set."""
    entries: list[PresEntry] = field(default_factory=list)


@dataclass
class PresSet:
    """一个 set，含 8 组 pair。A set holding 8 pairs."""
    pairs: list[PresPair] = field(default_factory=list)


@dataclass
class Pres:
    """一个完整的 PRES 资源树。A complete PRES resource tree."""
    format: int = 0
    version: int = 0
    package_id: int = 0
    flags: int = 0
    rdp_doff: int = 0
    rdp_size: int = 0
    body_length: int = 0
    set_count: int = 0
    sets: list[PresSet] = field(default_factory=list)
    shared_data: dict[str, bytes] = field(default_factory=dict)

    def all_entries(self) -> Iterator[PresEntry]:
        """遍历所有条目。Iterate over every entry in every pair of every set."""
        for s in self.sets:
            for pair in s.pairs:
                yield from pair.entries


def parse(data: bytes, *, strict: bool = True) -> Pres:
    """解析一段 PRES 字节。Parse a PRES blob.

    布局（与 REFERENCE 一致，已用真实数据验证）/ Layout (verified against real data):

        偏移 0   32 字节头部
                 +0  magic u32 = 0x73657250
                 +8  format u8
                 +9  version u8
                 +10 package_id u16
                 +12 flags u32
                 +16 body_length u32
                 +28 set_count i32

        set_count <= 1  ：只有一个 set，紧跟在头部之后（偏移 32）
        set_count 6 或 12：头部之后是 set_count 个 8 字节槽位，
                           每个槽位 = (该 set 的偏移 u32, 长度 u32)

        每个 set 内含 8 组 pair，每组 pair 一个 8 字节目录槽：
            (该 pair 的条目头数组偏移 u32, 条目数 u32)

        每个条目头 32 字节：
            +0  typeAndAddress u32   高 4 位=类型，低 28 位=数据区地址
            +4  data_size i32
            +8  name_table_at i32    名字指针数组的偏移
            +12 name_count i32
            +28 decompressed_size i32

    注意 setCount 的取值范围**：参考实现只接受 <=1 / 6 / 12 三种，其它一律抛错。
    这是一个"观察到的约束"而非格式必然，但我们照做，遇到异常值时能立刻发现新问题。
    """
    if len(data) < HEADER_SIZE:
        raise InvalidStructureError(
            f"PRES 数据仅 {len(data)} 字节，不足 {HEADER_SIZE} 字节头部 / "
            f"PRES blob too small: {len(data)}B < {HEADER_SIZE}B"
        )
    if _u32(data, 0) != MAGIC:
        raise BadMagicError(
            f"PRES magic 应为 / expected 0x{MAGIC:08X}，实际 / got 0x{_u32(data, 0):08X}"
        )

    pres = Pres(
        format=data[8],
        version=data[9],
        package_id=_u16(data, 10),
        flags=_u32(data, 12),
        rdp_doff=_u32(data, 20),
        rdp_size=_u32(data, 24),
        body_length=_u32(data, 16),
        set_count=_i32(data, 28),
    )

    set_count = pres.set_count
    shared: dict[str, bytes] = {}

    def _check(at: int, size: int, what: str) -> None:
        if at < 0 or size < 0 or at + size > len(data):
            raise InvalidStructureError(
                f"{what} 越界：偏移 {at}，长度 {size}，数据总长 {len(data)} / "
                f"{what} out of bounds: at={at} size={size} total={len(data)}"
            )

    if set_count <= 1:
        directory_at = HEADER_SIZE
        pres.sets.append(_parse_set(data, directory_at, 0, shared, _check))
    elif set_count in (6, 12):
        for i in range(set_count):
            slot = HEADER_SIZE + i * PAIR_SLOT_SIZE
            _check(slot, PAIR_SLOT_SIZE, f"set 槽位 / set slot {i}")
            directory_at = _i32(data, slot)
            pres.sets.append(_parse_set(data, directory_at, i, shared, _check))
    else:
        raise InvalidStructureError(
            f"不支持的 setCount={set_count}（参考实现只接受 <=1、6、12）/ "
            f"unsupported setCount {set_count} (reference accepts <=1, 6, 12)"
        )

    pres.shared_data = shared
    return pres


def _parse_set(
    data: bytes, directory_at: int, pair_count_hint: int, shared: dict[str, bytes], check
) -> PresSet:
    """解析一个 set（含 PAIR_COUNT=8 组 pair）。Parse one set (8 pairs)."""
    result = PresSet()
    for p in range(PAIR_COUNT):
        slot = directory_at + p * PAIR_SLOT_SIZE
        check(slot, PAIR_SLOT_SIZE, f"pair 槽位 / pair slot {p}")
        header_at = _i32(data, slot)
        count = _i32(data, slot + 4)

        pair = PresPair()
        if count > 0:
            check(header_at, count * ENTRY_HEADER_SIZE, f"pair {p} 的条目头数组 / entry headers")
            for e in range(count):
                pair.entries.append(_parse_entry(data, header_at + e * ENTRY_HEADER_SIZE, p, shared, check))
        result.pairs.append(pair)
    return result


def _parse_entry(
    data: bytes, at: int, pair_index: int, shared: dict[str, bytes], check
) -> PresEntry:
    """解析单个条目。Parse a single entry.

    伪代码 / Pseudocode:

        typeAddress = u32(at)                        # 打包字段
        entry.type  = typeAddress >> 28              # 高 4 位
        addr        = typeAddress & 0x0FFFFFFF       # 低 28 位
        data_size   = i32(at+4)
        nameTableAt = i32(at+8)                      # 名字指针数组的位置
        nameCount   = i32(at+12)
        decompSize  = i32(at+28)

        # 读名字：nameTableAt 处有 nameCount 个 u32 指针，每个指向一个 NUL 结尾字符串
        for i in 0 .. nameCount-1:
            nameAt = i32(nameTableAt + i*4)
            names[i] = cstring(data, nameAt)

        # 按类型取数据
        if type == 0x0B:                             # 引用型
            ref_path = cstring(data, addr)
        elif type == 0x0F:                           # 数据型
            if nameCount > 3:                        # names[3] 有效 -> 共享数据
                key = names[3]
                if key not in shared:
                    shared[key] = bytes(data[addr : addr+data_size])
                entry.data = shared[key]
            else:                                    # 本地载荷；pair 5 特例：长度 *4
                length = data_size * 4 if pairIndex == 5 else data_size
                entry.data = bytes(data[addr : addr+length])
    """
    check(at, ENTRY_HEADER_SIZE, "条目头 / entry header")

    type_address = _u32(data, at)
    entry_type = (type_address >> TYPE_SHIFT) & 0xF
    address = type_address & ADDRESS_MASK
    data_size = _i32(data, at + 4)
    name_table_at = _i32(data, at + 8)
    name_count = _i32(data, at + 12)
    decomp_size = _i32(data, at + 28)

    if name_count < 0:
        raise InvalidStructureError(f"条目 nameCount 为负 / negative nameCount {name_count}")

    entry = PresEntry(
        type=entry_type,
        data_size=data_size,
        decomp_size=decomp_size,
    )

    for i in range(name_count):
        ptr_at = name_table_at + i * 4
        check(ptr_at, 4, f"名字指针 / name pointer {i}")
        name_at = _i32(data, ptr_at)
        if name_at < 0 or name_at >= len(data):
            raise InvalidStructureError(
                f"名字 {i} 的指针 {name_at} 越界（数据长 {len(data)}）/ "
                f"name pointer {i} out of bounds: {name_at}"
            )
        entry.names.append(read_cstring(data, name_at))

    try:
        if entry_type == TYPE_REFERENCE:
            if address == 0:
                entry.ref_path = ""
            else:
                check(address, 1, "引用路径 / reference path")
                entry.ref_path = read_cstring(data, address)
        elif entry_type == TYPE_DATA:
            if name_count > NAME_SLOT_KEY:
                key = entry.names[NAME_SLOT_KEY]
                if key not in shared:
                    check(address, max(data_size, 0), f"共享数据 {key} / shared data")
                    shared[key] = bytes(data[address:address + data_size])
                entry.data = shared[key]
            else:
                # pair 5 的 dataSize 单位是 u32 而非字节，这是一条**观察到的特例规则**。
                # Observed special case: pair 5 counts dataSize in u32 units, not bytes.
                length = data_size * 4 if pair_index == 5 else data_size
                if length > 0:
                    check(address, length, "本地载荷 / local payload")
                    entry.data = bytes(data[address:address + length])
    except InvalidStructureError:
        if True:
            raise

    return entry


def iter_paths(pres: Pres) -> Iterator[str]:
    """遍历 PRES 树中出现的所有路径字符串。Yield every path string in the tree.

    两类来源 / Two sources:
        1. 引用型条目的 ref_path（指向另一个 PRES 或叶子资源）
        2. 名字槽 names[3] 里的资源名

    这些字符串就是构造"路径→哈希"名字表的原料。
    These strings are the raw material for building a path -> hash name map.
    """
    for entry in pres.all_entries():
        if entry.ref_path:
            yield entry.ref_path
        name = entry.resource_name
        if name:
            yield name


def build_name_map(pres: Pres) -> dict[int, str]:
    """由 PRES 树构建 hash -> 路径 映射。Build a hash -> path map from a PRES tree.

    这是解除"qpck 只有哈希没有文件名"死锁的关键函数。
    This is the function that unlocks the "qpck has hashes but no names" deadlock.

    返回的字典可直接传给 qpck.unpack_all(name_map=...) 让解包产物带上真实文件名。
    The result can be passed straight to qpck.unpack_all(name_map=...) so extracted
    files get real filenames.
    """
    mapping: dict[int, str] = {}
    for path in iter_paths(pres):
        try:
            mapping.setdefault(hash_path(path), path)
        except UnicodeEncodeError:
            # 非 ASCII 路径无法参与 CRC64（引擎用 ASCII）；跳过但不中断整体。
            # Non-ASCII paths cannot be CRC64'd (engine uses ASCII); skip, don't abort.
            continue
    return mapping
