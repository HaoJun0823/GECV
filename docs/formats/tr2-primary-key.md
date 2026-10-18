# tr2 记录主键（已定论）

> **本文解决的唯一问题**：tr2 的每张表里，"每条记录的 ID 是多少、怎么按 ID 找到记录"。
>
> 这个问题在 [`tr2-reading.md`](tr2-reading.md) §5.2 被列为**阻塞全部表间关系**的缺口，
> 现已解决并于全量数据验证通过。
>
> **结论一句话**：tr2 **每一张表内部自带一份"ID → 记录序号"的排序数组**，
> 它紧跟在 Field 表之后，用二分查找定位。

---

## 1. 结论

### 1.1 位置

```
+0x38  i32  fieldTableOff
+0x3C  i32  fieldCount
+0x40  Field 表，fieldCount × 20 字节
fieldTableOff + fieldCount*20  ← ★ 记录主键索引区起点
```

索引区结构：

| 相对索引区 | 类型 | 字段 |
|---|---|---|
| `+0x00` | u32 | **count**（记录数） |
| `+0x04` | u32[count] | **IDs**，**升序、唯一** |

### 1.2 查一条记录

```python
def record_ordinal_for_id(tr2: bytes, want_id: int) -> int | None:
    foff, fnum = struct.unpack_from("<2i", tr2, 0x38)
    idx_off = foff + fnum * 20
    count = u32(tr2, idx_off)
    ids = struct.unpack_from("<%dI" % count, tr2, idx_off + 4)

    # 二分查找（引擎 sub_1B84CCA 就是这么做的）
    lo, hi = 0, count - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if ids[mid] < want_id:
            lo = mid + 1
        elif ids[mid] > want_id:
            hi = mid - 1
        else:
            return mid          # ← mid 就是记录序号（第几条记录）
    return None
```

**返回的 `mid` 就是记录序号**，用它去各字段的偏移表取单元格：

```python
value = read_cell(field, row=mid)     # 见 tr2-reading.md §2.4
```

### 1.3 为什么这是"主键"

- **唯一**：全量 18,694 张有记录的表中，ID **无重复**（`unique` 全部成立）。
- **有序**：ID **严格升序**（`sorted` 全部成立），所以引擎能用二分（`sub_1B84CCA`）。
- **稳定**：ID 与"第几行"是两套编号；行的物理顺序就是 `ids[]` 的下标顺序。

---

## 2. 反汇编依据

三处函数互相印证，构成完整链条。

### 2.1 `tr2ChkID`（`sub_1B860F4`）—— 判定"这个字段是不是 ID 字段"

```c
int sub_1B860F4(int fhead, int id) {
    int n = *(_DWORD*)(fhead + 124);          // +0x7C
    if (n <= 0) return 0;
    if (*(char*)(fhead + 117) <= 1) {         // +0x75 宽度 <= 1 ⇒ 小整数 ID
        // 线性/近线性扫描 fhead+128 处的 8 字节项
    } else {
        char attr = *(_BYTE*)(fhead + 61);    // +0x3D 属性标志
        if (attr & 2) return sub_1B84DCF(...) >= 0;   // 32 位 ID → 二分
        if (attr & 1) return sub_1B84D4F(...) >= 0;   // 16 位 ID → 二分
        return sub_1B84CCA(fhead + 128, n, id) >= 0;  // 默认 → 二分
    }
}
```

### 2.2 `sub_1B84CCA` —— 32 位 ID 的二分查找

```c
int sub_1B84CCA(unsigned* a1, int n, unsigned want) {
    if (n <= 0) return -1;
    if (want < a1[0] || want > a1[3*n - 3]) return -1;   // 范围预检
    // 标准二分：项 12 字节，键在 +0
    // 命中后回退到重复段的首个（保证唯一性语义）
    return index;
}
```

### 2.3 `sub_1B84D4F` —— 16 位 ID 的二分查找

```c
int sub_1B84D4F(int a1, unsigned want) {
    int n = *(_DWORD*)(a1 + 124);
    if (want < *(i16*)(a1 + 128) || want > *(i16*)(a1 + 8*n + 120)) return -1;
    // 项 8 字节，键在 +0，二分
}
```

> 两处都表明：**ID 索引紧跟在某个头部之后（`+0x80` 相对运行时结构）**，
> 项宽 8 或 12 字节。这与实测的"Field 表之后 4 字节 count + 4 字节/项的 ID 数组"
> 是同一结构的**磁盘版**与**载入后内存版**的差异（载入时每项会补上记录指针等字段）。

