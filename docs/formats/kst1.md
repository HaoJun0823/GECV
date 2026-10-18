# kst1 格式规范

> **证据等级：A（最高）** —— 头部字段与索引算法全部来自 `GER.exe_full.i64` 的
> Hex-Rays 伪代码，并用 18 个真实文件完成了数据级验证（`total set bits == numrecord` 精确成立）。
> Evidence class A: header fields and the index algorithm come from Hex-Rays pseudocode,
> and are validated against 18 real files (set-bit total equals numrecord exactly).

**状态**：读路径完全确证　**样本**：GER 全部 18 个 `kst1` 文件

---

## 1. 这是什么

`kst1` 是引擎的**键值数据库**（key-value store），由 `src\lib\kst.c` 实现。

从 exe 里恢复出的完整 API：

| 函数 | 作用 | 源文件行号 |
|---|---|---|
| `kstOpenDatabase` | 打开并校验 magic | 192 |
| `kstFetchRecordByKey` | **按 key 取记录** | 93 |
| `kstFetchRecordByIndex` | 按索引取记录 | 158 |
| `kstGetString` | 取字符串 | 181 / 184 |

引擎里用它的地方包括：`OracleCellKst`、任务表（`mission.kst`）、文本（`article.kst`）、
角色扮演数据（`avatar_translate.kst`）。

### 1.1 实际样本分布

GER 里共 **18 个** `kst1` 文件，全部包在 BLZ4 里（后缀 `.kst.blz`），分三组：

| 组 | 记录数 | stride | 文件数 | 说明 |
|---|---|---|---|---|
| `Locale/exported/*/mission.kst` | 515 | 312 | 6（6 语言） | 任务表 |
| `Locale/exported/*/article.kst` | 13,162 | 24 | 6 | 文章/百科文本 |
| `GameData/g999_Base/db/avatar_text/*/avatar_translate.kst` | 14,112 | 24 | 6 | 头像文本 |

> **同一文件的不同语言版本，头部字段完全相同**，只有文件大小变化。
> 说明头部描述**结构**（stride / 记录数 / 偏移），内容（字符串）才是语言相关的。

---

## 2. 文件头部

来自 `kstFetchRecordByKey`（`0x19A0A84`）与 `kstFetchRecordByIndex`（`0x19A0A44`）反编译：

```c
// kstFetchRecordByIndex
v3 = *a1;                                   // v3 = header
if ( a2 >= *(_DWORD *)(*a1 + 12) )          // +0x0C = numrecord
    __debugbreak();                         // 断言 "index < header->numrecord"
return *a1 + *(_DWORD *)(v3 + 20)           // +0x14 = 记录表偏移
           + a2 * *(_DWORD *)(v3 + 8);      // +0x08 = stride

// kstFetchRecordByKey
v2 = header;
v3 = sub_19A0CC7( header + header[4], key );   // +0x10 = 索引表偏移
if ( v3 < 0 ) return 0;                        // 未找到
if ( v3 >= v2[3] ) __debugbreak();             // +0x0C = numrecord
return header + v2[5] + v3 * v2[2];            // +0x14, +0x08
```

| 偏移 | 类型 | 字段 | 样本值（mission） | 状态 |
|---|---|---|---|---|
| 0x00 | char[4] | `magic` = `"kst1"` | `6B 73 74 31` | ✅ 断言 `memcmp(header->magicword,"kst1",4)==0` |
| 0x04 | u32 | ?（恒 0） | `0` | ⚠️ 未解读 |
| 0x08 | u32 | **stride**（记录字节数） | `312` | ✅ 确证 |
| 0x0C | u32 | **numrecord**（记录数） | `515` | ✅ 确证 |
| 0x10 | u32 | **index_off**（索引表偏移，相对文件起始） | `24` | ✅ 确证 |
| 0x14 | u32 | **record_off**（记录表偏移，相对文件起始） | `2912` | ✅ 确证 |
| 0x18 | u32 | **numBlocks**（索引块数） | `80` | ✅ 实测 |
| 0x1C | u32 | **maxKey**（最大 key） | `20444` | ✅ 实测 |
| 0x20 | u32 | ?（恒 0） | `0` | ⚠️ 未解读 |
| 0x24 | u32 | ?（`mission`=215 / `article`=0x3FFFFF） | — | ⚠️ 未解读 |

