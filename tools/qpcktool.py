# -*- coding: utf-8 -*-
"""
qpcktool —— qpck 归档的命令行工具（查看 / 解包 / 打包 / 校验）。
qpcktool -- command-line tool for qpck archives (inspect / unpack / pack / verify).

设计约束 / Design constraint
----------------------------
本文件是"薄层"：只负责解析命令行参数、组织调用、打印结果。
所有的格式知识都在 gecv.qpck / gecv.crc64 里，CLI 不重复实现任何二进制逻辑。
这样做的好处是：库可以在测试/其它工具里复用，CLI 只是其中一个入口。
This file is intentionally thin: it parses arguments, orchestrates calls, prints results.
All format knowledge lives in gecv.qpck / gecv.crc64; the CLI duplicates no binary logic.
That keeps the library reusable from tests and other tools.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Sequence

from gecv.crc64 import hash_path
from gecv.qpck import (
    Entry,
    MultiArchive,
    open_archive,
    pack_entries,
    pack_from_manifest,
    unpack_all,
    validate_layout,
)

LOAD_ORDER = ["bin_patch.qpck", "bin.qpck", "conf.qpck", "data.qpck"]
_UNNAMED = "_unnamed"


def _fmt_hash(h: int) -> str:
    return f"{h:016X}"


def _human(n: int) -> str:
    step = 1024.0
    val = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if val < step or unit == "TiB":
            return f"{val:.2f} {unit}" if unit != "B" else f"{int(val)} B"
        val /= step
    return f"{val:.2f} TiB"


def cmd_info(args: argparse.Namespace) -> int:
    """打印 qpck 的头部/TOC 摘要与布局校验结果。Print header/TOC summary and layout checks."""
    entries: list[Entry] = open_archive(args.file, strict=False).entries
    size = os.path.getsize(args.file)
    report = validate_layout(entries, size, path=args.file)

    print(f"文件 / File     : {args.file}")
    print(f"大小 / Size     : {size} 字节 / bytes ({_human(size)})")
    print(f"条目数 / Count  : {report['count']}")
    print(f"数据区起点      : {report['data_start']}")
    print(f"数据区大小      : {_human(max(0, size - report['data_start']))}")
    print()
    print(f"  [{'OK' if report.get('no_padding') else '??'}] TOC 之后无填充 / no gap after TOC")
    print(f"  [{'OK' if report['contiguous'] else '!!'}] 数据块连续 / data blocks contiguous")
    print(f"  [{'OK' if report['sorted_by_hash'] else '!!'}] TOC 按 hash 升序 / TOC sorted by hash")
    dup = report["duplicate_hashes"]
    print(f"  [{'!!' if dup else 'OK'}] 重复 hash 数量 / duplicate hashes: {len(dup)}")
    if dup and args.verbose:
        for h in dup[:20]:
            print(f"        {_fmt_hash(h)}")

    if args.list:
        print()
        print(f"{'#':>5}  {'OFFSET':>16}  {'LENGTH':>12}  {'HASH':>16}")
        for i, e in enumerate(entries[: args.limit]):
            print(f"{i:>5}  {e.offset:>16}  {e.length:>12}  {_fmt_hash(e.hash)}")
        if len(entries) > args.limit:
            print(f"  ... 还有 {len(entries) - args.limit} 条（用 --limit 调整）/ "
                  f"{len(entries) - args.limit} more (use --limit)")
    return 0


def cmd_unpack(args: argparse.Namespace) -> int:
    """解包 qpck 到目录（可选提供名字表），并生成 manifest.jsonl。Unpack with manifest."""
    name_map: dict[int, str] = {}
    if args.names:
        from gecv.qpck import load_name_map

        name_map = load_name_map(args.names)

    arc = open_archive(args.file, strict=not args.lax)
    print(f"解包 / Unpacking {args.file}")
    print(f"  条目数 / entries : {len(arc.entries)}")
    print(f"  名字表 / names   : {len(name_map)}")

    stats = unpack_all(arc, args.out, name_map=name_map or None)
    print()
    print(f"  已写出 / written : {stats['total']}")
    print(f"  有名   / named   : {stats['named']}")
    print(f"  无名   / unnamed : {stats['unnamed']}"
          + ("  -> " + os.path.join(args.out, _UNNAMED)) if stats["unnamed"] else "")
    print(f"  字节数 / bytes   : {_human(stats['bytes'])}")
    print()
    print(f"manifest -> {os.path.join(args.out, 'manifest.jsonl')}")
    if stats["unnamed"]:
        print()
        print("提示 / Note: qpck 只存 hash 不存文件名，未匹配到名字的条目按 hash 命名落盘。")
        print("          提供 --names <文件>（每行一个资源路径）即可还原真实文件名。")
        print("          名字可由其它层（如 PRES 资源树）导出，这是后续工作的一部分。")
    return 0


def cmd_pack(args: argparse.Namespace) -> int:
    """打包：支持 manifest 驱动（推荐，保证往返一致）与名字表驱动两种模式。Pack a qpck."""
    if args.manifest:
        print(f"按 manifest 打包 / Packing from manifest: {args.manifest}")
        result = pack_from_manifest(args.manifest, out_path=args.out)
    elif args.names:
        from gecv.qpck import load_name_map

        name_map = load_name_map(args.names)
        print(f"按名字表打包 / Packing from name list: {args.names} ({len(name_map)} 条)")
        root = args.root
        items = []
        missing = 0
        for h, name in name_map.items():
            src_path = os.path.join(root, name.replace("\\", "/").lstrip("/"))
            if not os.path.isfile(src_path):
                missing += 1
                continue
            items.append((h, (src_path, 0, os.path.getsize(src_path))))
        if missing:
            print(f"  跳过缺失文件 / skipped missing: {missing}")
        result = pack_entries(items, args.out, sort_by_hash=not args.keep_order)
    else:
        print("错误：pack 需要 --manifest 或 --names 之一 / "
              "error: pack requires either --manifest or --names", file=sys.stderr)
        return 2

    print()
    print(f"  输出 / output  : {result['path']}")
    print(f"  条目 / count   : {result['count']}")
    print(f"  去重丢弃       : {result['dropped_duplicates']}")
    print(f"  大小 / size    : {_human(result['size'])}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """往返验证：解包目录 -> 重新打包 -> 与原件逐字节比对。Round-trip byte comparison."""
    manifest_path = os.path.join(args.dir, "manifest.jsonl")
    if not os.path.isfile(manifest_path):
        print(f"错误：找不到 {manifest_path}，请先用 unpack 解包 / "
              f"error: missing manifest, unpack first", file=sys.stderr)
        return 2

    tmp_out = args.tmp or os.path.join(args.dir, "_repacked.qpck")
    print("往返验证 / Round-trip verification")
    print(f"  原归档 / original : {args.file}")
    print(f"  重打包 / repack   : {tmp_out}")

    result = pack_from_manifest(manifest_path, out_path=tmp_out)

    if args.source:
        # 与原 qpck 比对 / compare against the source archive
        src_size = os.path.getsize(args.source)
        if src_size != result["size"]:
            print(f"  [FAIL] 大小不同 / size differs: {src_size} vs {result['size']}")
            return 1
        print("  逐字节比对 / byte-by-byte compare ...")
        h1 = hashlib.sha256()
        h2 = hashlib.sha256()
        with open(args.source, "rb") as a, open(tmp_out, "rb") as b:
            while True:
                ba = a.read(1 << 20)
                bb = b.read(1 << 20)
                if not ba and not bb:
                    break
                h1.update(ba)
                h2.update(bb)
        same = h1.hexdigest() == h2.hexdigest()
        print(f"  [{'OK' if same else 'FAIL'}] SHA256 一致 / identical: {same}")
        print(f"      original : {h1.hexdigest()}")
        print(f"      repacked : {h2.hexdigest()}")
        return 0 if same else 1

    print("  （未指定 --source，跳过字节比对）/ no --source given; skipped comparison")
    return 0


def cmd_hash(args: argparse.Namespace) -> int:
    """计算资源路径的 CRC64（用于理解名字 -> hash 的映射）。Print CRC64 of a path."""
    for p in args.paths:
        h = hash_path(p)
        if args.json:
            print(json.dumps({"path": p, "crc64": _fmt_hash(h), "int": h}, ensure_ascii=False))
        else:
            print(f"{_fmt_hash(h)}  {p}")
    return 0


def cmd_cat(args: argparse.Namespace) -> int:
    """按路径从多重归档中取出一个资源（模拟引擎加载顺序）。Fetch one resource by path."""
    gamedir = args.gamedir
    paths = [os.path.join(gamedir, n) for n in LOAD_ORDER]
    existing = [p for p in paths if os.path.isfile(p)]
    if not existing:
        print(f"错误：{gamedir} 下找不到任何已知的 qpck / no known qpck found", file=sys.stderr)
        return 2

    print(f"加载顺序 / load order: {', '.join(os.path.basename(p) for p in existing)}")
    ma = MultiArchive(existing, strict=False)
    data = ma.read_path(args.path)
    if data is None:
        print(f"未找到 / not found: {args.path}  (CRC64={_fmt_hash(hash_path(args.path))})")
        return 1
    print(f"找到 / found: {len(data)} 字节 / bytes")
    if args.output:
        with open(args.output, "wb") as fh:
            fh.write(data)
        print(f"已写出 / written -> {args.output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qpcktool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__,
        epilog="""
