# -*- coding: utf-8 -*-
"""
ksttool —— kst1 数据库的命令行工具（查看 / 导出 / 按 key 查询）。
ksttool -- command-line tool for kst1 databases (inspect / export / query by key).

它解决什么问题 / What problem it solves
--------------------------------------
kst1 是引擎的键值数据库，装着任务、文本、角色数据等真正的游戏内容。
本工具从 qpck 归档里取出 kst1（必要时解 BLZ4），自动发现字符串列，
导成人类可读的 JSON / TSV，或按 key 精确查询。
kst1 is the engine's key-value DB holding real game content. This tool pulls kst1 out of
qpck archives (unwrapping BLZ4 when needed), auto-discovers the text columns, and exports
readable JSON/TSV or resolves a key precisely.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Sequence

from gecv import blz4, kst1
from gecv.crc64 import hash_path
from gecv.qpck import MultiArchive, load_name_map

LOAD_ORDER = ["bin_patch.qpck", "bin.qpck", "conf.qpck", "data.qpck"]


def _human(n: int) -> str:
    step = 1024.0
    val = float(n)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if val < step or unit == "GiB":
            return f"{val:.2f} {unit}" if unit != "B" else f"{int(val)} B"
        val /= step
    return f"{val:.2f} GiB"


def _open_archive(gamedir: str) -> MultiArchive:
    paths = [os.path.join(gamedir, n) for n in LOAD_ORDER]
    existing = [p for p in paths if os.path.isfile(p)]
    if not existing:
        raise SystemExit(f"错误：{gamedir} 下找不到任何 qpck / no qpck found")
    return MultiArchive(existing, strict=False)


def _load_db(ma: MultiArchive, path: str) -> kst1.Kst1:
    raw = ma.read_path(path)
    if raw is None:
        raise SystemExit(f"错误：归档里找不到 {path} / not found in archives")
    if blz4.is_blz4(raw):
        raw = blz4.decompress(raw)
    return kst1.Kst1(raw)


def _find_kst_paths(ma: MultiArchive, name_map: dict[int, str]) -> list[str]:
    """找出所有 kst 资源路径。Find all kst resource paths."""
    cands = {v for v in name_map.values() if ".kst" in v}
    out = []
    for p in sorted(cands):
        raw = ma.read_path(p)
        if not raw:
            continue
        if blz4.is_blz4(raw):
            try:
                raw = blz4.decompress(raw)
            except Exception:
                continue
        if raw[:4] == b"kst1":
            out.append(p)
    return out


def cmd_info(args: argparse.Namespace) -> int:
    """显示一个 kst1 的结构摘要。Show the structural summary of one kst1."""
    ma = _open_archive(args.gamedir)
    try:
        db = _load_db(ma, args.path)
    finally:
        pass

    print(f"文件 / File      : {args.path}")
    print(f"大小 / Size      : {_human(len(db.data))}")
    print(f"version          : {db.version}  (须为 0 / must be 0)")
    print(f"stride           : {db.stride} 字节/记录 / bytes per record")
    print(f"numrecord        : {db.numrecord}")
    print(f"index_off        : 0x{db.index_off:X}")
    print(f"record_off       : 0x{db.record_off:X}")
    print(f"numBlocks        : {db.numblocks}")
    print(f"maxKey           : {db.maxkey}")
    rec_end = db.record_off + db.numrecord * db.stride
    print(f"记录表结束       : 0x{rec_end:X}   文本区大小 / text region: "
          f"{_human(len(db.data) - rec_end)}")

    print()
    cols = db.string_columns
    print(f"自动发现的字符串列 / string columns: {cols}")
    if cols:
        for pos in cols:
            sample = None
            for i in range(min(db.numrecord, 200)):
                t = kst1.read_kst_string(db.data, db.dword(i, pos))
                if t:
                    sample = t
                    break
            print(f"  dword[{pos}]  例 / e.g. {sample!r}")

    present = db.count_present_keys()
    print()
    print(f"索引置位总数     : {present}")
    print(f"与 numrecord 一致: {present == db.numrecord}")
    ma.close()
    return 0


def cmd_sample(args: argparse.Namespace) -> int:
    """抽样打印若干条记录。Print a few records."""
    ma = _open_archive(args.gamedir)
    db = _load_db(ma, args.path)
    cols = db.string_columns
    print(f"{args.path}  stride={db.stride} numrecord={db.numrecord} cols={cols}")

    for i in range(min(args.count, db.numrecord)):
        strings = db.strings_of_record(i)
        head = db.dword(i, 0)
        print(f"\nrec{i}  dword[0]=0x{head:08X} "
              f"(line={head & 0xFFFF}, type={(head >> 16) & 0xFF})")
        if not strings:
            print("   (无字符串 / no strings)")
        for pos, text in strings.items():
            print(f"   [{pos}] {text}")
    ma.close()
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """导出全部（或指定范围）记录。Export all (or a slice of) records."""
    ma = _open_archive(args.gamedir)

    if args.all:
        name_map = load_name_map(args.names) if args.names else {}
        if not name_map:
            raise SystemExit("错误：--all 需要 --names 名字表 / --all requires --names")
        paths = _find_kst_paths(ma, name_map)
        print(f"发现 kst1 文件 / found {len(paths)} kst1 files")
    else:
        if not args.path:
            raise SystemExit("错误：需要 --path 或 --all / need --path or --all")
        paths = [args.path]

    os.makedirs(args.out, exist_ok=True)
    total_records = 0

    for path in paths:
        try:
            db = _load_db(ma, path)
        except Exception as exc:
            print(f"  跳过 / skip {path}: {exc}")
            continue

        safe = path.replace("\\", "/").lstrip("/").replace("/", "__")
        base = os.path.splitext(safe)[0]
        out_path = os.path.join(args.out, base + "." + args.format)

        rows = []
        for i in range(db.numrecord):
            strings = db.strings_of_record(i)
            rows.append({
                "index": i,
                "strings": {str(k): v for k, v in strings.items()},
                "dwords": [db.dword(i, p) for p in range(db.stride // 4)]
                if args.with_dwords else None,
            })
        total_records += len(rows)

        if args.format == "json":
            payload = {
                "source": path,
                "version": db.version,
                "stride": db.stride,
                "numrecord": db.numrecord,
                "string_columns": db.string_columns,
                "records": rows,
            }
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=1)
        elif args.format == "tsv":
            cols = db.string_columns
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write("index\t" + "\t".join(f"col{c}" for c in cols) + "\n")
                for r in rows:
                    cells = [r["strings"].get(str(c), "") for c in cols]
                    cells = [c.replace("\t", " ").replace("\n", "\\n") for c in cells]
                    fh.write(f"{r['index']}\t" + "\t".join(cells) + "\n")
        else:
            raise SystemExit(f"未知格式 / unknown format: {args.format}")

        named = sum(1 for r in rows if r["strings"])
        print(f"  {path}")
        print(f"    -> {out_path}  ({len(rows)} 条, {named} 条有文本)")

    print(f"\n合计导出 / total records: {total_records}")
    print(f"输出目录 / output dir   : {args.out}")
    ma.close()
    return 0


def cmd_key(args: argparse.Namespace) -> int:
    """按 key 查询记录（走索引表）。Resolve a key through the index table."""
    ma = _open_archive(args.gamedir)
    db = _load_db(ma, args.path)

    print(f"{args.path}  numrecord={db.numrecord} maxKey={db.maxkey}")
    for key in args.keys:
        rec = db.record_by_key(key)
        if rec is None:
            print(f"\nkey={key} -> 不存在 / not present")
            continue
        print(f"\nkey={key} -> record[{rec['index']}]")
        for pos, text in rec["strings"].items():
            print(f"   [{pos}] {text}")
    ma.close()
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """对全部 kst1 做结构自检。Structural self-check across every kst1."""
    ma = _open_archive(args.gamedir)
    name_map = load_name_map(args.names)
    paths = _find_kst_paths(ma, name_map)
    print(f"kst1 文件数 / count: {len(paths)}\n")
    print(f"{'file':<44} {'stride':>6} {'recs':>7} {'present':>8} {'ok':>4}  cols")
    print("-" * 110)

    all_ok = True
    for path in paths:
        try:
            db = _load_db(ma, path)
            present = db.count_present_keys()
            ok = present == db.numrecord
            cols = ",".join(str(c) for c in db.string_columns)
            print(f"{os.path.basename(path):<44} {db.stride:>6} {db.numrecord:>7} "
                  f"{present:>8} {str(ok):>4}  {cols}")
            if not ok:
                all_ok = False
        except Exception as exc:
            all_ok = False
            print(f"{os.path.basename(path):<44} ERROR: {exc}")

    print()
    print(f"全部通过 / all passed: {all_ok}")
    ma.close()
    return 0 if all_ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ksttool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__,
        epilog="""
