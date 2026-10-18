# 资源之间的引用关系（核心）

> **本文目的**：把 `qpck / PRES / tr2 / kst1 / rtbl / tbl` 这几个格式之间的
> **引用关系**讲清楚，让"这些资源是怎么互相找到对方的"从一个难以理解的问题
> 变成一条可执行的三层寻址链。
>
> **证据等级**：核心机制全部来自 `GER.exe` 反汇编（`src\fw\res.c`），
> 规模性结论来自两作全量数据普查。

---

## 1. 一句话总结

> **引擎用一个 32 位整数（URID）定位"哪个包的哪个 dataset 的第几条条目"，
> 而"哪个包"是通过该包 PRES 头里的 `packageId` 匹配出来的。**

```
URID (32 bit)
┌──────────────┬──────┬─────────────┐
│ label / 16b  │ sect │  index /12b │
│   包的标识    │ 4b   │  条目序号    │
└──────────────┴──────┴─────────────┘
      │            │         │
      │            │         └─> 该 dataset 内的第 index 条 entry（0..4095）
      │            └───────────> dataset 号 0..7（= res/prx/asset/unk/conf/tbl/text/rtbl）
      └────────────────────────> 目标包的 packageId（PRES 头 +0x0A）
```

---

## 2. 三层寻址（反汇编确证）

### 第 1 层：全局实例表 —— "哪个包已经加载了"

**数据结构**：`dword_171E33C[0..7]`（`GER.exe` 地址 `0x171E33C`）
—— 最多 **8 个**已导出（exported）的 res 实例槽。

**注册**（`resRegisterExported` @ `0x1DAE29B`）：

```c
if ( instance->PackageID != 0 )          // 实例结构 +0x0A 处是 PackageID (u16)
{
    for ( slot = 0; slot < 8; slot++ )
        if ( !dword_171E33C[slot] ) break;
    if ( slot >= 8 ) __debugbreak();      // 8 个槽满了就崩
    dword_171E33C[slot] = instance;
    log("resRegisterExported: Register:pInst=%p:PackageID=0x%04x");
}
```

**查找**（`resGetInstUrid` @ `0x1DAC299`）：

```c
label = HIWORD(urid);                     // URID 高 16 位
for ( i = 0; i < 8; i++ )
    if ( dword_171E33C[i] && *(u16*)(*dword_171E33C[i] + 10) == label )
        return dword_171E33C[i];          // 命中：拿到实例
return 0;                                  // 未找到
```

> **`instance + 0x0A` 就是 PRES 文件头 `+0x0A` 的 `packageId`** ——
> 同一个字段，两处语义在这里闭合。

### 第 2 层：URID 拆包 —— "包的哪里"

**`resGetInstUrid`（`0x1DAC299`）**：

```c
if ( !HIWORD(urid) ) return 0;                    // label=0 => 本地寻址，不走全局表
label = HIWORD(urid);                             // 高 16 位
sect  = ((urid >> 12) & 0xF) - 1;                 // bit12..15 减 1 = 0..7
if ( sect >= 8 ) { warn("URID(Label)=0x%08x"); __debugbreak(); }
index = urid & 0xFFF;                             // 低 12 位 = 0..4095
log("URID=0x%08x:pInst=%p:sect=%d:label=%d");
```

**位域布局**：

| 位段 | 宽度 | 含义 |
|---|---|---|
| `31..16` | 16 | `label` = 目标包的 `packageId`；**0 表示本地** |
| `15..12` | 4 | `sect + 1` = dataset 号（1..8 ⇒ 0..7） |
| `11..0` | 12 | `index` = 该 dataset 内的条目序号 |

### 第 3 层：条目定位 —— "拿到 entry 头"

**`resGetDatSect`（`0x1DABD69`）**：