示例 / Examples
---------------
  # 查看归档基本信息 / Inspect an archive
  python -m tools.qpcktool info samples/conf.resurrection.qpck --list

  # 解包到目录（生成 manifest.jsonl 以便原样打包）/ Unpack (emits manifest.jsonl)
  python -m tools.qpcktool unpack assets/data/000000.qpck --out work/extracted

  # 由解包目录重新打包（保证往返一致）/ Repack from an extracted dir
  python -m tools.qpcktool pack --manifest work/extracted/manifest.jsonl --out work/new.qpck

  # 往返验证：重打包后与原文件逐字节比对 / Verify round-trip byte equality
  python -m tools.qpcktool verify assets/data/000000.qpck --dir work/extracted --source assets/data/000000.qpck

  # 计算某个资源路径的 CRC64（排查资源到底是哪个 hash）/ CRC64 of a path
  python -m tools.qpcktool hash system/resident/actor_table.bin

  # 模拟引擎加载顺序，从游戏目录取一个资源 / Fetch a resource the way the engine does
  python -m tools.qpcktool cat "system/resident/actor_table.bin" --gamedir "<游戏安装目录>"

退出码 / Exit codes
-------------------
  0  成功 / success
  1  校验失败（例如往返字节不一致）/ verification failed
  2  用法错误 / usage error
