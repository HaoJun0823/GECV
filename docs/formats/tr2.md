# tr2 格式 —— 静态逆向证据汇总

> **证据等级说明 / Evidence classes**
>
> - **A 级（强）**：来自 exe 内部符号串或格式化诊断串 —— 引擎自己留下的痕迹
> - **B 级（中）**：对大量真实样本统计得出的相关性
> - **C 级（弱）**：合理推测，尚未交叉验证
>
> 目标文件：`GER.exe`（machine `0x014C` x86-32、optional_magic `0x010B` PE32、
> ImageBase `0x00400000`、11 个节区）

---

## 0. 术语更正：应当使用引擎自己的说法

⚠️ **我们此前一直在用 C# 参考实现的命名，那不是引擎的概念。**
Warning: we had been using the C# reference's naming, which is not the engine's own vocabulary.

| 我们曾用的 | **引擎的术语** | 依据符号（A 级） |
|---|---|---|
| `row_inf` | **Record** | `tr2GetRecord`、`tr2GetRecordHead`、`tr2GetRecordCore`、`tr2MakeRecord` |
| `row_data` 中的项 | **Field** | `tr2GetFieldHead`、`tr2GetFieldIndex`、`tr2GetFieldNum` |
| 数据单元 | **Cell** | `tr2ChkCellAddr`、`tr2GetSetCellAddrAH`、`tr2GetTr2HeadByCellAddr` |
| header | **Head** | `tr2GetTr2Head`、`tr2GetRecordHead`、`tr2GetFieldHead` |
| index / id 列表 | **RecordIndex** | 诊断串 `"aRecordIndex[i=%d].nID = aIDs[j=%d]"` |

**结论：今后一律使用 Record / Field / Cell / Head。**
From now on always use Record / Field / Cell / Head.

---

## 1. 解析器位置（A 级）

exe 中的断言串直接给出了源文件路径：

```
VA 0x011CC64C (file 0xDCBA4C)
pBin....tr2GetArrayNumH.src\app\tr2.c...tr2GetRecordHead....tr2GetFieldIndex....
```

**源文件：`src\app\tr2.c`**

全 exe 共发现 **107 个 `tr2*` 标识符**（可能是函数名/符号）。

---

## 2. 类型名：它们是字符串，但只出现在诊断信息里（已两度修正）

⚠️ **本节我先后给过两个错误结论，这里给出精确版本。**

| 版本 | 说法 | 错在哪 |
|---|---|---|
| 初版 | 类型串全 0 命中 ⇒ 必然是整数枚举 | 搜索时误加了 `\x00` 终止符 |
| 二版 | 类型串确实存在 ⇒ 存在运行时字符串类型表 | 未检查上下文，把无关命中算了进去 |
| **当前（精确）** | 类型名**确实以字符串存在**，但**目前只见于诊断/报错串** | — |

### 2.1 无关命中（不是 tr2 的）

`INT8` / `INT16` / `UINT16` / `INT32` / `UINT32` 各出现 1 次，但上下文是**断言宏里的
最大值常量**，与 tr2 无关：

```
INT8     @0xE11E6C  ...inhibit_remove_count <= INT8_MAX....
INT16    @0xE402CE  ...Get_AssaultStaggerMaxHp() <= UINT16_MAX._metamotion_interface_p...
UINT32   @0xDF2CF6  ...m_blocker_count < UINT32_MAX....
```

### 2.2 真正的 tr2 命中

`UTF-16LE` 出现在 tr2 诊断串群里（`0xDCBF59`，紧邻 `src\app\tr2.c` 区域）：

```
!!! Error !!! : %s %d : %s : %s*%d [UTF-16LE]:pBin=%p
!!! Error !!! : %s %d : %s : %s*%d [UTF-8]:pBin={{.%s.}}
%s*%d NOT F...
```

注意其中的 `%s*%d` —— **名字 × 数量** 的形式，与你 tr2 spec 里
「根据 0x76 决定读取数量」的描述吻合。

### 2.2.1 该区域完整上下文（实测）

