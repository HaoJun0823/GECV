# -*- coding: utf-8 -*-
"""
restopo —— 资源打包机制的拓扑分析工具（提供 modules / domains 两个子命令）。
restopo -- resource-topology analyser (provides the `modules` and `domains` commands).

它解决什么问题 / What problem it solves
--------------------------------------
「res 包套 res 包」这件事在直觉上像一棵树，实测却不是：上万个 PRES 里 95%
被多个父节点引用，是一张高度共享的 DAG。本工具把这张图聚合成**人能读的两张表**：

1. `modules` —— 把 PRES 按目录聚合成模块，统计模块之间的引用边，
   回答「谁套谁」。`enemy` 这种出边为 0 的是纯资源，
   `event` / `mission` 这种出边巨大的是调度者。
   Aggregates PRES by directory into modules and counts cross-module edges.
   Zero-out-degree modules (e.g. `enemy`) are pure assets;
   high-out-degree ones (`event`, `mission`) are schedulers.

2. `domains` —— 把命名资源按业务域（武器 / 服装 / 关卡 / 道具 / 任务 …）分组，
   统计每域的规模与格式构成，回答「哪类业务在哪、用什么格式」。
   Groups named resources into business domains (weapon / costume / field /
   item / mission …) and reports size and format mix per domain.

输入 / Inputs
-------------
- `modules`: 拓扑图 JSON，即 prestool 类的遍历产物，结构为
  `{"nodes": {path: {...}}, "edges": [{"from","to","channel"}], "fan_in": {...}}`。
  仓库的 `work/` 目录不入版本库，所以图文件需要你自己先生成；
  本工具只负责解读，不负责遍历。
- `domains`: 名字表，一行一条资源路径（`prestool names` 的输出即可）。

两者都是**只读分析**，不修改任何输入。

用法 / Usage
------------
    python -m tools.restopo modules --graph GER.v2.graph.json
    python -m tools.restopo domains --names names_ger_full.txt
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
from typing import Sequence

# 路径前缀：所有 PRES 路径都挂在这一层下面，打印时剥掉以节省宽度。
# Prefix shared by every PRES path; stripped when printing to save width.
PATH_PREFIX = "bin/resconv_pc/"

# 业务域判定规则：按列表顺序优先，互斥（先命中者胜）。
# Order matters: rules are evaluated top-down and are mutually exclusive.
DOMAINS: list[tuple[str, str]] = [
    ("任务 mission",   r"/mission/"),
    ("场景 field",     r"/field/"),
    ("怪物 enemy",     r"/enemy/|/Enemy/|effect/Enemy/"),
    ("NPC / 剧情角色",  r"/npc/|/NPC/|/g998_Result/|event/Demo/"),
    ("玩家服装 Male",   r"/player/Male/"),
    ("玩家服装 Female", r"/player/Female/"),
    ("玩家共通",       r"/player/(Base|Eye|Motion|Voice|Accessory|PredatorArts)/"),
    ("武器 Weapon",    r"/player/Weapon/|/Arms/"),
    ("特效 effect",    r"/effect/"),
    ("UI 菜单 menu",   r"/menu/|/layout/|/Locale/"),
    ("音效 voice/se",  r"/sound/"),
    ("脚本 script",    r"/script/"),
    ("数据库 db/tr2",  r"/db/|/Tr2/|\.tr2"),
    ("Buff/子弹",      r"/oracle/|/bullet/|/Bullet/"),
]


def strip_prefix(path: str) -> str:
    """剥掉公共前缀。Strip the shared path prefix."""
    return path[len(PATH_PREFIX):] if path.startswith(PATH_PREFIX) else path


def module_of(path: str) -> str:
    """把 PRES 路径归到一个模块名。Map a PRES path to a module name.

    `src/<module>/...`       -> `src/<module>`
    `data/GameData/<x>/...`  -> `data/<x>`
    """
    parts = strip_prefix(path).split("/")
    if parts[0] == "src":
        return "src/" + (parts[1] if len(parts) > 1 else "?")
    if len(parts) >= 3 and parts[0] == "data" and parts[1] == "GameData":
        return "data/" + parts[2]
    return "/".join(parts[:3])


def load_graph(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def unique_edges(graph: dict) -> list[tuple[str, str]]:
    """取两端都在节点集里的边，去重、去自环。
    Keep edges whose endpoints are both known nodes; dedupe, drop self-loops.
    """
    nodes = graph.get("nodes", {})
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for e in graph.get("edges", []):
        a, b = e.get("from"), e.get("to")
        if a in nodes and b in nodes and a != b and (a, b) not in seen:
            seen.add((a, b))
            out.append((a, b))
    return out


def cmd_modules(args: argparse.Namespace) -> int:
    graph = load_graph(args.graph)
    nodes = graph.get("nodes", {})
    edges = unique_edges(graph)

    print(f"PRES 节点 {len(nodes)}   有效边 {len(edges)}")

    mod_nodes = collections.Counter(module_of(p) for p in nodes)
    mod_out = collections.Counter()
    mod_in = collections.Counter()
    cross = collections.Counter()
    for a, b in edges:
        ma, mb = module_of(a), module_of(b)
        mod_out[ma] += 1
        mod_in[mb] += 1
        if ma != mb:
            cross[(ma, mb)] += 1

    print(f"\n{'模块':<24}{'PRES数':>7}{'出边':>7}{'入边':>7}")
    print("-" * 60)
    mods = sorted(set(mod_nodes) | set(mod_out) | set(mod_in),
                  key=lambda m: (-mod_nodes.get(m, 0), m))
    for m in mods:
        print(f"{m:<24}{mod_nodes.get(m, 0):>7}{mod_out.get(m, 0):>7}"
              f"{mod_in.get(m, 0):>7}")

    print(f"\n--- 跨模块边 top {args.top}（父 -> 子）---")
    shown = 0
    for (a, b), v in cross.most_common():
        if shown >= args.top:
            break
        print(f"  {v:>6}  {a}  ->  {b}")
        shown += 1

    if args.packages:
        print("\n--- 顶层包（packageId != 0）直接引用的子模块 ---")
        tops = [(p, n) for p, n in nodes.items() if n.get("package_id")]
        tops.sort(key=lambda x: -x[1].get("size", 0))
        for p, n in tops:
            kids = [b for a, b in edges if a == p]
            print(f"\n  0x{n['package_id']:04X}  {strip_prefix(p)}"
                  f"  ({n.get('size', 0)} B, 直接子 PRES {len(kids)})")
            kc = collections.Counter(module_of(k) for k in kids)
            for m, v in kc.most_common(8):
                print(f"        {v:>5}  {m}")
    return 0


def ext_of(path: str) -> str:
    base = path.rsplit("/", 1)[-1]
    if "." not in base:
        return "(none)"
    return base.rsplit(".", 1)[-1].lower()


def cmd_domains(args: argparse.Namespace) -> int:
    with open(args.names, encoding="utf-8") as f:
        names = [l.strip() for l in f if l.strip()]

    print(f"命名资源 {len(names)}")

    exts = collections.Counter(ext_of(n) for n in names)
    print(f"\n扩展名 top {args.top}:")
    for e, c in exts.most_common(args.top):
        print(f"  {c:>7}  {e}")

    print(f"\n{'业务域':<18}{'数量':>7}   主要格式")
    print("-" * 78)
    used: set[str] = set()
    for label, rx in DOMAINS:
        r = re.compile(rx)
        hits = [n for n in names if n not in used and r.search(n)]
        used.update(hits)
        if not hits:
            continue
        ec = collections.Counter(ext_of(n) for n in hits)
        top = ", ".join(f"{e}:{c}" for e, c in ec.most_common(5))
        print(f"{label:<18}{len(hits):>7}   {top}")

    rest = [n for n in names if n not in used]
    ec = collections.Counter(ext_of(n) for n in rest)
    print(f"{'未归类':<18}{len(rest):>7}   "
          f"{', '.join(f'{e}:{c}' for e, c in ec.most_common(5))}")

    if args.samples:
        print("\n--- 样本（每域若干条）---")
        used2: set[str] = set()
        for label, rx in DOMAINS:
            r = re.compile(rx)
            hits = [n for n in names if n not in used2 and r.search(n)]
            used2.update(hits)
            if not hits:
                continue
            print(f"\n  [{label}]  计 {len(hits)}")
            for n in sorted(hits)[:args.samples]:
                print(f"      {n}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="restopo",
        description="资源打包机制的拓扑分析（模块聚合 / 业务域普查）。",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("modules", help="按目录聚合 PRES，统计模块间引用边")
    m.add_argument("--graph", required=True, help="拓扑图 JSON 路径")
    m.add_argument("--top", type=int, default=25, help="跨模块边显示条数")
    m.add_argument("--packages", action="store_true",
                   help="额外列出顶层包的子模块构成")
    m.set_defaults(func=cmd_modules)

    d = sub.add_parser("domains", help="按业务域普查命名资源")
    d.add_argument("--names", required=True, help="名字表（一行一条路径）")
    d.add_argument("--top", type=int, default=14, help="扩展名显示条数")
    d.add_argument("--samples", type=int, default=0,
                   help="每域打印的样本条数，0 为不打印")
    d.set_defaults(func=cmd_domains)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
