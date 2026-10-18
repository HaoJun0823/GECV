# -*- coding: utf-8 -*-
"""
qpck —— 引擎的资源归档容器格式（God Eater RESURRECTION / GE2RB 共用）。
qpck -- the engine's resource archive container (shared by God Eater RESURRECTION / GE2RB).

文件整体布局 / Overall file layout
---------------------------------
    +---------------------------+  偏移 0
    | magic      u32  LE        |  0x37402858
    | count      i32  LE        |  TOC 条目数
    +---------------------------+  偏移 8
    | TOC[0]  offset i64 LE     |
    |         hash   u64 LE     |  每条 20 字节
    |         length i32 LE     |
    | TOC[1]  ...               |
    | ...                       |
    +---------------------------+  偏移 8 + count*20
    | 数据块 0（TOC[0] 指向）   |
    | 数据块 1（TOC[1] 指向）   |  连续存放，无对齐填充（已验证）
    | ...                       |
    +---------------------------+  EOF

关键事实与验证状态 / Key facts and verification status
----------------------------------------------------
| 事实                                   | 状态   | 依据                          |
|----------------------------------------|--------|-------------------------------|
| magic = 0x37402858                     | 已验证 | 两个版本的 conf.qpck 实测      |
| count 为 i32（有符号）                 | 已验证 | 同上，与 C# ReadInt32 一致     |
| 条目 = offset i64 + hash u64 + len i32 | 已验证 | 20 字节步长，样本自洽          |
| 数据区紧随 TOC，无填充                 | 已验证 | 样本：8+count*20 == 首个 offset |
| 数据块按 TOC 顺序连续排布             | 已验证 | 每个 offset == 上一块的末尾     |
| 整个文件无空洞，末块末尾 == 文件大小   | 已验证 | 样本 end == size               |
| TOC 按 hash 升序排列                   | 已验证 | 两个样本均为升序               |
| hash = CRC64(归一化路径，ASCII)        | 已验证 | 见 crc64 模块说明              |
| 游戏/引擎用什么算法查 TOC              | 未验证 | 有序性暗示可能是二分查找，未证实 |

为什么"TOC 有序"很重要 / Why TOC ordering matters
------------------------------------------------
有序性强烈暗示引擎用二分查找（O(log n)）而不是线性扫描来定位资源——考虑到
bin.qpck 有数十万条目，线性扫描会很慢。但这只是合理推测，**未验证**。
实际的保守做法：我们打包时一律按 hash 升序输出，这样无论引擎是二分还是线性扫描
都能正确工作，同时也与真实样本字节一致（可往返比对）。
Ordering strongly hints the engine binary-searches (O(log n)) rather than linearly scans --
bin.qpck holds hundreds of thousands of entries, where linear scan would be slow. This is
plausible inference but UNVERIFIED. Our conservative policy: always emit entries sorted by
hash ascending, which works under either lookup strategy and stays byte-identical to real
samples (enabling round-trip comparison).

"多重归档覆盖"语义（mod 的基础）/ Multi-archive override semantics (basis of modding)
----------------------------------------------------------------------------------
引擎按固定顺序加载多个 qpck，加载时若同一 hash 已存在，则**保留先出现的、忽略后出现的**
（先入为主）。因此 bin_patch.qpck 放在最前面即可覆盖 bin.qpck 中的同名资源。
多条队伍: 加载顺序：bin_patch.qpck -> bin.qpck -> conf.qpck -> data.qpck
本模块提供 MultiArchive 来复现这个语义。
"""

from __future__ import annotations

import json
import os
import struct
from dataclasses import dataclass
from typing import BinaryIO, Iterable, Iterator, Sequence

from .crc64 import hash_path

__all__ = [
    "MAGIC",
    "HEADER_SIZE",
    "TOC_ENTRY_SIZE",
    "Entry",
    "QpckError",
    "BadMagicError",
    "TruncatedError",
    "LengthMismatchError",
    "EntryOutOfBoundsError",
    "read_toc",
    "validate_layout",
    "open_archive",
    "MultiArchive",
    "unpack_all",
    "pack_entries",
    "pack_from_manifest",
    "load_name_map",
    "build_name_map",
]