```
...%s : `%s' not found in `%s'`%s'....._tr2GetFixnumH..%s : error : %s not found
...%s : Rel ... %s.....%s : Set ... %s:%d
...!!! Error !!! : %s %d : %s : %s*%d [UTF-16LE]:pBin=%p
...!!! Error !!! : %s %d : %s : %s*%d [UTF-8]:pBin={{.%s.}}
...%s*%d NOT FOUND
...%s : Warning!! : Please do not use UTF in %s
...total = %d..rand = %f...%d : %f.....result = %d(%f).....%s : {..ret=%s:%d.}
```

新观察到的三点（**B 级**）：

| 观测 | 含义 |
|---|---|
| `_tr2GetFixnumH..%s : error : %s not found` | `tr2GetFixnumH` 有专门的失败路径，且带下划线前缀变体 |
| `%s : Rel ... %s` / `%s : Set ... %s:%d` | 存在 **Rel**（相对地址）与 **Set**（设置）两类操作，对应 `tr2GetRelCellAddrAH` / `tr2GetSetCellAddrAH` |
| `Warning!! : Please do not use UTF in %s` | **引擎明确限制某些字段不得使用 UTF 编码**。这条对打包很重要：改文本时不能随意切编码 |

### 2.3 结论

- 类型**名字**确实作为字符串存在于 exe，但**证据只支持"用于报错信息的格式化"**。
- **不能据此断定**运行时有一张字符串查找表（那需要反汇编类型分发点才能确认）。
- **级别：B（中）** —— 比初版强，但不足以定论。

> 教训：二进制串搜索**必须看上下文**，否则会把同名垃圾当成证据，或反之漏掉真信号。

```
tr2GetFloatAH  tr2GetFloatAHR  tr2GetFloatByIDAH
tr2GetIntAHR   tr2GetIntByIDAH
tr2GetUIntH
tr2GetStrAH    tr2GetStrByIDAH   tr2GetStrByIDH
tr2GetUtf8StringAHR  tr2GetUtf8StringByIDAH  tr2GetUtf8StringPtrByIDAH
tr2GetUcs4StringAHR  tr2GetUcs4StringByIDAH
tr2GetAsciiStringByIDAH
tr2GetFixnumH
```

**结论：类型以整数枚举存在，代码按类型分派到不同 getter。**
Type info is an integer enum; code dispatches to per-type getters.

### 2.1 两个 spec v1.7 未记载的类型

| 类型 | 依据 | 级别 |
|---|---|---|
| **Fixnum** | `tr2GetFixnumH`、`tr2IsCellArrayFixnumH` | A |
| **Ucs4**（UTF-32） | `tr2GetUcs4StringAHR`、`tr2GetUcs4StringByIDAH` | A |

---

## 3. Cell 的两种形态 —— 证实了 v1.7（A 级）

```
tr2IsCellArrayFixnumH     # 数值数组
tr2IsCellArrayTextH       # 文本数组
tr2GetCellArrayNumByIDH   # 取数组元素数
tr2GetStrCellArrayByIDAH  # 取字符串数组
tr2GetSharedFieldIDOffset # 共享优化
```

**`tr2GetSharedFieldIDOffset` 证实"相同数据合并优化"是引擎的正式机制**，
印证了 v1.7 里的猜测。

---

## 4. 版本的概念确实存在（A 级）

`tr2GetTr2Ver` —— 引擎有专门的取版本函数。
⇒ **VER.1 / VER.2 是引擎真实概念，不是后人总结的经验规则。**

另有 `tr2IsFieldIndexSmallH` / `tr2IsFieldIndexMinimumH`，暗示
**field index 有"小编码/最小编码"两种形式** —— 这很可能是 v1.7 里
ver.1 / ver.2 行为差异的根因。级别 C（尚未反汇编确认）。

---

## 5. 诊断串揭示的结构（A 级）

exe 中的格式化字符串，来自解析器自身：