```c
if ( !dword_171D330[urid] ) __debugbreak();       // urid 句柄必须已加载（上限 1024）
entries = *(_DWORD*)(*(_DWORD*)dword_171D330[urid] + 4);   // section 数组基址
count   = *(_DWORD*)(entries + 8*sect + 4);                 // 该 dataset 条目数
if ( count <= 0 ) return 0;
return  *(u32*)(entries + 8*sect) + 32*index;              // entry 头 = 起点 + 32*index
```

即：**entry 头数组的起点 + `32 × index`**，与 `pres.md` §5.1 的目录槽定义完全一致。

---

## 3. 实测：只有 10 个包能被跨文件引用

这是理解引用关系最关键的一条事实。

### 3.1 PackageID 分布（两作全量）

| 游戏 | 可达 PRES 总数 | `packageId = 0` | `packageId ≠ 0` |
|---|---|---|---|
| GER | 2,952 | **2,942** | **10** |
| GE2RB | 5,634 | 5,624 | **10** |

### 3.2 那 10 个顶层包（两作**完全相同**）

| PackageID | 深度 | GER 大小 | 路径 |
|---|---|---|---|
| `0x7C6E` | 0 | 908,640 | `bin/resconv_pc/src/system/system.res` ← **入口** |
| `0x4356` | 2 | 19,744,752 | `bin/resconv_pc/src/god_game/god_game.res` |
| `0x23E2` | 1 | 6,033,088 | `bin/resconv_pc/src/god_menu/god_menu.res` |
| `0x728F` | 3 | 1,186,272 | `data/GameData/game/sound/se/se_game.res` |
| `0x1DA3` | 3 | 905,856 | `bin/resconv_pc/src/x005_at3/x005_at3.res` |
| `0x73DD` | 5 | 826,608 | `data/GameData/effect/Player/player_effect_scy.res` |
| `0x3426` | 5 | 407,568 | `data/GameData/effect/Player/player_effect_ham.res` |
| `0x04A3` | 5 | 401,008 | `data/GameData/effect/Player/player_effect_bus.res` |
| `0x0663` | 5 | 349,024 | `data/GameData/effect/Player/player_effect_spe.res` |
| `0x28C0` | 5 | 99,200 | `data/GameData/effect/Player/player_effect_lon.res` |

**含义**：

- 只有这 10 个包有非零 `packageId`，因此**只有它们能被 URID 跨文件引用**。
- 其余 2,942 / 5,624 个 PRES 的 `packageId = 0`，它们是内部节点，
  通过父节点的路径字符串（B 类型条目）直接定位，不走全局表。
- **两作的 10 个 packageId 完全一致** —— 说明这是引擎设计的固定模块划分，
  不随游戏内容变化。

> ⚠️ **一个矛盾点**：全局表只有 8 个槽，但有 10 个包带 packageId。
> 说明**不是所有包同时注册**——引擎按需注册当前活跃的包（例如正在玩某个武器
> 时只注册对应的 effect 包）。这条尚待运行时验证，标为【推测】。

---

## 4. 各格式在引用链中的位置

```
qpck 归档
 │  平铺表：CRC64(路径) -> 字节块。 不含任何引用关系。
 │
 └─ PRES（语义层）
     │  头 +0x0A = packageId        <- 第 1 层寻址的 key
     │  头 +0x1C = countryCount     <- 语言分组 1 或 6
     │
     ├─ country（语言）
     │   └─ dataset ×8（res/prx/asset/unk/conf/tbl/text/rtbl）
     │       └─ entry（32 字节）
     │           ├─ 类型 B：dataAt -> 路径字符串 -> CRC64 -> qpck 查表   【跨文件引用】
     │           ├─ 类型 F：dataAt -> 内嵌数据 / 尾部共享池              【本文件内数据】
     │           └─ 类型 0：占位，无数据
     │
     ├─ tr2（表数据库）
     │   自身的 Record/Field/Cell 结构。PRES 只把它当作一个"文件"引用，
     │   不懂它的内部结构。tr2 内部的引用靠 RecordIndex（nID）。
     │
     ├─ kst1（键值数据库）
     │   自身的 header/索引/记录结构。PRES 只当作文件引用。
     │   kst1 内部的引用靠它自己的 key 索引（numBlocks + 位图）。
     │
     ├─ tbl（散表）
     │   纯 u32 数组，无内部结构。靠 dataset 内的 entry index 定位。
     │
     └─ rtbl（引用表）
         指向一个 *.rtbl 文件，该文件按 0x200 字节一槽记录间接资源。
         PRES 侧的 _EXISTS= 位图标记哪些槽被占用。
```