MAGIC = 0x37402858
HEADER_SIZE = 8
TOC_ENTRY_SIZE = 20

_COPY_BUFSIZE = 1 << 20


class QpckError(Exception):
    """qpck 相关异常的基类。Base class for qpck errors."""


class BadMagicError(QpckError):
    """文件头 magic 不匹配。Header magic mismatch."""


class TruncatedError(QpckError):
    """文件长度不足以容纳声明的结构。File too short for the declared structure."""


class LengthMismatchError(QpckError):
    """文件大小与数据区推算的末尾不一致。File size disagrees with computed data end."""


class EntryOutOfBoundsError(QpckError):
    """某个条目指向了文件之外。An entry points outside the file."""


@dataclass(frozen=True)
class Entry:
    """一条 TOC 记录。One TOC record.

    offset: 该数据块在文件中的绝对偏移（字节）。
    hash:   资源路径的 CRC64，是这条记录的键。
    length: 数据块长度（字节）。
    """
    offset: int
    hash: int
    length: int

    @property
    def end(self) -> int:
        """数据块末尾（不含）。Exclusive end of the data block."""
        return self.offset + self.length


def copy_range(src: BinaryIO, offset: int, length: int, dst: BinaryIO) -> int:
    """把文件的 [offset, offset+length) 区间拷到另一个文件对象，返回实际拷贝字节数。

    Copy [offset, offset+length) from src into dst; return bytes copied.
    用固定 1MiB 缓冲分块拷贝，因此单个 1GB 的资源也不会把内存撑爆。
    Uses a fixed 1 MiB buffer so even a 1 GB resource never blows up memory.
    """
    remaining = length
    src.seek(offset)
    copied = 0
    while remaining > 0:
        chunk = src.read(min(_COPY_BUFSIZE, remaining))
        if not chunk:
            break
        dst.write(chunk)
        remaining -= len(chunk)
        copied += len(chunk)
    return copied


def read_toc(path: str, *, strict: bool = True) -> list[Entry]:
    """读取一个 qpck 文件的头部与 TOC，返回条目列表。Read header + TOC; return entries.

    只读取文件开头的 (8 + count*20) 字节，不做任何数据区的 IO。因此对 6.8GB 的
    bin.qpck 来说，这个函数也是毫秒级、几乎不占内存的。
    Only the leading (8 + count*20) bytes are read -- no data-area IO. So even for the
    6.8 GB bin.qpck this is milliseconds and nearly memory-free.

    strict=True 时会校验：magic、count 合理性、首块偏移、每块是否越界、是否连续、
    末尾是否等于文件大小。任一项不符即抛异常（异常信息带具体偏移，便于定位）。
    Any failure raises with concrete offsets so you can locate the byte that broke.
    """
    size = os.path.getsize(path)
    if size < HEADER_SIZE:
        raise TruncatedError(f"{path}: 文件仅 {size} 字节，连 8 字节头部都不够 / too small for header")

    with open(path, "rb") as fh:
        raw = fh.read(HEADER_SIZE)
        magic, count = struct.unpack("<Ii", raw)
        if magic != MAGIC:
            raise BadMagicError(
                f"{path}: magic 应为 / expected 0x{MAGIC:08X}，实际 / got 0x{magic:08X}"
            )
        if count < 0:
            raise TruncatedError(f"{path}: count={count} 为负数 / negative count")

        data_start = HEADER_SIZE + count * TOC_ENTRY_SIZE
        if data_start > size:
            raise TruncatedError(
                f"{path}: count={count} 需要 {data_start} 字节的头部+TOC，"
                f"但文件只有 {size} 字节 / need {data_start}B for header+TOC but file is {size}B"
            )

        toc_bytes = fh.read(count * TOC_ENTRY_SIZE)
        entries: list[Entry] = []
        for i in range(count):
            base = i * TOC_ENTRY_SIZE
            offset, hash_value, length = struct.unpack_from("<qQi", toc_bytes, base)
            global_pos = HEADER_SIZE + base
            if offset < 0:
                raise EntryOutOfBoundsError(
                    f"{path}: TOC[{i}]（文件偏移 / at file offset {global_pos}）"
                    f" 偏移为负 / negative offset {offset}"
                )
            if length < 0:
                raise EntryOutOfBoundsError(
                    f"{path}: TOC[{i}]（文件偏移 / at {global_pos}）长度为负 / negative length {length}"
                )
            if offset + length > size:
                raise EntryOutOfBoundsError(
                    f"{path}: TOC[{i}] 指向 [{offset}, {offset + length})，"
                    f"超出文件大小 {size} / beyond file size {size}"
                )
            entries.append(Entry(offset=offset, hash=hash_value, length=length))

        if strict:
            validate_layout(entries, size, path=path, data_start=data_start)
        return entries