| VA | 字符串 | 可读出的信息 |
|---|---|---|
| `0x011CC9FB` | `"RecordMode Extract %s.tr2(%p)"` | 存在 **RecordMode** 概念 |
| `0x011CC9FB` | `"aRecordIndex[i=%d].nID = aIDs[j=%d]"` | RecordIndex 是索引数组，项有 `nID` |
| `0x011CCD0F` | `"%s.tr2 : ID=%d, FieldNum=%d"` | 一条 Record = ID + **FieldNum** |
| `0x011CCD34` | `"f=%d : %s[%s] : %c{%d}"` | Field = 编号 + 名字[类型] + **格式字符** + 长度 |
| `0x011CCD34` | `"bString=%d"` | 布尔：**是否字符串** |
| `0x011CCC61` | `"not tr2 file %s"` | 格式校验失败信息 |
| `0x011E3B29` | `"invalid npc_tuning.tr2 (has'nt ID=0 default for no-class)"` | ID=0 是默认记录 |

> **`bString` + `%c{%d}` 是重要线索**（级别 C）：cell 形态很可能由
> 「是否字符串」+ 一个格式字符 + 长度共同决定。这与我们观察到但未能解释的
> 0x74 / 0x75 / 0x76 字节**可能对应**，映射尚未建立。

---

## 6. 已知字段与其来源对照

| 字段 | v1.7 的说法 | 静态证据支持 | 级别 |
|---|---|---|---|
| `magic` = `.tr2` | 固定 | 19,473/19,473 真实文件全部匹配 | **A** |
| `header_magic` 高位 = 年份 | 是 | 实例 `0x07DF`=2015 | **A** |
| `column_inf_offset` | 通常 0x40 | 实例一致 | **A** |
| `offset` 存 (类型4bit + 地址28bit) | 是 | 解析全部 PRES 无失败 | **A** |
| Record = ID + FieldNum | — | 诊断串 `"ID=%d, FieldNum=%d"` | **A** |
| FieldIndex 有大小两编码 | 未提 | `tr2IsFieldIndexSmall/MinimumH` | C |
| 0x74 / 0x75 含义 | 标"未知" | 疑似对应 `bString`/格式字符 | **C（未解决）** |
| 0x76+0x77 = INT16 | 2024-11-23 改判 | 325 样本中 0x77 恒 0、0x76 恒非 0 | **B** |
| `row_inf.magic`(0x14) 是魔术码 | 是 | 我存疑，可能是长度/数量 | **C（存疑）** |

---

## 7. 交叉引用：指向函数体的地址

多 个 tr2 符号名字符串被引用于 `0x015ED060–0x015ED908` 一带：

| 符号名 | 字符串 VA | 引用点（代码位置） |
|---|---|---|
| `tr2GetRecordHead` | `0x011CC654` | `0x015ED8E8` |
| `tr2GetFieldHead` | `0x011CC2F0` | `0x015ED518 / 0x015ED558 / 0x015ED568 / 0x015ED5A8` |
| `tr2GetRecordCore` | `0x011CC11C` | `0x015ED360 / 0x015ED3E8 / 0x015ED438 / 0x015ED4A8` |
| `tr2GetTr2Head` | `0x011CC3AC` | `0x015ED608 / 0x015ED618 / 0x015ED628` |
| `tr2GetTr2Ver` | `0x011CC468` | `0x015ED6B8 / 0x015ED6D8` |
| `tr2ChkTr2ID` | `0x011CC32C` | `0x015ED56C / 0x015ED62C / 0x015ED7BC / 0x015ED7FC` |
| `tr2GetFloatAH` | `0x011CBFE4` | `0x015ED190 / 0x015ED1B0` |
| `tr2GetUtf8StringByIDAH` | `0x011CBE8C` | `0x015ED0A0 / 0x015ED0C0 / 0x015ED0E0` |
| `tr2MakeRecord` | `0x011CC39C` | `0x015ED5F8 / 0x015ED638` |

> **`0x015EDxxx` 不是指针表**（已否证）：对该区域的 dump 显示它是**机器码**
> （大量 `0F` 前缀、`C7/85/89` mov 操作码）。因此这些"引用点"是**代码内的立即数操作数**，
> 即它们位于**真正引用 tr2 符号名的函数内部**。这比指针表更有用。

