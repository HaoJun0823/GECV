# GECV

**GOD EATER PC 版格式研究与解析工具集**

[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-active-brightgreen.svg)](https://github.com/HaoJun0823/GECV/commits/main)

> 仓库由 CODE EATER 小组维护。格式文档为中文，暂不提供英文版。

---

## 中文

### 这是什么

GECV 是对《GOD EATER》（噬神者 / ゴッドイーター）PC 版数据结构的**逆向研究成果与配套解析工具**。

仓库包含两部分：

| 目录 | 内容 |
|---|---|
| [`docs/`](docs/) | 格式研究文档（**中文**）。这是本仓库的主体 |
| [`src/gecv/`](src/gecv/) | Python 解析库 |
| [`tools/`](tools/) | 命令行工具 |
| [`samples/`](samples/) | 可直接验证的小样本归档 |

**相关仓库**：早期版本见 [GECV-OLD](https://github.com/HaoJun0823/GECV-OLD)。

### 文档入口

文档均在 [`docs/`](docs/) 目录，**仅提供中文**。

建议从 [`docs/INDEX.md`](docs/INDEX.md) 开始——它按"读者想知道什么"分组，
而不是按文件名排列。

当前收录的格式：

| 格式 | 说明文档 |
|---|---|
| PRES 资源树 | [`docs/formats/pres.md`](docs/formats/pres.md) |
| PRES 逐字节实例 | [`docs/formats/pres-illustrated.md`](docs/formats/pres-illustrated.md) |
| 四种格式设计意图 | [`docs/formats/design-rationale.md`](docs/formats/design-rationale.md) |
| qpck 归档 | [`docs/formats/qpck.md`](docs/formats/qpck.md) |
| tr2 表格 | [`docs/formats/tr2-reading.md`](docs/formats/tr2-reading.md)、[`tr2-primary-key.md`](docs/formats/tr2-primary-key.md) |
| kst1 键值库 | [`docs/formats/kst1.md`](docs/formats/kst1.md) |
| 资源拓扑 | [`docs/topology.md`](docs/topology.md)、[`topology-graph.md`](docs/topology-graph.md) |
| 打包机制（谁套谁） | [`docs/packaging.md`](docs/packaging.md) |

### 环境

- Python 3.10 或更高
- 仅使用标准库，无第三方依赖

运行前需要让 Python 找到 `gecv` 包：

```bash
export PYTHONPATH=src          # Linux / macOS
set PYTHONPATH=src             # Windows (cmd)
$env:PYTHONPATH = "src"        # Windows (PowerShell)
```

### 快速开始

```bash
# 查看归档概览
python -m tools.qpcktool info <file.qpck>

# 解包（需要名字表才能还原文件名）
python -m tools.qpcktool unpack <file.qpck> --out out/

# 校验
python -m tools.qpcktool verify <file.qpck>
```

更详细的用法见各工具的 `--help`。仓库自带的 [`samples/`](samples/) 里有可直接试的小归档。

### 项目状态

| 项目 | 状态 |
|---|---|
| 格式文档 | 持续更新中 |
| 读取路径 | 已验证 |
| 写入路径 | 部分格式尚未实现 |

这是一份**仍在进行中**的研究成果，不是成品软件。文档中每一项结论都标注了证据等级
（实测 / 反汇编 / 参考 / 推测），未验证的部分会明确标出。

### 许可

本项目采用 **GNU General Public License v3.0 or later（GPL-3.0-or-later）**，
并附带额外条款。**这是强约束协议**，详见 [LICENSE](LICENSE)。

要点：

- 任何分发（含二进制）**必须**同时提供完整对应源码，且以同一协议授权
- **不得**改为更宽松或闭源协议
- **必须保留**对 CODE EATER 小组、qingyu0510 及贡献者的署名
- **不得**增加任何限制下游用户的额外条款

本项目**不包含任何游戏资源**。使用所需的游戏数据须来自你**自己合法持有的游戏副本**。

### 版权与致谢

- 原始内容（格式规格、研究结论、工具、文档）的知识产权归
  **CODE EATER 小组、qingyu0510 及相关贡献者**所有
- 《GOD EATER》系列及其全部素材、商标归其各自权利人
  （包括 BANDAI NAMCO Entertainment Inc.、SHIFT Inc.）所有
- 本项目与上述权利人**无任何隶属、授权或背书关系**

---

## English

### What this is

GECV is **reverse-engineering research and parsing tooling** for the on-disk
data structures of the PC versions of *GOD EATER* (GOD EATER RESURRECTION and
GOD EATER 2 Rage Burst).

Repository layout:

| Path | Contents |
|---|---|
| [`docs/`](docs/) | Format research documentation (**Chinese only**) |
| [`src/gecv/`](src/gecv/) | Python parsing library |
| [`tools/`](tools/) | Command-line tools |
| [`samples/`](samples/) | Small archives for verification |

**Related**: earlier work lives at [GECV-OLD](https://github.com/HaoJun0823/GECV-OLD).

> **Note on language**: the format documentation is written in Chinese and is
> **not** translated at this time. This README is the only bilingual document
> in the repository.

### Documentation

All docs live in [`docs/`](docs/) and are Chinese-only. Start at
[`docs/INDEX.md`](docs/INDEX.md), which is grouped by *what you want to know*
rather than by filename.

Formats currently covered:

| Format | Document |
|---|---|
| PRES resource tree | [`docs/formats/pres.md`](docs/formats/pres.md) |
| PRES byte-level walkthrough | [`docs/formats/pres-illustrated.md`](docs/formats/pres-illustrated.md) |
| Design rationale (4 formats) | [`docs/formats/design-rationale.md`](docs/formats/design-rationale.md) |
| qpck archive | [`docs/formats/qpck.md`](docs/formats/qpck.md) |
| tr2 tables | [`docs/formats/tr2-reading.md`](docs/formats/tr2-reading.md), [`tr2-primary-key.md`](docs/formats/tr2-primary-key.md) |
| kst1 key-value store | [`docs/formats/kst1.md`](docs/formats/kst1.md) |
| Resource topology | [`docs/topology.md`](docs/topology.md), [`topology-graph.md`](docs/topology-graph.md) |
| Packaging (what wraps what) | [`docs/packaging.md`](docs/packaging.md) |

### Requirements

- Python 3.10 or newer
- Standard library only — no third-party dependencies

The `gecv` package must be importable:

```bash
export PYTHONPATH=src          # Linux / macOS
set PYTHONPATH=src             # Windows (cmd)
$env:PYTHONPATH = "src"        # Windows (PowerShell)
```

### Quick start

```bash
# Inspect an archive
python -m tools.qpcktool info <file.qpck>

# Unpack (a name map is needed to recover real filenames)
python -m tools.qpcktool unpack <file.qpck> --out out/

# Verify
python -m tools.qpcktool verify <file.qpck>
```

See each tool's `--help` for details. The bundled [`samples/`](samples/)
directory contains small archives you can try immediately.

### Project status

| Area | Status |
|---|---|
| Format documentation | Continuously updated |
| Read paths | Verified |
| Write paths | Partially unimplemented |

This is **research in progress**, not finished software. Every claim in the
docs is tagged with an evidence grade (measured / disassembly / reference /
inferred), and unverified items are called out explicitly rather than presented
as fact.

### License

This project is licensed under **GNU General Public License v3.0 or later
(GPL-3.0-or-later)** with additional terms. **This is a strict, binding
license.** See [LICENSE](LICENSE).

Key points:

- Any distribution (including binaries) **must** ship the complete
  corresponding source under the same license
- You **may not** relicense under a more permissive or proprietary license
- You **must preserve** attribution to CODE EATER (CODE EATER 小组),
  qingyu0510, and contributors
- You **may not** impose additional restrictions on downstream recipients

This project contains **no game assets**. Any game data required must come from
**your own legally acquired copy** of the game.

### Copyright and credits

- All intellectual property in the original content (format specifications,
  research findings, tooling, documentation) belongs to **CODE EATER
  (CODE EATER 小组), qingyu0510, and contributors**
- *GOD EATER* and all related titles, assets, and trademarks are the property
  of their respective rights holders, including BANDAI NAMCO Entertainment Inc.
  and SHIFT Inc.
- This project has **no affiliation with, endorsement by, or sponsorship from**
  those rights holders