### 4.1 关键区分：三种"引用"是不同的东西

这是最容易混淆的地方，必须分开理解：

| 引用类型 | 载体 | 解析方式 | 跨文件？ |
|---|---|---|---|
| **路径引用** | PRES 类型 B 条目的 `dataAt` 处字符串 | CRC64(路径) → qpck TOC | **是** |
| **URID 引用** | 32 位整数（代码里） | label → PackageID → 全局表 → sect/index | 是（限 10 个包） |
| **内部索引** | tr2 的 RecordIndex、kst1 的 key | 各格式自己的算法 | 否（格式内） |
| **槽位表** | rtbl 的 0x200 字节槽 | 槽内 `+0x20` 处路径 | 是 |

> **理解要点**：tr2 和 kst1 **不参与** PRES 的引用体系。
> 它们对 PRES 而言只是"一个文件"。它们的内部引用是**各自格式私有的**。
> 所以"tr2/kst1 怎么引用"和"PRES 怎么引用"是两个不同层次的问题。

---

## 5. 数据侧交叉验证

### 5.1 URID 的 12 位 index 够不够用

对两作全部 PRES 统计每个 dataset 的最大条目数：

| dataset | GER max | GE2RB max | 是否 ≤ 4095 |
|---|---|---|---|
| `res` | 551 | 1,376 | ✅ |
| `prx` | 1 | 1 | ✅ |
| `asset` | 1,568 | 1,553 | ✅ |
| `unk` | 0 | 0 | ✅ |
| `conf` | 1,145 | 1,541 | ✅ |
| `tbl` | 1,313 | 1,292 | ✅ |
| `text` | 46 | — | ✅ |
| `rtbl` | 422 | 347 | ✅ |
| **超过 4095 的 dataset 数** | **0** | **0** | — |

**结论**：12 位 index 完全够用，`0x1000` 是设计约束而非巧合。
（合计 3,403,114 条 entry 分布在 105,688 个 (country, dataset) 组合里，
平均每组仅约 32 条，最大的组也才 1,568 条。）

### 5.2 packageId 与 country 的关系

两者的取值**一一对应**：同一个包在不同语言版本里是**同一个 PRES 文件**，
country 层是文件内部分组，**不**产生新的 packageId。

---

## 6. 尚未解决

| 问题 | 现状 | 需要的证据 |
|---|---|---|
| 10 个包 vs 8 个槽的矛盾 | 推测按需注册 | 运行时断点观察 `resRegisterExported` 调用次数 |
| `label = 0` 时的本地寻址规则 | 只知道不走全局表 | 反汇编 `resGetInstUrid` 返回 0 后调用方的分支 |
| `rtbl` 槽内是否存 URID | **已证否**（见 §6.1） | — |
| `dword_171D330`（1024 槽句柄表）的填充时机 | 知道是 urid->实例映射 | 追踪写入点 |

### 6.1 【已证否】数据文件里不存 URID

这是一个**重要的负结果**，推翻了我们最初的猜测，必须记录。

**最初的猜测**：URID 可能被序列化进 tr2 / rtbl 载荷，若能证实就能从数据侧重建完整引用图。

**实测方法与结果**：

用两套判据扫描真实 tr2 数据（30 个文件，累计 92,228 个 dword），
并与 200,000 个随机 dword 的基线对照：