> 注意 `index_off` 在样本里恒为 **24（0x18）**，即索引表紧跟在头部之后；
> `numBlocks` / `maxKey` 恰好落在 `0x18` / `0x1C`，也就是**索引表的头两个字段**，
> 而非独立头部字段。因此头部实际只到 `0x18` 为止。

---

## 3. 索引表：两级 + 位图

这是 kst1 最精妙的部分。反编译 `sub_19A0CC7`（key → 记录序号）：

```c
int sub_19A0CC7(_DWORD *a1, int key)      // a1 = index table
{
  if ( key < 0 ) __debugbreak();
  if ( a1[1] < (unsigned)key ) return -1;         // a1[1] = maxKey
  if ( (unsigned)(key / 256) >= *a1 ) __debugbreak();  // a1[0] = numBlocks
  return sub_19A0C67( &a1[8 * (key/256) + 2 + (key/256)], key );
}
```

块内查找 `sub_19A0C67`：

```c
int sub_19A0C67(_DWORD *blk, int key)
{
  int k = key % 256;
  if ( ((0x80000000 >> (k % 32)) & blk[k/32 + 1]) != 0 )   // 位图判断存在性
      return *blk + sub_19A09C5((int)(blk + 1), k);        // base + popcount前缀和
  return -1;                                               // 不存在
}
```

### 3.1 结构

```
索引表 @ index_off:
    +0x00  u32  numBlocks      块数量
    +0x04  u32  maxKey         最大 key
    +0x08  block[0]            每块 36 字节
    +0x2C  block[1]
    ...
```

**每块 36 字节（9 个 dword）**：

| 块内偏移 | 类型 | 字段 |
|---|---|---|
| +0x00 | u32 | **base** —— 该块第一个有效 key 对应的记录序号 |
| +0x04 | u32[8] | **bitmap** —— 256 位，标记 key 在块内是否存在 |

### 3.2 块起始的字节偏移（易错点）

反编译里写的是 `&a1[8*b + 2 + b]`，`a1` 是 **dword 指针**，因此字节偏移：

```
bytes = 4 * (8*b + 2 + b) = 36*b + 8
```

即 **每块 36 字节，而非 32**。这一点如果不按 dword 指针换算就会错位，
导致把所有块读成垃圾（我第一次就踩了这个坑，读出 `base=8388591` 这种哨兵值）。

### 3.3 key → 记录序号的完整算法

```
b = key / 256                     # 块号
k = key % 256                     # 块内偏移
blk = index_table + 8 + 36*b      # 块起始
if bitmap(blk).bit[k] == 0:       # 位图检查（方向：0x80000000 >> (k%32)）
    return NOT_FOUND
idx = u32(blk) + popcount(bitmap(blk), 0..k-1)   # base + 前缀和
record = file + record_off + idx * stride
```

### 3.4 位图方向

```c
(0x80000000 >> (k % 32)) & blk[k/32 + 1]
```

**从最高位开始**（bit 31 对应 `k%32 == 0`）。这与常见的 LSB-first 位图相反，容易写错。

### 3.5 popcount 前缀和

反编译 `sub_19A09C5`：

```c
int sub_19A09C5(int a1, int a2)
{
  int v2 = 0;
  for ( i = 0; i < a2 / 32; v2 += popcount32(*(u32*)(a1 + 4*i++)) );  // 整 dword 累加
  if ( a2 % 32 )
      return v2 + popcount32( *(u32*)(a1 + 4*i) >> (32 - a2 % 32) );    // 余数部分右移后再数
  return v2;
}
```

即：统计**该 key 之前**已置位的数量。

---