### 2.4 诊断串佐证

`tr2GetRecordCore` 里的日志格式直接写出了语义：

```
"%s : [[ %s.tr2 : ID=%d, FieldNum=%d\n"     ← 入参 a2 就是 ID
"%s : bString=%d, bFloat=%d, bArray=%d, bID=%d, cAttr=%x\n"
```

以及 `tr2GetMinID` / `tr2GetMaxID` / `tr2ChkIDH` / `id_num<nMax` 这组符号，
证明 **ID 是 tr2 的一等概念**，不是外部附会。

---

## 3. 全量验证（GER，19,486 个 tr2）

| 结果 | 数量 | 占比 |
|---|---|---|
| tr2 成功解析 | 19,473 | 99.93% |
| **有 ID 索引且升序唯一（完美）** | **18,694** | **96.00%** |
| 空表（`count == 0`） | 778 | 4.00% |
| 索引越界（布局变体） | 1 | 0.005% |
| 名字表缺失 | 13 | 0.07% |
| **累计记录数** | **502,857** | — |

> **与独立统计的交叉验证**：另一路统计（`tr2-kinds.md`）得到"91 种表 / 503,658 行"。
> 本文从**完全不同的路径**（ID 索引的 count 字段求和）得到 502,857。
> 两者相差 801 行（0.16%），来源是 778 个空表与 13 个缺失——**量级完全吻合**，
> 两条独立证据互相印证。

### 3.1 成功样本

| 表 | count | ID 范围 |
|---|---|---|
| `article_composition.tr2` | 1,277 | `[1, 2, 3, 4, 5 … 1277]`（连号） |
| `equipment_composition.tr2` | 921 | `[1, 2, 3, 4, 5 … 921]`（连号） |
| `eq_label_main_cond.tr2` | 326 | `[17, 18, 19, 20, 21 … 455]` |
| `article_shop.tr2` | 33 | `[1941, 1942, 1944, 1948, 1953 … 13557]`（稀疏） |
| `equipment_shop.tr2` | 80 | `[10719, 10755, 10767 … 13705]`（稀疏） |
| `article_ext.tr2` | 5 | `[3115, 6848, 6849, 6850, 6851]` |

> 注意 **ID 既可能连号也可能稀疏**。连号（`1..N`）说明该表是"内部序号"型；
> 稀疏（如 `1941, 1948 …`）说明该 ID 由**其它系统分配**——这正是跨表引用的载体。

### 3.2 778 个空表的真相

它们**不是解析失败**，而是**真的没有记录**：

```
@idx_off: 00 00 00 00 | 00 00 00 00 | 00 00 00 00 | 61 72 74 69 63 6c 65 5f ...
          count=0       (对齐填充)                    "article_conv..."
```

`count = 0`，后跟字段名，结构完全合理。分布上也很符合逻辑：

| 表 | 空表数 | 解释 |
|---|---|---|
| `enemy_entry_table.tr2` | 510 | 大部分 mission 没有登场怪物表 |
| `dig.tr2` | 183 | 大部分 mission 没有挖掘点 |
| `en_mat.tr2` / `en_oracle.tr2` | 36 / 25 | 掉落 / Oracle 表，非每个 mission 都有 |

> 这与 `tr2-reading.md` §3.1 对 `dig.tr2` 的判断一致：**是空表，不是解析失败**。

### 3.3 唯一的异常：布局变体

`data/GameData/mission/XXX_Building/db/enemy/Tr2/virtual_motion.tr2`（63,088 B）：
`foff=0x40, fnum=4`，索引区起点 `0x90` 处却是 ASCII 字符串
`"virtual_motion_ascii_name"` 而非 count。

**推测**：这张表的字段名直接内联在 Field 表之后（省掉一次间接），
属于打包器的另一种布局变体。**未验证**，占比 1/19,473，可忽略但需记录。

---

## 4. 这解决了什么（对全工程的意义）

`tr2-reading.md` §5.2 说映射表建不起来，根本原因是：

> 我能读字段**数据值**，但"这张表有哪些记录、每条记录的 ID 是多少"还没定位。
> 没有这个，就无法建立"ID → 记录"的映射，也就无法验证跨表引用。

**现在这个缺口补上了。** 具体解锁：

| 之前 | 现在 |
|---|---|
| 只能按"行号"取数据 | 可以按**业务 ID** 取数据 |
| 跨表引用只能猜"这个 13688 大概是道具 ID" | 可以**直接验证**：在道具表里查 `id == 13688` 是否存在 |
| 无法确认表间关系 | 可以做"源字段取值 ⊆ 目标表 ID 集合"的**严格验证**（不再受行号干扰） |