def validate_layout(
    entries: Sequence[Entry], size: int, *, path: str = "<qpck>", data_start: int | None = None
) -> dict:
    """校验布局自洽性并返回一份统计报告。Validate layout consistency; return a stats report.

    检查项（均已意识到这些是"样本规律"而非格式强制约束，但保持它们有助于发现问题）：
    Checks (recognized as observed sample regularities, not format-enforced rules, but useful):

        1. 首个数据块的偏移 == data_start（TOC 之后没有任何填充）
        2. 数据块严格按 TOC 顺序首尾相接
        3. 最后一块的末尾 == 文件大小（文件尾无多余字节）
        4. TOC 按 hash 升序
        5. 是否存在重复 hash

    返回字典包含上述各项的布尔结果与 count/data_size 等统计量；
    违反 1/2/3 会抛异常（这些关系到能否正确读取），4/5 只记录不抛错
    （引擎的先入为主语义意味着重复本身可能合法，但我们需要知道）。
    Violating 1/2/3 raises (they affect correctness); 4/5 are only recorded, because the
    first-wins override semantics means duplicates may be legitimate -- but we must know.
    """
    if data_start is None:
        data_start = HEADER_SIZE + len(entries) * TOC_ENTRY_SIZE

    report: dict = {
        "count": len(entries),
        "data_start": data_start,
        "size": size,
        "sorted_by_hash": True,
        "duplicate_hashes": [],
        "contiguous": True,
    }
    if not entries:
        report["data_end"] = data_start
        report["no_padding"] = True
        return report

    if entries[0].offset != data_start:
        raise LengthMismatchError(
            f"{path}: 首个数据块偏移 {entries[0].offset} != 头部+TOC 之后的 {data_start}，"
            f"说明 TOC 与数据区之间存在 {entries[0].offset - data_start} 字节未知内容 / "
            f"unexpected gap between TOC and data"
        )

    cursor = data_start
    for i, e in enumerate(entries):
        if e.offset != cursor:
            report["contiguous"] = False
            raise LengthMismatchError(
                f"{path}: TOC[{i}] 偏移 {e.offset} != 预期的连续位置 {cursor}"
                f"（差 {e.offset - cursor} 字节）/ non-contiguous data area"
            )
        cursor = e.end

    if cursor != size:
        raise LengthMismatchError(
            f"{path}: 数据区推算末尾 {cursor} != 文件大小 {size}"
            f"（文件尾部有 {size - cursor} 字节未解释内容）/ trailing bytes after last block"
        )
    report["data_end"] = cursor

    hashes = [e.hash for e in entries]
    report["sorted_by_hash"] = hashes == sorted(hashes)

    seen: set[int] = set()
    for h in hashes:
        if h in seen and h not in report["duplicate_hashes"]:
            report["duplicate_hashes"].append(h)
        seen.add(h)

    report["no_padding"] = True
    return report