## 4. 数据级验证（决定性）

对 `mission.kst` 实测：

```
header:
  +0x08 stride     = 312
  +0x0C numrecord  = 515
  +0x10 index_off  = 0x18
  +0x14 record_off = 0xB60

index @0x18:
  numBlocks = 80
  maxKey    = 20444

blocks:
  blk0: base=0    bitmap_ones=89
  blk1: base=89   bitmap_ones=43
  blk2: base=132  bitmap_ones=0     <- 空块

KEY RESOLUTION:
  key=255  -> EXISTS record[88]
  key=256  -> EXISTS record[89]

★★ total set bits across all blocks = 515
★★ numrecord                        = 515
★★ match: True
```

**所有块的置位总数精确等于 numrecord** —— 这证明：
1. 每块 36 字节的布局正确
2. 位图方向正确
3. `base` 确实是前缀和累加（blk0 结束于 89 = blk1 起点）

其余验证：

| 检查 | 结果 |
|---|---|
| `record_off + numrecord*stride <= filesize` | ✅ 163,592 ≤ 263,819 |
| `base` 跨块连续递增 | ✅ 0 → 89 → 132 |
| 块覆盖的 key 范围 | `numBlocks*256 = 20,480` ≥ `maxKey = 20,444` ✅ |

---

## 5. 记录（Record）内部结构

### 5.1 字符串取法（已确证）

来自 `kstGetString`（`0x19A0B64`）反编译：

```c
v5 = (unsigned __int16 *)(*a4 + *a1);      // 字符串位置 = 基址 + 记录内偏移
if ( *v5 > a3 )                            // 断言 p->length <= bufsize (行 181)
    __debugbreak();
memcpy(a2, v5 + 1, *v5);                   // 跳过 2 字节长度，拷贝 length 字节
if ( a2[*v5 - 1] )                         // 断言 buf[p->length-1] == '\0' (行 184)
    __debugbreak();
```

**字符串结构**：

```
[u16 length][length 字节内容，最后一个字节必须是 \0]
```

### 5.2 记录字段（实测 statistical 判定）

对 `article.kst`（stride=76，13,162 条）逐 dword 做统计，判定字段类型：

| dword | 语义 | 依据 |
|---|---|---|
| `dword[0]` | **`[top:8][type:8][line_no:16]`** | 低 16 位 = 10,11,12… 连续行号 |
| `dword[1]` | **`[category:8][sub_index:8]`** | `0x3100`/`0x3101`/`0x7109`，高字节是类别 |
| `dword[3]` | 常量 / 少量取值 | 36 种取值 |
| `dword[4]` | 恒 `0xFFFFFFFF` | 完全恒定 |
| **`dword[7]`** | **字符串偏移（相对文件起始）** | **13,162/13,162 全部有效** |
| `dword[17]` | 恒 0 | 完全恒定 |

实测样例（`article.kst` 前几条）：

```
idx  line  cat  sub  typ   text
  0    10   49    0   14   R:GERショート_切      ← 短剑_斩
  1    11   49    0   14   R:GERショート_貫      ← 短剑_贯
  3    13   49    1   14   R:GERロング           ← 长剑
  4    14   49    2   14   R:GERバスター_切      ← 大剑_斩
 10    20   49    5   16   R:GERバックラー       ← 小盾
 11    21   49    7   16   R:GERタワー           ← 塔盾
 12    22  113    9   15   DBGx25 Schusswaffe   ← 德语调试武器
```

`line` 字段（`dword[0]` 低 16 位）严格递增 → 是**表内行号**。
`cat`（`dword[1]` 高字节）区分资源类别（49=武器，113=德语调试条目，911361=异常值）。

### 5.3 验证结果

| 检查 | 结果 |
|---|---|
| `article.kst` 全部 13,162 条字符串能否解出 | **13,162 / 13,162 = 100.00%** |
| 索引 `resolve_key` 命中总数 | 13,162，与 `numrecord` 完全一致 |
| 字符串偏移单调性 | 递增（delta = 字符串长度+2，2 字节对齐） |