---

## 8. 尚未解决（需要反汇编）

| 问题 | 需要的手段 |
|---|---|
| 0x74 / 0x75 的确切语义 | 反汇编 `tr2GetRecordHead` / `tr2GetFieldHead`，读 %c{%d} 的处理 |
| `row_inf.magic`(0x14) 是不是魔术码 | 反汇编 + 交叉引用 |
| `IsFieldIndexSmall` vs `IsFieldIndexMinimum` | 反汇编这两个函数 |
| Field / Cell 的完整内存布局 | 反汇编 `tr2GetRecordCore` |

---

## 9. 过程中的两个方法论教训

1. **PE 节表起点算错**：第一版脚本用 `e_lfanew+16` 取 `SizeOfOptionalHeader`，
   正确应为 `+20`。导致节区全乱码、地址不可信。
   教训：二进制解析的每个中间结果都要 sanity check（如 VA 是否单调、大小是否合理）。

2. **不要用 shell 重定向改 Python 源码**：本轮多次用 `[System.IO.File]::WriteAllLines`
   修补 .py，造成 UTF-8 编码损坏 + 误删多行，前后浪费多个回合。
   教训：改代码一律整文件重写。

---

## 10. IDA 阻塞记录（供下一轮直接接续）

### 10.1 现状

| 尝试 | 结果 |
|---|---|
| MCP `idb_open` GER.exe.i64（458 MB） | 超时；**后台确实启动了 worker**（`GER.exe.id0` 写到 232 MB）后死亡 |
| MCP `idb_open` GER.exe（松散集） | 超时 |
| MCP `idb_open` GE2RB.exe.i64（456 MB） | 超时 |
| MCP `idb_open` `work/idafresh/GER_fresh.id0` | 超时 |
| MCP `idb_open` `tiny.i64`（41 KB） | **✅ 秒开，Hex-Rays 就绪** |
| 便携版 `idat.exe -A` 直开 GER.exe | 可启动（CPU 3000+ 秒仍未完成全量分析） |
| 便携版打开已建松散集并存盘 | `error code 1 / 4` |

### 10.2 结论

**MCP 链路本身是好的**（小库秒开证明）。阻塞点是
**"两个 ~458 MB 库的加载耗时超过 MCP 调用超时窗口"**：
worker 每次都被启动、工作一段时间、然后被截断。
每次重试都会再次拖垮 supervisor —— 上一轮甚至导致已打开的 `probe_tiny` 会话也超时。

### 10.3 下一轮可行的三条路（按性价比）

1. **提高 MCP 超时**：若 DSH 侧可配置 `idb_open` 超时，放宽到 15–20 分钟即可。
2. **用小库替代**：只分析 tr2 相关函数附近的一小段。
3. **绕开 MCP**：便携版 IDA + IDAPython（`-S`）直跑；
   关键是脚本要**写文件而非 print**（实测 `-S` 的 stdout 不回传），
   且需让分析跑完（约 30–50 分钟 CPU）。

### 10.4 可直接复用

`work/ida_query2.py` —— 已写好的 IDAPython 查询脚本（结果写 `RESULT.txt`），
已修正 import 与输出通道问题。

---

## 11. 附：IDA 环境事实（本机）

| 项 | 值 |
|---|---|
| IDA 安装位置 | `G:\Downloads\ida93sp2\portable_win\`（**便携版，不在 PATH**） |
| 版本 | 9.3.26.0421 |
| Hex-Rays | 9.3.0.260421（**decompiler 可用**） |
| license | `idapro.hexlic` 存在且有效 |
| MCP 插件 | idalib 模式下可加载 |

> **关键操作常识**：本机 IDA 是便携版，DSH 的 `idalib-mcp` worker 无法自行找到它，
> 直接用 `-A` 正常。
> Key operational fact: IDA here is portable and not on PATH, so DSH's idalib-mcp worker
> cannot launch it by itself; invoke it directly.