""",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    p_info = sub.add_parser(
        "info",
        help="查看归档头部、TOC 与布局自洽性 / show header, TOC and layout checks",
        description="读取 qpck 的 magic/count/TOC，并校验「数据区 TOC 之后紧贴、连续、无尾部多余字节、按 hash 升序」这几条样本规律。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_info.add_argument("file", help="qpck 文件路径 / path to the qpck file")
    p_info.add_argument("--list", action="store_true", help="列出 TOC 条目 / list TOC entries")
    p_info.add_argument("--limit", type=int, default=50, help="最多列出多少条 / max rows to list")
    p_info.add_argument("-v", "--verbose", action="store_true", help="显示重复 hash 明细 / show duplicate hashes")
    p_info.set_defaults(func=cmd_info)

    p_unpack = sub.add_parser(
        "unpack",
        help="把 qpck 解包到目录（同时写 manifest.jsonl）/ extract entries to a directory and write manifest.jsonl",
        description="""把归档里的每个条目写成独立文件。

重要 / IMPORTANT: qpck 只存 CRC64 哈希，**不存文件名**。因此：
  - 提供了 --names（每行一个资源路径）时，命中 hash 的条目按真实路径落盘；
  - 未命中的落到 _unnamed/<HEX>.bin。
manifest.jsonl 记录每条的 hash/offset/length/名字/输出路径，配合 verify 可用来
确认"原样重新打包"是否字节一致。名字表本身需要从资源树导出，这是独立的后续工作。""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_unpack.add_argument("file", help="qpck 文件 / source qpck")
    p_unpack.add_argument("--out", required=True, help="输出目录 / output directory")
    p_unpack.add_argument("--names", help="名字表文件（每行一个资源路径）/ name list file")
    p_unpack.add_argument("--lax", action="store_true", help="放宽布局校验 / relax layout validation")
    p_unpack.set_defaults(func=cmd_unpack)

    p_pack = sub.add_parser(
        "pack",
        help="把文件打包成 qpck / build a qpck from files",
        description="""两种模式，推荐第一种 / Two modes; the first is recommended:

  1) --manifest ：由 unpack 生成的 manifest.jsonl 驱动。
     数据直接从原归档流式拷贝，内存占用恒定，且严格按原顺序重建，
     是"往返字节一致"的保证路径。
  2) --names + --root ：由名字表驱动，把 --root 目录下对应路径的文件打包。
     用于制作 mod 补丁包（产出可直接放进游戏的 .qpck）。

两种模式都默认按 hash 升序输出（与真实样本一致；用 --keep-order 关闭），
并对重复 hash 执行"先入为主"去重。""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_pack.add_argument("--manifest", help="manifest.jsonl 路径（unpack 生成）/ manifest path")
    p_pack.add_argument("--names", help="名字表文件 / name list file")
    p_pack.add_argument("--root", default=".", help="配合 --names 的根目录 / root dir for --names")
    p_pack.add_argument("--out", required=True, help="输出的 qpck 路径 / output qpck path")
    p_pack.add_argument("--keep-order", action="store_true", help="不按 hash 排序 / do not sort by hash")
    p_pack.set_defaults(func=cmd_pack)

    p_verify = sub.add_parser(
        "verify",
        help="往返验证：重打包后与原文件逐字节比对 / round-trip verification with byte comparison",
        description="""这是保障"改代码不会悄悄破坏格式"的核心手段。

流程：读 <dir>/manifest.jsonl -> 重新打包成 qpck -> 与 --source 指定的原文件
计算 SHA256 并比对。两者一致说明我们对格式的理解是自洽且可复原的。""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_verify.add_argument("file", help="原始 qpck（用于读 TOC）/ original qpck (for TOC)")
    p_verify.add_argument("--dir", required=True, help="unpack 产出的目录 / extracted directory")
    p_verify.add_argument("--source", help="要比对的原始 qpck，通常与 <file> 相同 / original to compare against")
    p_verify.add_argument("--tmp", help="重打包临时输出路径 / temporary repack output path")
    p_verify.set_defaults(func=cmd_verify)

    p_hash = sub.add_parser(
        "hash",
        help="计算资源路径的 CRC64 / print the CRC64 of resource paths",
        description="""打印每个路径归一化后的 CRC64。用于：
  - 确认某个资源是否就在某个 hash 条目里；
  - 反向调试：手头有一个 hash，想知道它可能对应什么路径时挨个试。

归一化规则：反斜杠转正斜杠、去前导斜杠、转大写、ASCII 编码。""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_hash.add_argument("paths", nargs="+", help="资源路径 / resource paths")
    p_hash.add_argument("--json", action="store_true", help="JSON 输出 / JSON output")
    p_hash.set_defaults(func=cmd_hash)

    p_cat = sub.add_parser(
        "cat",
        help="按资源路径从游戏加载链中取出数据 / fetch one resource through the load chain",
        description="""按引擎的加载顺序打开多个归档（先入为主），再按路径取数据：

    bin_patch.qpck -> bin.qpck -> conf.qpck -> data.qpck

这条链正是 mod 覆盖生效的机制：把改过的资源放进最前面的 archive 即可覆盖原版。""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_cat.add_argument("path", help="资源路径 / resource path")
    p_cat.add_argument("--gamedir", required=True, help="游戏安装目录 / game install directory")
    p_cat.add_argument("-o", "--output", help="写出到文件 / write to file")
    p_cat.set_defaults(func=cmd_cat)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