解出的文本涵盖中/日/德三语真实游戏资源：

```
R:GERショート_切     Garuda-Knochen      NPC_011N_Top 色8
1:ガンマスター       5:八尋盾             Donnernde Jungfrau II
```

### 5.4 不同 kst1 的列布局不同（重要）

**机制相同，但字符串偏移所在的列不同。** 实测两种布局：

| 文件 | stride | 字符串偏移列 | 语义 |
|---|---|---|---|
| `article.kst` | 76 | **`dword[7]`** | 单字段（名称） |
| `avatar_translate.kst` | 24 | 待验证 | — |
| `mission.kst` | **312** | **`dword[73..77]`** | **多字段**（名称/描述/地点/时限） |

`mission.kst` 实测解出（德语版）：

| 列 | 内容 |
|---|---|
| `dword[73]` | `'Teufelsschweif'`（任务名） |
| `dword[74]` | `'1 Ogerschweif wurde in der Alten Stadt bestätigt...'`（任务描述，含换行） |
| `dword[75]` | `'Stadt der Gnade'`（地点） |
| `dword[76]` | `'Zeitlimit: 30:00'`（时限） |
| `dword[77]` | `''`（空串） |

> 由此可见 kst1 是**通用的行式数据库**：`stride` 是行宽，但**列的含义由外部 schema 决定**。
> `article.kst` 一行 76 字节里有 19 个 dword，只有第 7 个是字符串偏移；
> `mission.kst` 一行 312 字节里有 78 个 dword，第 73–77 个才是字符串列。
>
> 因此**不存在"通用的 kst1 记录解析"**——必须知道每个文件的列定义。
> 好在可以用统计法自动发现字符串列：逐个 dword 列测试"该值是否指向合法 kst 字符串"，
> 命中率高（>90%）的列即为字符串列。这个方法在本轮对两种布局都有效。

### 5.5 自动发现字符串列（定稿算法）

```python
def find_string_columns(d, rec_off, stride, numrec, probe=300,
                        threshold=0.90):
    tail_start = rec_off + numrec * stride
    cols = []
    n_probe = min(numrec, probe)
    for pos in range(stride // 4):
        vals = [u32(d, rec_off + r * stride + pos * 4) for r in range(n_probe)]
        if len(set(vals)) <= 1:                 # 常量列 -> 不是偏移
            continue
        if min(vals) < tail_start:              # 偏移必须 >= 记录表末尾
            continue
        texts = [read_kst_string(d, v) for v in vals]
        good = sum(1 for t in texts if looks_like_text(t))
        if good >= n_probe * threshold:
            cols.append((pos, good, n_probe))
    return cols
```

**实测结果**：

| 文件 | stride | 发现的字符串列 |
|---|---|---|
| `avatar_translate.kst` | 16 | `[1]` |
| `article.kst` | 76 | `[7]` |
| `mission.kst` | 312 | `[73][74][75][76]` |

**17/18 文件完全成功**，唯一例外见 §5.6。

#### 为什么不用"取值多样性"做判据

我试过用"唯一值占比 >= 25%"排除低基数列，结果把 `mission.kst` 的
`[75]`（地点名）和 `[76]`（`"Zeitlimit: 30:00"`）误杀了 —— 它们的重复率很高，
但**确实是字符串列**。

正确的做法是引入**文本质量判据**（`looks_like_text`）：
可打印字符占比 ≥ 95%、控制字符比例不过高、长度 ≥ 2。

#### 已排除的陷阱列

`avatar_translate.kst` 的 `dword[3]` 会骗过简单判据：
它的取值恒为 `373280`，**恰好等于记录表末尾**（`147488 + 14112*16`），
而那个位置刚好能读出一个"看似合法"的短串。

用"偏移必须 >= 记录表末尾"+"非常量"两条约束可以排除它。

---

### 5.6 ⚠️ 发现：俄语版文本使用**混合编码**