示例 / Examples
---------------
  # 查看结构（自动发现字符串列）/ Inspect structure
  python -m tools.ksttool info --gamedir "<game>" --path "bin/resconv_pc/data/Locale/exported/en/article.kst.blz"

  # 抽样打印 / Print a few records
  python -m tools.ksttool sample --gamedir "<game>" --path "<kst>" --count 10

  # 导出全部 kst1 为 JSON / Export every kst1 to JSON
  python -m tools.ksttool export --gamedir "<game>" --all --names work/names_ger_full.txt --out out --format json

  # 按 key 查询 / Resolve a key
  python -m tools.ksttool key --gamedir "<game>" --path "<kst>" 255 256

  # 全部 kst1 结构自检 / Structural self-check on all kst1
  python -m tools.ksttool verify --gamedir "<game>" --names work/names_ger_full.txt

退出码 / Exit codes
-------------------
  0  成功 / success
  1  校验失败 / verification failed
  2  用法错误 / usage error
""",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    def add_common(p, path_required=True):
        p.add_argument("--gamedir", required=True, help="游戏安装目录 / game install directory")
        if path_required:
            p.add_argument("--path", required=True, help="kst 资源路径 / kst resource path")

    p_info = sub.add_parser("info", help="结构摘要 / structural summary",
                            description="读取头部、索引表，并自动发现字符串列。")
    add_common(p_info)
    p_info.set_defaults(func=cmd_info)

    p_sample = sub.add_parser("sample", help="抽样打印记录 / print sample records",
                              description="打印前 N 条记录的字符串列内容与首字段。")
    add_common(p_sample)
    p_sample.add_argument("--count", type=int, default=5, help="打印条数 / how many")
    p_sample.set_defaults(func=cmd_sample)

    p_export = sub.add_parser("export", help="导出为 JSON/TSV / export to JSON or TSV",
                              description="导出单个 kst1，或用 --all 导出全部（需 --names）。")
    p_export.add_argument("--gamedir", required=True, help="游戏安装目录 / game directory")
    p_export.add_argument("--path", help="单个 kst 资源路径 / one kst path")
    p_export.add_argument("--all", action="store_true", help="导出全部 kst1 / export all")
    p_export.add_argument("--names", help="名字表（--all 时必需）/ name map (required for --all)")
    p_export.add_argument("--out", required=True, help="输出目录 / output directory")
    p_export.add_argument("--format", choices=("json", "tsv"), default="json",
                          help="输出格式 / output format")
    p_export.add_argument("--with-dwords", action="store_true",
                          help="JSON 里附带全部 dword / include raw dwords")
    p_export.set_defaults(func=cmd_export)

    p_key = sub.add_parser("key", help="按 key 查记录 / resolve keys",
                           description="用索引表把 key 映射为记录序号并打印内容。")
    add_common(p_key)
    p_key.add_argument("keys", nargs="+", type=int, help="要查询的 key / keys to resolve")
    p_key.set_defaults(func=cmd_key)

    p_verify = sub.add_parser("verify", help="全部 kst1 自检 / self-check all kst1",
                              description="检查每个 kst1 的索引置位总数是否等于 numrecord。")
    p_verify.add_argument("--gamedir", required=True, help="游戏安装目录 / game directory")
    p_verify.add_argument("--names", required=True, help="名字表 / name map")
    p_verify.set_defaults(func=cmd_verify)

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