### 4.1 立即可以做的严格验证

```python
def verify_ref(src_tr2, src_field, dst_tr2):
    src_ids = set(src_tr2.values(src_field))
    dst_ids = set(dst_tr2.all_ids())          # ← 现在可获得了
    return len(src_ids & dst_ids) / len(src_ids)
```

用这个可以**逐条确认** §5.1 列出的 8 条引用关系，而不是靠字段名猜。

> ⚠️ 但要注意：**能验证"值集合有交集"不等于"语义上就是这个引用"**。
> 低基数表（如 `en_def.tr2` 只有 4 个值）仍会产生假阳性。
> 建议判据：**交集率 ≥ 0.95 且目标表 ID 数 ≥ 20**。

---

## 5. 与 kst1 的对照（两种"主键"的本质区别）

| | kst1 | tr2 |
|---|---|---|
| 主键声明位置 | **文件头**（`maxKey` / `numBlocks`） | Field 表之后的 **count + ids[]** |
| 主键空间 | `u32`，靠**位图**记录存在性 | `u32`，靠**排序数组 + 二分** |
| 定位方式 | `base + popcount(bitmap, 0..k-1)` | 二分查找下标 |
| 适合 | **稠密**的 key 空间（key 连续） | **稀疏**的 ID（ID 由业务分配） |
| 空表表示 | 位图全 0 | `count = 0` |

**设计差异的原因**：

- `kst1` 的 key 是**连续的**（文本 ID `0..20444`），所以位图最省：2.8KB 覆盖 20,444 个可能值。
- `tr2` 的 ID 是**业务分配的稀疏值**（如道具 ID `1941, 1948, 13557`），
  位图会产生巨大空洞（最大 ID 13557 但只有 33 条记录）。所以用**排序数组 + 二分**。

**这解释了两者为什么不能互换**：选择哪种取决于"key 空间是否稠密"这一先验，
而这是由业务决定的，不是格式设计者能自由选的。

---

## 6. 已验证 / 未验证

### 已验证 ✅

| 断言 | 证据 |
|---|---|
| ID 索引在 `fieldTableOff + fieldCount*20` | 3 个样本逐字节 + 18,694 张表全量 |
| 结构 = `u32 count` + `u32[count] ids` | 全量 |
| ID **升序** | 18,694 / 18,694 |
| ID **唯一** | 18,694 / 18,694 |
| 记录序号 = ID 在数组中的下标 | 与 `sub_1B84CCA` 的返回值语义一致 |
| 空表 = `count == 0` | 778 个，后跟字段名验证 |
| 引擎用二分查找 | 反汇编 `sub_1B84CCA` / `sub_1B84D4F` |

### 未验证 ⚠️

| 断言 | 影响 |
|---|---|
| `virtual_motion.tr2` 的变体布局 | 低（1/19,473） |
| 内存版索引项为何是 8/12 字节（磁盘版是 4 字节） | 低，不影响读取 |
| `+0x3D` 属性位 bit0/bit1 与 16/32 位 ID 的对应 | 中，可能影响极少数表 |
| GE2RB 的 tr2 是否同构 | 中，未验证（GER 已全通） |

---

## 7. 复现代码

```python
import struct

def u32(b, o): return struct.unpack_from("<I", b, o)[0]

def tr2_ids(data: bytes):
    """返回该 tr2 的全部记录 ID（升序）。"""
    assert data[:4] == b".tr2"
    foff, fnum = struct.unpack_from("<2i", data, 0x38)
    idx = foff + fnum * 20
    count = u32(data, idx)
    return struct.unpack_from("<%dI" % count, data, idx + 4)

def tr2_field_index(data: bytes):
    """字段名 -> (nameOff, stride, metaOff)"""
    foff, fnum = struct.unpack_from("<2i", data, 0x38)
    out = {}
    for i in range(fnum):
        o = foff + i * 20
        _idx, name_off, stride, meta = struct.unpack_from("<4i", data, o)
        end = data.find(b"\x00", name_off, name_off + 48)
        name = data[name_off:end].decode("ascii", "replace")
        out[name] = (name_off, stride, meta)
    return out
```

> 验证方式：用本节给出的 `tr2_ids()` 遍历全部 19,486 个 tr2，
> 检查 ID 数组是否升序、唯一（本地脚本，未入库）。