| 判据 | 定义 | 真实数据命中率 | 随机基线 | 判定 |
|---|---|---|---|---|
| 宽松 | `sect ∈ 0..7` 且 (`label == 0` 或 label 属 10 个已知 packageId) | **26.39%** | 0.0095% | ❌ 误报 |
| **严格** | `sect ∈ 0..7` 且 `label` **必须属于**那 10 个 packageId | **0.0087%** | **0.0080%** | ✅ **与随机不可区分** |

**结论**：**tr2 载荷中不存在 URID。**

宽松判据的 26.39% 全部是误报。原因是：
- `(v >> 12) & 0xF` 落在 1..8 的概率是 **50%**（16 种取值里 8 种合法）
- `label == 0` 的概率是 `1/65536`
- 两者相乘仍会给出可观的假阳性率，而真实数据里 `label == 0` 的情况
  被大量小整数值（索引、ID、标志位）意外满足

**只有严格判据（label 必须精确等于 10 个已知 packageId 之一）才可信**，
它给出的结果是"与随机无异"。

**对建模的影响**：

- URID 是**纯运行时**的寻址优化，**不落盘**。
- 因此**无法从数据侧直接重建引用图**；引用图只能通过
  「PRES 类型 B 的路径字符串 + CRC64 → qpck TOC」重建。
- 这也说明：**数据文件之间的耦合比想象中更松**——
  tr2 / kst1 确实是自包含的，它们与 PRES 只有"被当作一个文件引用"这一层关系。

> 教训：设计二进制模式扫描时，**必须用随机基线对照**，并检查每个约束的实际通过率。
> 单看"命中率 26%"会得出完全错误的结论。这个错误我犯了，靠严格判据 + 基线对照才发现。

### 6.2 rtbl 的 URID 扫描：同样为负

用同一套严格判据重验 rtbl（40 个文件、5,735,680 个 dword）：

| 判据 | 命中率 | 随机基线 | 判定 |
|---|---|---|---|
| 宽松 | 0.4791% | 0.0095% | ❌ 误报（看着像 ×50 信号） |
| **严格** | **0.0000%** | 0.0080% | ✅ **完全不存在** |

**结论：rtbl 载荷里也没有 URID。**

两处独立验证（tr2 的 0.0087% ≈ 基线、rtbl 的 0.0000% < 基线）共同支持同一条结论：

> **URID 是纯运行时概念，任何数据文件都不存它。**

这也把引用关系的模型简化了很多：

- 数据层（qpck / PRES / tr2 / kst1 / rtbl / tbl）之间**唯一的持久化引用是路径字符串**。
- URID 只在内存里由引擎动态构造，用于加速已加载资源之间的访问。
- 因此 **mod 作者只需要关心路径 + CRC64**，不需要重建 URID。

---

## 7. 复现方法

```python
# 1) 找出带 packageId 的顶层包
from gecv.pres import parse
pres = parse(blob)
if pres.package_id:
    print(f"top-level package: 0x{pres.package_id:04X}")

# 2) 拆解 URID（代码侧语义）
def decode_urid(urid):
    label = (urid >> 16) & 0xFFFF
    sect  = ((urid >> 12) & 0xF) - 1
    index = urid & 0xFFF
    return label, sect, index

# 3) 用 (label, sect, index) 定位 entry
#    entry_at = section_offsets[sect] + 32 * index
```

IDA 定位线索：

| 项 | 地址（GER） |
|---|---|
| 全局实例表 | `dword_171E33C` |
| 全局句柄表（1024 槽） | `dword_171D330` |
| `resGetInstUrid` | `0x1DAC299` |
| `resGetDatSect` | `0x1DABD69` |
| `resRegisterExported` | `0x1DAE29B` |
| `resUnregisterExported` | `0x1DAEE41` |
| 子 res 判定（`names[1]=="res"`） | `0x1DABC5D` |
| 常量 `"res"` | `0x118B3D8` |