class QpckArchive:
    """单个 qpck 归档的只读视图。Read-only view of a single qpck archive.

    惰性读取：构造时只读 TOC，真正取数据时才 seek+read。这使得打开一个数 GB 的
    归档是恒定的低成本操作。
    Lazy: only the TOC is read at construction; data is seek+read on demand, so opening a
    multi-GB archive stays cheap.
    """

    def __init__(self, path: str, *, strict: bool = True) -> None:
        self.path = path
        self.entries = read_toc(path, strict=strict)
        self._by_hash: dict[int, Entry] = {}
        for e in self.entries:
            # 先入为主：同一 hash 重复出现时保留第一条。
            # First wins: keep the first occurrence if a hash repeats.
            self._by_hash.setdefault(e.hash, e)
        self._fh: BinaryIO | None = None

    def __enter__(self) -> QpckArchive:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        """关闭底层文件句柄。Close the underlying file handle."""
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def _ensure_open(self) -> BinaryIO:
        if self._fh is None:
            self._fh = open(self.path, "rb")
        return self._fh

    def __len__(self) -> int:
        return len(self._by_hash)

    @property
    def hashes(self) -> list[int]:
        """所有去重后的 hash（按 TOC 中的出现顺序）。All deduplicated hashes in TOC order."""
        return list(self._by_hash.keys())

    def contains_hash(self, hash_value: int) -> bool:
        """该 hash 是否存在。Whether the hash exists."""
        return hash_value in self._by_hash

    def contains_path(self, path: str) -> bool:
        """给定资源路径是否存在（走 CRC64 归一化）。Whether a resource path exists."""
        return self.contains_hash(hash_path(path))

    def get_entry(self, hash_value: int) -> Entry | None:
        """取 TOC 记录，不存在返回 None。Get the TOC record, or None."""
        return self._by_hash.get(hash_value)

    def read_hash(self, hash_value: int) -> bytes | None:
        """读取该 hash 对应的完整数据到内存。不存在返回 None。

        Read the full data for a hash into memory; None if absent.
        注意：这会一次性分配 length 字节。超大资源请用 open_hash_stream()。
        Note: allocates `length` bytes at once. Use open_hash_stream() for huge entries.
        """
        e = self._by_hash.get(hash_value)
        if e is None:
            return None
        fh = self._ensure_open()
        fh.seek(e.offset)
        data = fh.read(e.length)
        if len(data) != e.length:
            raise TruncatedError(
                f"{self.path}: 期望读 {e.length} 字节但只读到 {len(data)}"
                f"（文件被截断？）/ short read, file truncated?"
            )
        return data

    def read_path(self, path: str) -> bytes | None:
        """按资源路径读取（内部会做 CRC64 归一化）。Read by resource path."""
        return self.read_hash(hash_path(path))

    def open_hash_stream(self, hash_value: int, target: BinaryIO) -> int:
        """把一个条目流式拷到目标文件对象，返回拷贝字节数。

        Stream-copy an entry into a target file object; return bytes copied.
        内存占用恒定为 1MiB，适合 GB 级条目。
        Constant 1 MiB memory; suitable for GB-scale entries.
        """
        e = self._by_hash.get(hash_value)
        if e is None:
            return 0
        return copy_range(self._ensure_open(), e.offset, e.length, target)


def open_archive(path: str, *, strict: bool = True) -> QpckArchive:
    """打开一个 qpck 归档。Open a qpck archive."""
    return QpckArchive(path, strict=strict)


class MultiArchive:
    """把多个 qpck 合并成一个虚拟归档，复现引擎的"先入为主"覆盖语义。

    Combine several qpck archives into one virtual archive reproducing the engine's
    first-wins override semantics. 这就是 bin_patch.qpck 能覆盖 bin.qpck 的原理。
    This is exactly how bin_patch.qpck overrides bin.qpck.

    用法 Usage::

        ma = MultiArchive([r"H:/.../bin_patch.qpck", r"H:/.../bin.qpck"])
        data = ma.read_path("system/resident/foo.bin")
    """

    def __init__(self, paths: Iterable[str], *, strict: bool = True) -> None:
        self.archives: list[QpckArchive] = []
        self._by_hash: dict[int, QpckArchive] = {}
        for p in paths:
            arc = QpckArchive(p, strict=strict)
            self.archives.append(arc)
            for h in arc.hashes:
                # setdefault 保证靠前归档优先 / guarantees earlier archive wins.
                self._by_hash.setdefault(h, arc)

    def __enter__(self) -> MultiArchive:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        for arc in self.archives:
            arc.close()

    def __len__(self) -> int:
        return len(self._by_hash)

    def read_path(self, path: str) -> bytes | None:
        """按路径读取，返回 None 表示所有归档里都没有。Read by path; None if absent."""
        return self.read_hash(hash_path(path))

    def read_hash(self, hash_value: int) -> bytes | None:
        arc = self._by_hash.get(hash_value)
        return arc.read_hash(hash_value) if arc else None

    def contains_path(self, path: str) -> bool:
        return hash_path(path) in self._by_hash


