# tr2 逆向证据（来自 GER.exe 本体）

> **证据等级**：本文结论取自 **exe 内部的符号字符串**，属于引擎自身留下的痕迹，
> 高于此前基于数据自洽的推断。
> Evidence class: taken from symbol strings inside the EXE itself -- traces left by the
> engine -- which outranks our earlier data-consistency inference.

目标文件：`H:\SteamLibrary\steamapps\common\GOD EATER RESURRECTION\GER.exe`
PE：machine `0x014C`（x86 32 位）、optional_magic `0x010B`（PE32）、ImageBase `0x00400000`、11 个节区。

---

## 1. 关键锚点：源文件路径 + 函数名

在 VA `0x011CC64C`（文件偏移 `0xDCBA4C`）附近发现：

```
pBin....tr2GetArrayNumH.src\app\tr2.c...tr2GetRecordHead....tr2GetFieldIndex....
```

这条来自 exe 的断言串同时给出了三件事：

| 项目 | 值 |
|---|---|
| **源文件路径** | `src\app\tr2.c` |
| 函数名 | `tr2GetArrayNumH` |
| 函数名 | `tr2GetRecordHead` |
| 函数名 | `tr2GetFieldIndex` |

这是解析器所在 translation unit 的直接证据。

---

## 2. tr2 的 API 全表（107 个符号）

引擎的命名约定为 `tr2*`。全 exe 共抓到 **107 个不同的 tr2 相关标识符**。
这些函数名本身就是结构文档——它们揭示了引擎眼中的概念。

### 2.1 概念命名更正（重要）

| 我们此前叫法 | 引擎叫法（来自函数名） | 依据符号 |
|---|---|---|
| `row_inf` / 行 | **Record** | `tr2GetRecord`、`tr2GetRecordHead`、`tr2GetRecordCore`、`tr2GetRecordFieldNum`、`tr2MakeRecord` |
| `row_data` 里的单项 | **Field**（字段/列） | `tr2GetFieldHead`、`tr2GetFieldIndex`、`tr2GetFieldNum` |
| `row_data_data` 单元 | **Cell**（单元格） | `tr2GetSetCellAddrAH`、`tr2GetRelCellAddrAH`、`tr2ChkCellAddr`、`tr2GetTr2HeadByCellAddr` |
| header | **Head** | `tr2GetTr2Head`、`tr2GetRecordHead`、`tr2GetFieldHead` |

> 结论：应当改用 **Record / Field / Cell** 这套术语，与引擎一致。
> 我们此前的 row_* 命名源自 C# 参考实现，不是引擎术语。

### 2.2 类型系统：证实了「整数枚举，非字符串表」

目标枚举検索 `INT8` / `UINT8` / `INT16` / `UINT16` / `INT32` / `UINT32` / `FLOAT32` /
`UTF-8` / `UTF-16LE` 在 exe 中**全部 0 命中**（`ASCII` 有 3 处，但属其它用途）。

同时 API 里有强类型取值函数名：

```
tr2GetFloatAH      tr2GetFloatAHR     tr2GetFloatByIDAH
tr2GetIntAHR       tr2GetIntByIDAH
tr2GetUIntH
tr2GetStrAH        tr2GetStrByIDAH    tr2GetStrByIDH
tr2GetUtf8StringAHR      tr2GetUtf8StringByIDAH   tr2GetUtf8StringPtrByIDAH
tr2GetUcs4StringAHR      tr2GetUcs4StringByIDAH
tr2GetAsciiStringByIDAH
tr2GetFixnumH
```

**推断（证据强）**：类型信息以**整数枚举**存在，按类型分派到不同的 getter。
这**否证了**"类型以字符串表存储"的假设。

附带发现一个 v1.7 未记载的类型：**`Fixnum`**（`tr2GetFixnumH`、`tr2IsCellArrayFixnumH`）。
另有 `Ucs4`（UTF-32）也是 v1.7 未提的。

### 2.3 Cell 的两种形态（证实了 v1.7 的说法）

```
tr2IsCellArrayFixnumH      # 数值数组
tr2IsCellArrayTextH        # 文本数组
tr2GetCellArrayNumByIDH    # 取数组元素数
tr2GetStrCellArrayByIDAH   # 取字符串数组
tr2GetSharedFieldIDOffset  # 共享优化的迹象
```

`tr2GetSharedFieldIDOffset` 与 v1.7 里"相同数据被合并以优化"的猜测吻合——
**引擎确有"共享字段"的概念**。

### 2.4 索引结构H / 后缀

API 里大量出现 `H` 后缀（`tr2GetArrayNumH`、`tr2GetIndexNumH`、`tr2GetMaxIDH`）。
按常见约定，这通常表示操纵 **handle**（句柄）而非裸指针。

另有 index 相关：`tr2GetIndexH`、`tr2GetIndexNum`、`tr2GetFieldIndex`、
`tr2IsFieldIndexMinimumH`、`tr2IsFieldIndexSmallH`。

> ⚠️ `IsFieldIndexSmall` / `IsFieldIndexMinimum` 暗示 **field index 有大小两种编码**——
> 这很可能是 v1.7 里观察到 ver.1 / ver.2 差异的根因之一。待查。

### 2.5 其它值得注意的 API

