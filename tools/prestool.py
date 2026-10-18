# -*- coding: utf-8 -*-
"""
prestool —— PRES 资源树的命令行工具（提供 names 子命令）。
prestool -- command-line tool for the PRES resource tree (provides the `names` command).

它解决什么问题 / What problem it solves
--------------------------------------
qpck 归档只存 CRC64 哈希、不存文件名。PRES 资源树里则有完整的路径字符串。
本工具从"入口 PRES"出发递归遍历整棵资源树，收集所有路径，产出名字表，
供 qpcktool 解包/打包时使用。
The qpck archive stores only CRC64 hashes, no filenames. The PRES resource tree contains
the full path strings. This tool starts from the entry PRES, recursively walks the tree,
collects every path, and emits a name map for qpcktool.

三个关键点 / Three key points
----------------------------
1. **递归**：只解析入口层只能拿到约 1488 条路径。真正的资源藏在子树里，
   必须沿着引用型条目（type 0x0B，带 RefPath）往下走。
   Recursion: the entry layer alone yields ~1488 paths; real resources live in sub-trees
   reached via reference entries (type 0x0B with a RefPath).

2. **BLZ4 解压**：部分资源被 BLZ4 容器包裹。解压后可以读取其真实内容。
   BLZ4: some resources are BLZ4-wrapped; decompressing exposes their real content.

3. **.rtbl 补充**：还有一大批资源是通过 .rtbl 引用表间接登记的，
   尤其是语音/音效事件类资源。PRES 树自身不包含它们。
   .rtbl: many resources are registered indirectly through .rtbl reference tables,
   notably voice and sound-event resources. The PRES tree alone omits them.

加载顺序与 mod 覆盖 / Load order and mod override
-----------------------------------------------
与游戏一致，按 bin_patch -> bin -> conf -> data 打开多个归档，同名的以靠前者为准。
Opens archives in engine order (bin_patch -> bin -> conf -> data), first wins.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Sequence

from gecv import blz4
from gecv.crc64 import hash_path
from gecv.pres import iter_paths, parse
from gecv.qpck import MultiArchive

PRES_MAGIC = bytes.fromhex("50726573")

LOAD_ORDER = ["bin_patch.qpck", "bin.qpck", "conf.qpck", "data.qpck"]
DEFAULT_ENTRY = "bin/resconv_pc/src/system/system.res"

# .rtbl 引用表：定长记录，每条 512 字节；路径字符串位于记录内偏移 0x20 处。
# .rtbl reference table: fixed 512-byte records; path string at record offset 0x20.
RTBL_RECORD_SIZE = 512
RTBL_PATH_AT = 0x20


def _human(n: int) -> str:
    step = 1024.0
    val = float(n)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if val < step or unit == "GiB":
            return f"{val:.2f} {unit}" if unit != "B" else f"{int(val)} B"
        val /= step
    return f"{val:.2f} GiB"


def collect_rtbl_paths(
    ma: MultiArchive, name_map: dict[int, str], stats: dict, found: dict
) -> None:
    """从 .rtbl 引用表里补充路径。Harvest extra paths from .rtbl reference tables.

    布局（据参考实现，已在本仓库真实数据上验证）/ Layout (verified against real data):
        定长记录，每条 512 字节；record[0] == 0 表示该条为空；
        有效记录的 offset+0x20 处是一条 NUL 结尾的路径字符串。
        Fixed 512-byte records; a leading zero byte marks an empty slot; valid records
        carry a NUL-terminated path string at offset+0x20.
    """
    targets = sorted({p for p in name_map.values() if p.endswith(".rtbl")})
    for path in targets:
        raw = ma.read_path(path)
        if not raw:
            continue
        if blz4.is_blz4(raw):
            try:
                raw = blz4.decompress(raw)
            except Exception:
                stats["unreadable"] += 1
                continue
        stats["rtbl_scanned"] += 1
        for off in range(0, len(raw), RTBL_RECORD_SIZE):
            if off >= len(raw) or raw[off] == 0:
                continue
            end = raw.find(b"\x00", off + RTBL_PATH_AT)
            if end < 0:
                continue
            try:
                ref = raw[off + RTBL_PATH_AT:end].decode("ascii")
            except UnicodeDecodeError:
                continue
            if ref:
                found.setdefault(ref, None)


def cmd_names(args: argparse.Namespace) -> int:
    """遍历 PRES 树并导出名字表。Walk the PRES tree and export a name map."""
    gamedir = args.gamedir
    archives = [os.path.join(gamedir, n) for n in LOAD_ORDER]
    existing = [p for p in archives if os.path.isfile(p)]
    if not existing:
        print(f"错误：{gamedir} 下找不到任何 qpck / no qpck found in {gamedir}", file=sys.stderr)
        return 2

    print(f"游戏目录 / game dir : {gamedir}")
    print(f"加载 / loading      : {', '.join(os.path.basename(p) for p in existing)}")
    ma = MultiArchive(existing, strict=False)

    paths: dict[int, str] = {}
    stats = {
        "pres_parsed": 0,
        "blz4_decompressed": 0,
        "unreadable": 0,
        "rtbl_scanned": 0,
        "rtbl_new": 0,
        "broken_pres": 0,
        "raw_bytes_prepared": 0,
    }
    visited: set[str] = set()

    def maybe_unwrap(data: bytes) -> bytes:
        """若数据是 BLZ4 容器则解压，否则原样返回。Unwrap BLZ4 if present."""
        if data and blz4.is_blz4(data):
            try:
                out = blz4.decompress(data)
                stats["blz4_decompressed"] += 1
                return out
            except Exception as exc:
                stats["unreadable"] += 1
                if args.verbose:
                    print(f"    [warn] BLZ4 解压失败 / decompress failed: {exc}")
                return b""
        return data

    entry_blob = ma.read_path(args.entry)
    if entry_blob is None:
        print(f"错误：找不到入口资源 / entry not found: {args.entry}", file=sys.stderr)
        return 2
    print(f"入口 / entry        : {args.entry} ({_human(len(entry_blob))})")
    entry_blob = maybe_unwrap(entry_blob)

    # 先收集 PRES 树里的路径。Collect paths from the PRES tree itself.
    seen_paths: set[str] = set()

    def walk_collect(blob: bytes, depth: int) -> None:
        """遍历一棵 PRES 树，把路径收集进 seen_paths。

        Walk one PRES tree, collecting its paths into seen_paths.

        !!! visited 去重至关重要 !!!
        !!! The visited dedup is essential !!!
        资源树里存在被多个父节点共享的子树。若不去重，同一棵子树会被重复遍历，
        遍历次数随共享程度指数增长 —— 表现为工具看似"卡住"，实则在做无用功。
        Subtrees are commonly shared by several parents. Without dedup the same subtree is
        walked again and again, and the walk count grows with sharing; the tool then appears
        to hang while doing redundant work.
        """
        try:
            pres = parse(blob)
        except Exception:
            return
        for p in iter_paths(pres):
            if p:
                seen_paths.add(p)
        if depth >= args.max_depth:
            return
        for entry in pres.all_entries():
            if not entry.ref_path:
                continue
            if not entry.ref_path.endswith((".res", ".blz")):
                continue
            if entry.ref_path in visited:
                continue
            visited.add(entry.ref_path)
            raw = ma.read_path(entry.ref_path)
            if not raw:
                continue
            stats["raw_bytes_prepared"] += len(raw)
            unwrapped = maybe_unwrap(raw)
            if len(unwrapped) >= 4 and unwrapped[:4] == PRES_MAGIC:
                walk_collect(unwrapped, depth + 1)
        stats["pres_parsed"] += 1

    # 单次遍历同时完成统计与收集。Walk once, collecting stats and paths together.
    stats_before = stats["pres_parsed"]
    walk_collect(entry_blob, 0)
    for p in seen_paths:
        try:
            paths.setdefault(hash_path(p), p)
        except UnicodeEncodeError:
            continue

    before_rtbl = len(paths)
    if args.rtbl:
        print()
        print("扫描 .rtbl 引用表 / scanning .rtbl reference tables ...")
        rtbl_found: dict[str, None] = {}
        collect_rtbl_paths(ma, paths, stats, rtbl_found)
        for ref in rtbl_found:
            try:
                paths.setdefault(hash_path(ref), ref)
            except UnicodeEncodeError:
                continue
        stats["rtbl_new"] = len(paths) - before_rtbl

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        for path in sorted(set(paths.values())):
            fh.write(path + "\n")

    print()
    print(f"  解析的 PRES 树 / parsed PRES   : {stats['pres_parsed']}")
    print(f"  解压的 BLZ4 容器 / BLZ4 blobs : {stats['blz4_decompressed']}")
    print(f"  失败跳过 / skipped            : BLZ4={stats['unreadable']} PRES={stats['broken_pres']}")
    if args.rtbl:
        print(f"  扫描的 .rtbl / rtbl scanned   : {stats['rtbl_scanned']}")
        print(f"  .rtbl 新增路径 / rtbl new     : {stats['rtbl_new']}")
    print(f"  唯一路径数 / unique paths     : {len(paths)}")
    print(f"  输出 / output                 : {args.out}")
    ma.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prestool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__,
        epilog="""