这是本轮**最重要的异常发现**，且已通过统计确定为一种明确的混合编码方案。

#### 现象

`ru/article.kst` 抽样 300 条，有 **273 条**含控制字符：

```
rec12 → 'Д\x11\x0c\x0b\x0f-\x1b\x1fш\x16\x0b x25'
rec24 → 'М\x0b\x16\x11\x1e \x1f\x1d\x1e\x1c\x1a\x15\x1d\x1e\x0e\x0b'
```

#### 统计证据（决定性）

对全部 13,162 条记录的原始字节做统计：

| 观测 | 数值 |
|---|---|
| 控制字节总数 | 34,587 |
| **控制字节的不同取值** | **仅 20 种** |
| **取值范围** | **全部落在 `0x0B`–`0x1F`（11–31）** |
| 同时存活的合法 UTF-8 西里尔字母 | `я`(1054) `ы`(971) `ь`(848) `К`(468) `ч`(443) `ш`(385) … |

最高频的控制码：

```
0x0B x4313    0x1A x3506    0x11 x3173    0x14 x2791
0x1C x2783    0x19 x2737    0x1E x2257    0x17 x2097
0x16 x2082    0x1D x1493    0x0E x1124    0x18 x929
```

#### 结论

俄语版使用的是**混合编码**：

- 大部分字符仍是标准 UTF-8（西里尔字母可以正常解出）
- 但**约 20 个高频字符**被替换成了单字节码 `0x0B`–`0x1F`

`0x0B` 出现 4,313 次，对应俄语最高频字母（`о` 或 `е`，两者在俄语中频率约 11% / 8.5%）。
这与"用 20 个槽位压缩最高频字符"的策略完全吻合。

> 证据强度：**强**（20 种取值 + 全落在 11–31 区间 + 频率分布符合自然语言）。
>
> 但 **20 个码到具体字母的映射表仍未找到**。exe 里没有 `cp1251` / `charconv` 相关字符串，
> 对照表可能在数据文件里，或需要结合语料统计反推（俄语字母频率 + 词形约束）。
> 这是当前 kst1 唯一的实质缺口。

#### 对工具的影响

读取器不能假定文本一定是 UTF-8，也不能靠"可打印率"盲选编码
（UTF-8 字节用 cp1251 解码同样可打印，只是变成无意义的西里尔乱码）。
当前实现按 **UTF-8 → 其它编码按可打印率打分 → UTF-8 替换兜底** 的顺序解码，
遇到俄语这种混合编码会解出乱码但**不丢数据**（`errors="replace"` 会保留 `\uFFFD` 标记）。

---

## 6. 工具与导出结果

### 6.1 模块与命令

| 文件 | 说明 |
|---|---|
| [`src/gecv/kst1.py`](../../src/gecv/kst1.py) | kst1 解析库（含索引、字符串、列自动发现、编码处理） |
| [`tools/ksttool.py`](../../tools/ksttool.py) | CLI：`info` / `sample` / `export` / `key` / `verify` |

```bash
# 结构摘要
python -m tools.ksttool info --gamedir "<game>" --path "<kst>"

# 导出全部为 TSV
python -m tools.ksttool export --gamedir "<game>" --all \
    --names <本地名字表.txt> --out out --format tsv

# 按 key 查询
python -m tools.ksttool key --gamedir "<game>" --path "<kst>" 255 256

# 全部自检
python -m tools.ksttool verify --gamedir "<game>" --names <本地名字表.txt>
```

### 6.2 导出实测结果（GER，18 个文件）

| 文件组 | 记录数 | 成功解析文本 | 字符串列 |
|---|---|---|---|
| `avatar_translate.kst`（6 语言） | 14,112 × 6 | 14,112 × 6 | `[1]` |
| `article.kst`（de/en/es/fr/it） | 13,162 × 5 | 13,162 × 5 | `[7]` |
| `article.kst`（**ru**） | 13,162 | **0**（混合编码未解） | — |
| `mission.kst`（6 语言） | 515 × 6 | 515 × 6 | `[73][74][75][76]` |
| **合计** | **166,734** | **153,572** | — |