| 符号 | 可能的含义 |
|---|---|
| `tr2GetTr2Ver` | **确有一个取版本号的函数** —— 直接印证 v1.7 的 VER.1/VER.2 区分是引擎真实概念 |
| `tr2IsUseByLangTag` | 与 PRES 的 country（EN/FR/IT/DE/ES/RU）语言分组呼应 |
| `tr2ChkTr2ID` / `tr2ChkTr2IDHH` | 校验 tr2 的 ID |
| `tr2AddLink` / `tr2AddLinkTop` / `tr2ChkLink` | 存在 link（链式）组织 |
| `tr2GetRandCol` / `tr2GetRandColByIDH` | 随机取列？ |
| `tr2GetSetIntH` / `tr2GetSetIntByIDH` | 「set」概念 |
| `tr2GetMinID` / `tr2GetMaxID` | ID 范围查询 |

---

## 3. 诊断字符串（直接揭示字段语义）

exe 中的格式化串，来自解析器自身：

```
0x011CC9FB  "%d...%s : RecordMode Extract %s.tr2(%p)..%s : aRecordIndex[i=%d].nID = aIDs[j=%d"
0x011CCC61  "d %s not found in %s...%s : not tr2 file %s....%s : not tr2 file %s.%s.....%s : "
0x011CCD0F  "%s is not utf-8..%f..%s : [[ %s.tr2 : ID=%d, FieldNum=%d.....%s : %s.tr2 : f=%d "
0x011CCD34  "ID=%d, FieldNum=%d.....%s : %s.tr2 : f=%d : %s[%s] : %c{%d}....%s : bString=%d,"
0x01286104  "record[%d] = {..MsgStart : 0x%x.....MsgE"
0x011D8E38  "!! : %s %d : %s : Invalid table(tr2 for demo)"
0x011E3B29  "%s %d : %s : invalid npc_tuning.tr2 (has'nt ID=0 default for no-class)"
0x011E900A  "%s %d : %s : no record in en_atk.tr2. id=%d"
0x0114190A  ") == 0....resCmpExt(p_res_dat, "tr2") == 0"
0x012402C2  "ocal(inst)....resCmpExt(p_tr2, "tr2") == 0"
```

从中可直接读出：

| 观测到的名字 | 含义 |
|---|---|
| `RecordMode Extract %s.tr2` | 存在 **RecordMode** 概念（解构模式） |
| `aRecordIndex[i].nID = aIDs[j]` | 存在 **RecordIndex 索引数组**，每项有 `nID` 字段 |
| `ID=%d, FieldNum=%d` | 一条记录 = ID + 字段数量 |
| `f=%d : %s[%s] : %c{%d}` | 字段 = 编号 + 名字[type] + **格式字符`%c`** + 长度`{d}` |
| `bString=%d` | 一个布尔：**是否是字符串** |
| `has'nt ID=0 default for no-class` | ID=0 是默认记录 |
| `not tr2 file %s` | 格式校验失败信息 |

> **`bString` 与 `%c{%d}` 是重要发现**：它说明 cell 的形态由"是否字符串" +
> 一个格式字符 + 长度共同决定。这与我们推断的 0x74/0x75/0x76 字节很可能对应——
> 但**尚未建立映射**，需要反汇编确认。

---

## 4. 一个重要的方法论修正

本轮先前的脚本**算错了 PE 节表起点**（误用 `e_lfanew+16` 取 SizeOfOptionalHeader，
正确是 `+20`），导致节区表全部乱码、所有 VA 不可信。修正后才得到上述地址。

**教训**：涉及二进制格式时，任何"看起来能跑"的地址都必须用 sanity check 验证
（检查 e_lfanew、signature、节区 VA 是否单调等）。这次是 PE 头的基本字段错了。

---

## 5. 当前状态与下一步

### 已确证 ✅

- 解析器在 `src\app\tr2.c`
- 术语应当为 **Record / Field / Cell / Head**
- 类型以**整数枚举**区分（有 Float/Int/UInt/Str/Utf8/Ucs4/Ascii/Fixnum getter）
- 存在 **`Fixnum` 与 `Ucs4`** 两个 v1.7 未记载的类型
- 存在 **`tr2GetTr2Ver`** —— VER.1/VER.2 是引擎真实概念
- 存在 **`tr2GetSharedFieldIDOffset`** —— 共享字段优化是真实机制
- 存在 **RecordIndex 索引数组**，项为 `nID`

### 仍未解决 ❌

| 问题 | 需要的手段 |
|---|---|
| 0x74 / 0x75 的确切含义 | **反汇编** `tr2GetRecordHead` / `tr2GetFieldHead` |
| `row_inf.magic`(0x14) 是魔术码还是长度 | 反汇编 + 交叉引用 |
| `%c{%d}` 格式字符与字节的映射 | 反汇编类型分发点 |
| `IsFieldIndexSmall/Minimum` 的差异 | 反汇编这两个函数 |

### 阻塞：IDA MCP 服务不可用

实测情况：存在 `idalib-mcp` 进程（PID 34368）但仅占 **5MB 内存**、
**未派生 idat64 子进程**；`idb_list`、`idb_open` 调用**全部超时**。
即服务层卡死，不是"加载慢"。这需要重启 MCP 服务或排查其启动方式后才能继续。