SourceItem = int | bytes | tuple[str, int, int]


def load_name_map(path: str) -> dict[int, str]:
    """从文本文件加载 hash -> 路径 的映射（每行一个路径）。

    Load a hash -> path map from a text file (one path per line).
    '# ' 开头与空行会被忽略；重复路径自动去重。
    Lines starting with '# ' and blank lines are ignored; duplicates collapse naturally.
    """
    mapping: dict[int, str] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            mapping.setdefault(hash_path(line), line)
    return mapping


def build_name_map(paths: Iterable[str]) -> dict[int, str]:
    """由一组路径直接构建 hash -> 路径 映射。Build a hash -> path map from paths."""
    return {hash_path(p): p for p in paths}


def unpack_all(
    archive: QpckArchive,
    out_dir: str,
    *,
    name_map: dict[int, str] | None = None,
    manifest_name: str = "manifest.jsonl",
) -> dict:
    """把归档解包到目录，并写一份 manifest.jsonl 记录每个条目的元信息。

    Unpack an archive into a directory, writing manifest.jsonl with per-entry metadata.

    文件命名规则 / Naming rules:
        - 若该 hash 在 name_map 中有对应路径，则按真实路径落盘（并创建子目录）
        - 否则落到 `_unnamed/<hash 16 位大写十六进制>.bin`
    为什么必须写 manifest：
        qpck 只存 hash 不存文件名，没有 manifest 就无法保证"原样重新打包"。
        manifest 记录了原始 offset/length/顺序，是往返一致的地基。
    """
    if name_map is None:
        name_map = {}
    os.makedirs(out_dir, exist_ok=True)
    unnamed_dir = os.path.join(out_dir, "_unnamed")
    made_unnamed = False

    manifest_path = os.path.join(out_dir, manifest_name)
    stats = {"total": 0, "named": 0, "unnamed": 0, "bytes": 0}

    source_abs = os.path.abspath(archive.path)
    with open(manifest_path, "w", encoding="utf-8") as mf:
        mf.write(
            json.dumps({"source_qpck": source_abs}, ensure_ascii=False) + "\n"
        )
        for e in archive.entries:
            name = name_map.get(e.hash)
            if name is not None:
                rel = name.replace("\\", "/").lstrip("/")
                named = True
            else:
                rel = f"_unnamed/{e.hash:016X}.bin"
                named = False
                if not made_unnamed:
                    os.makedirs(unnamed_dir, exist_ok=True)
                    made_unnamed = True

            dst_path = os.path.join(out_dir, *rel.split("/"))
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            wrote = 0
            with open(dst_path, "wb") as dst:
                wrote = copy_range(archive._ensure_open(), e.offset, e.length, dst)

            stats["total"] += 1
            stats["named" if named else "unnamed"] += 1
            stats["bytes"] += wrote

            mf.write(
                json.dumps(
                    {
                        "hash": f"{e.hash:016X}",
                        "offset": e.offset,
                        "length": e.length,
                        "name": name,
                        "out": rel,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    archive.close()
    return stats


def pack_entries(
    items: Iterable[tuple[int, SourceItem]],
    out_path: str,
    *,
    sort_by_hash: bool = True,
) -> dict:
    """把 (hash, 数据源) 序列打包成一个 qpck 文件。

    Pack a sequence of (hash, source) pairs into a qpck file.

    数据源 source 可以是三种形式之一 / A source may be one of three forms:
        1. bytes / bytearray       —— 已在内存里的数据
        2. (文件路径, 偏移, 长度)   —— 从另一个文件流式拷贝（支持 GB 级条目）
        3. 未实现的其它类型         —— 抛 TypeError

    默认 sort_by_hash=True：按 hash 升序输出，理由见模块文档顶部。
    这样处理同时保证：(a) 与真实样本字节一致，可往返比对；(b) 兼容二分查找。
    """
    entries = list(items)

    if sort_by_hash:
        entries.sort(key=lambda kv: kv[0])

    # 去重：先入为主，与 read_toc / MultiArchive 的语义保持一致。
    # Deduplicate first-wins, consistent with read_toc / MultiArchive.
    seen: set[int] = set()
    deduped: list[tuple[int, SourceItem]] = []
    dropped = 0
    for h, src in entries:
        if h in seen:
            dropped += 1
            continue
        seen.add(h)
        deduped.append((h, src))

    def _length_of(src: SourceItem) -> int:
        if isinstance(src, (bytes, bytearray, memoryview)):
            return len(src)
        if isinstance(src, tuple) and len(src) == 3:
            return int(src[2])
        raise TypeError(f"不支持的数据源类型 / unsupported source type: {type(src)!r}")

    data_start = HEADER_SIZE + TOC_ENTRY_SIZE * len(deduped)
    offset = data_start
    layout: list[tuple[int, int, int, SourceItem]] = []
    for h, src in deduped:
        length = _length_of(src)
        layout.append((h, offset, length, src))
        offset += length

    parent = os.path.dirname(os.path.abspath(out_path))
    if parent:
        os.makedirs(parent, exist_ok=True)

    total_bytes = 0
    with open(out_path, "wb") as out:
        out.write(struct.pack("<Ii", MAGIC, len(deduped)))
        for h, blk_offset, length, _src in layout:
            out.write(struct.pack("<qQi", blk_offset, h, length))

        open_files: dict[str, BinaryIO] = {}
        try:
            for _h, blk_offset, length, src in layout:
                if isinstance(src, (bytes, bytearray, memoryview)):
                    out.write(bytes(src))
                    total_bytes += len(src)
                else:
                    path, src_off, src_len = src
                    if path not in open_files:
                        open_files[path] = open(path, "rb")
                    wrote = copy_range(open_files[path], int(src_off), int(src_len), out)
                    if wrote != int(src_len):
                        raise TruncatedError(
                            f"{path}: 期望复制 {src_len} 字节，实际 {wrote} / short copy"
                        )
                    total_bytes += wrote
        finally:
            for fh in open_files.values():
                fh.close()

    return {
        "path": out_path,
        "count": len(deduped),
        "dropped_duplicates": dropped,
        "data_bytes": total_bytes,
        "size": data_start + total_bytes,
    }


def pack_from_manifest(
    manifest_path: str,
    *,
    out_path: str,
    prefer_named: bool = True,
) -> dict:
    """依据 unpack_all 生成的 manifest.jsonl 重新打包。Repack from a manifest.

    这是保证"解包 -> 原样打包 -> 字节完全一致"的推荐路径。
    This is the recommended path guaranteeing unpack -> repack -> byte-identical output.

    数据源直接引用原 qpck 文件的对应区间（流式拷贝），因此整个过程内存占用恒定，
    可用于 GB 级归档。
    Data comes from the original qpck via streamed range copies, so memory stays constant
    and this scales to GB-sized archives.

    manifest 需要含 source_qpck 字段（由 CLI 写入），或由 unpack_all 记录的原 qpck 路径。
    The manifest must include a `source_qpck` field (written by the CLI).
    """
    items: list[tuple[int, SourceItem]] = []
    source_qpck: str | None = None
    with open(manifest_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            rec = json.loads(line)
            if rec.get("source_qpck"):
                source_qpck = rec["source_qpck"]
                continue
            h = int(rec["hash"], 16)
            items.append((h, (source_qpck, int(rec["offset"]), int(rec["length"]))))

    if source_qpck is None:
        raise QpckError(
            f"{manifest_path}: manifest 缺少 source_qpck 字段，无法定位原始归档 / "
            f"missing source_qpck, cannot locate original archive"
        )
    return pack_entries(items, out_path, sort_by_hash=prefer_named)