示例 / Examples
---------------
  # 只看 PRES 树 / PRES tree only
  python -m tools.prestool names --gamedir "H:/SteamLibrary/steamapps/common/GOD EATER RESURRECTION" \\
      --out work/names_ger.txt

  # 同时扫描 .rtbl（推荐，能多出数万条）/ also scan .rtbl (recommended, adds tens of thousands)
  python -m tools.prestool names --gamedir "H:/SteamLibrary/steamapps/common/GOD EATER RESURRECTION" \\
      --out work/names_ger_full.txt --rtbl

  # 用名字表解包 / Unpack using the name map
  python -m tools.qpcktool unpack <file.qpck> --out work/extracted --names work/names_ger_full.txt

退出码 / Exit codes
-------------------
  0  成功 / success
  2  用法错误或入口资源缺失 / usage error or missing entry
""",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    p_names = sub.add_parser(
        "names",
        help="递归遍历 PRES 树，导出路径名字表 / walk the PRES tree and export a name map",
        description=(
            "从入口 PRES 出发递归遍历资源树，产出一行一个路径的名字表。\n\n"
            "关键点 / Key points:\n"
            "  - 递归：沿引用型条目向下钻，只读入口层会漏掉绝大多数资源。\n"
            "  - BLZ4：资源常被 BLZ4 包裹，需先解压才能看到内容。\n"
            "  - --rtbl：额外扫描 .rtbl 引用表，能补出大量 PRES 树自身未登记的路径\n"
            "    （尤其是语音/音效事件类资源）。实测 GER 多出 25082 条。\n"
            "  - 加载顺序：bin_patch -> bin -> conf -> data，同名的以靠前者为准。\n\n"
            "名字表一行一个路径，可直接作为 qpcktool unpack --names 的输入。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_names.add_argument("--gamedir", required=True, help="游戏安装目录 / game install directory")
    p_names.add_argument("--out", required=True, help="输出的名字表文件 / output name map file")
    p_names.add_argument("--entry", default=DEFAULT_ENTRY, help="入口资源路径 / entry resource path")
    p_names.add_argument("--max-depth", type=int, default=8, help="最大递归深度 / max recursion depth")
    p_names.add_argument(
        "--rtbl",
        action="store_true",
        help="额外扫描 .rtbl 引用表以补充路径 / also scan .rtbl reference tables for extra paths",
    )
    p_names.add_argument("-v", "--verbose", action="store_true", help="显示跳过项的细节 / show skipped items")
    p_names.set_defaults(func=cmd_names)

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