**成功率 92.11%**。唯一的失败是整个 `ru/article.kst`（详见 §5.6）。

### 6.3 解出的真实内容示例

英语任务（`mission.kst`）：

```
[73] Devil's Tail
[74] 1 Ogretail confirmed in the Old City. Eliminate as soon as possible.
     Research identifies the outer shell...
[75] City of Mercy
[76] Time Limit: 30:00
```

武器表（`article.kst`）：

```
R:GERショート_切       R:GERバスター_破       R:GER火のショート
Garuda-Knochen        Donnernde Jungfrau II  NPC_011N_Top 色8
```

技能表：

```
1:ガンマスター    5:八尋盾    1:遂行技能Ⅳ    5:蛮勇の技Ⅲ
```

> ⚠️ 注意 `mission.kst` 的 `[75]` / `[76]` 语义并不稳定：
> 有的记录 `[75]` 是地名（`City of Mercy`）配 `[76]` 时限，
> 有的记录 `[75]` 是人名（`Lindow`）配 `[76]` 地名。
> 说明这两列可能是"多个可选字段"而非固定含义，**尚未完全解读**。

### 5.5 尚未解读

| 项 | 状态 |
|---|---|
| `mission.kst` 的记录布局 | ❌ 未知（stride 312，列布局不同） |
| `dword[0]` 的 `top` 字节 | ⚠️ 疑为偏移高字节或标志 |
| 头部 `+0x20` | ⚠️ 恒 0 |
| 头部 `+0x24` | ⚠️ 依文件类型而异（215 vs 0x3FFFFF） |
| schema 定义在哪 | ❌ 未找到 |

---

## 6. 尚未解读的字段

| 位置 | 现象 | 猜测 |
|---|---|---|
| 头部 `+0x04` | 恒 0 | 版本号或标志（`kst version mismatch` 警告串提示存在版本字段） |
| 头部 `+0x20` | 恒 0 | 保留 |
| 头部 `+0x24` | `mission`=215、`article`=0x3FFFFF | 可能是 `numBlocks` 上界或哨兵；需更多样本裁定 |
| 记录内部 | 未解析 | 下一步 |

> `0x24` 值得注意：`0x3FFFFF` = 4,194,303 是 `(1<<22)-1`，像一个"无上限"哨兵值；
> 而 215 更像真实计数。这两者语义不同，说明该字段含义依文件类型而异，暂不下结论。

---

## 7. 复现方法

```python
import struct

def resolve(path_or_bytes, key):
    d = parse_blz4(path_or_bytes) if is_blz4(d) else d
    stride, numrec, idx_off, rec_off = struct.unpack_from("<4I", d, 0x08)
    nblocks, maxkey = struct.unpack_from("<2I", d, idx_off)
    b, k = divmod(key, 256)
    blk = idx_off + 8 + 36 * b
    base = struct.unpack_from("<I", d, blk)[0]
    bitmap = struct.unpack_from("<8I", d, blk + 4)
    if not (bitmap[k // 32] >> (31 - (k % 32))) & 1:
        return None
    idx = base + popcount_prefix(bitmap, k)
    return d[rec_off + idx * stride : rec_off + (idx + 1) * stride]
```

---

## 8. IDA 定位线索（供后续复用）

| 项 | 地址（GER） |
|---|---|
| `"kst1"` 断言串 | `0x116555C` |
| `pTr2Dat` 同级的 `src\lib\kst.c` | `0x116545C` |
| 断言表区域 | `0x15BB7B0` 一带（16 字节/条：源文件/行号/函数名/断言） |
| `kstFetchRecordByIndex` 实现 | `0x19A0A44` |
| `kstFetchRecordByKey` 实现 | `0x19A0A84` |
| 索引查找 | `0x19A0CC7` |
| 块内查找 | `0x19A0C67` |
| popcount 前缀和 | `0x19A09C5` |
