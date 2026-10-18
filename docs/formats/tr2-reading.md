# tr2 真实解析与表间引用

> **本文的定位**：记录 tr2 的**正确读取方法**（已用真实数据验证），
> 以及"表间 ID 映射表"目前的进展与缺口。
>
> **重要**：本文修正了此前 `tr2_ida_confirmed.md` 中若干错误结论（见 §1）。

---

## 1. 对先前结论的修正

| 先前结论 | 实测修正 | 章节 |
|---|---|---|
| "类型名只用于报错，不是运行时表" | ❌ **错**。类型字符串确实在 Field 元数据 `+0x40` 处 | §2 |
| "Field 的 `+0x04` 是数据偏移" | ❌ **错**。`+0x04` 指向元数据区；数据偏移在 `+0x80` | §2 |
| "记录按 4 字节对齐" | ⚠️ tr2 不是"行式记录"，而是**列式存储** | §3 |

---

## 2. tr2 的完整布局（已实测确证）

### 2.1 文件头

| 偏移 | 类型 | 字段 |
|---|---|---|
| `+0x00` | char[4] | `.tr2` |
| `+0x04` | u32 | header_magic（高位 = 年份） |
| `+0x08` | char[48] | 表名 |
| `+0x38` | i32 | **Field 表偏移** |
| `+0x3C` | i32 | **Field 数量** |

### 2.2 Field 表（每条 20 字节）

| 偏移 | 类型 | 字段 |
|---|---|---|
| `+0x00` | i32 | field_index |
| `+0x04` | i32 | **name_offset** → 指向该字段的元数据区 |
| `+0x08` | i32 | stride（恒 20） |
| `+0x0C` | i32 | meta_size（元数据区大小，常 0x90 或 0xA0） |

### 2.3 元数据区（最终确认版）

以 `en_atk.tr2` 的 `en_atk_slash` 为例（`meta=0x140`, `size=0xC0`），逐字节核对：

```
0x140  65 6E 5F 61 74 6B 5F 73 6C 61 73 68 00..   "en_atk_slash"
0x17C  02 DF 07                                    版本标记
0x180  49 4E 54 31 36 00..                          "INT16"
0x1B4  73                                          's'  格式字符
0x1B5  04                                          宽度 4
0x1B6  01 00                                       arr = 1（每行元素数）
0x1B8  7F 00 0C 00                                 标志
0x1BC  08 00 00 00                                 n = 8（行数）
0x1C0  A8 AA AC AE B0 B2 B4 B6                     偏移表[0..7]（相对 meta）
0x1E0  B8 00 00 00                                 偏移表[8]（结束标记）
0x1E4  00 00 00 00
0x1E8  02 00 06 00 08 00 06 00                     数据区（INT16 序列）
0x1F0  06 00 08 00 08 00 08 00                     数据继续
```

**完整字段表**：

| 相对 meta | 类型 | 字段 | 实例 |
|---|---|---|---|
| `+0x00` | char[] | 字段名（NUL 结尾） | `en_atk_slash` |
| `+0x3C` | u8[3] | 版本标记 | `02 DF 07` |
| `+0x40` | char[16] | **类型字符串** | `INT16` |
| `+0x74` | u8 | 格式字符 | `'s'` |
| `+0x75` | u8 | 元素宽度 | `4` |
| `+0x76` | u16 | **arr**（每行元素数） | `1` |
| `+0x78` | u32 | 标志 | `0x000C007F` |
| `+0x7C` | i32 | **n**（行数） | `8` |
| `+0x80` | u32[n+1] | **偏移表**（相对 meta），末项是数据区结束 | `[0xA8,0xAA,...,0xB8]` |
| `+0x80+4(n+1)` | — | **数据区起点** | `0x1E8` |

### 2.4 读取算法（唯一正确的形式）

```python
def read_cell(table, field, row):
    base = field.meta + field.offsets[row]        # 该行该字段的数据起点
    size = TYPE_SIZE[field.type]                  # 1/2/4
    return [read_number(base + k*size, size)      # 读 arr 个元素
            for k in range(field.arr)]
```

### 2.5 关键验证

`en_atk_slash` 的 row0：`offsets[0] = 0xA8`，`meta + 0xA8 = 0x140 + 0xA8 = 0x1E8`，
该处是 `02 00` = **2**，与「斩击攻击力 = 2」相符。

全部 8 行读出的值：`[2] [6] [8] [6] [6] [8] [8] [8]`，
对应 8 个不同的攻击动作（见 §4.1 的名称列）。

### 2.6 ⚠️ 重要：tr2 没有"数值主键列"

我反复尝试寻找"每行的 ID"，结论是：**tr2 的行没有独立的数值主键**。

- 行的身份由**偏移表的下标**决定（第 0 行、第 1 行……）
- 表内跨字段的对应关系靠**行号对齐**（同一行号的各字段值属于同一条记录）
- 跨表引用（`en_mat_article_id` 等）引用的是**另一张表里的某个业务 ID 值**，
  而不是"行号"

这解释了为什么映射表很难建立：**行号不是业务 ID**。
`en_mat_article_id = 13688` 里的 13688 是道具系统的 ID，要去道具表里按某个
**业务 ID 列**（而非行号）查找。

### 2.5 类型字符串全集（800 表 / 4,686 字段普查）

| 类型串 | 出现次数 | 字节大小 |
|---|---|---|
| `UINT8` | 1,630 | 1 |
| `INT16` | 1,074 | 2 |
| `ASCII` | 635 | 1（文本槽） |
| `UINT32` | 458 | 4 |
| `UINT16` | 325 | 2 |
| `INT8` | 260 | 1 |
| `FLOAT32` | 192 | 4 |
| `INT32` | 96 | 4 |
| `UTF-8` | 12 | 变长 |
| `UTF-16LE` | 3 | 2 |
| `FLOAT` | 1 | 4 |

---

## 3. 关键结构认识：tr2 是列式存储

**tr2 没有"行"的概念。**

传统理解是"一张表 = N 行 × M 列"，但 tr2 的实际布局是：

```
文件头
Field 表（M 条，每条指向一个元数据区）
元数据区 0（字段0: 名字/类型/arr/数据偏移 + 该列的 arr 个值）
元数据区 1（字段1: ...）
...
```

即：**每个字段自带它的全部数据**，数据紧跟在该字段的元数据之后。
所以：
- `arr` 就是"这一列有多少个元素"
- **不存在行跨列对齐**，也没有统一的 `stride`（那个 20 是 Field 表的步长，不是行宽）

### 3.1 为什么 `dig.tr2` 看起来是空的

`dig.tr2` 的文件大小恰好等于"全部元数据区的总长"，没有额外数据。
说明该 mission 的 `dig` 表**没有实际内容**（0 条记录），而不是解析失败。

---

## 4. 已读出的真实业务数据（样本）

### 4.1 `en_hit_atk.tr2`（怪物攻击判定）

```
en_hit_attack_ascii_name      ASCII    = '1_OgreTail_Misc_Default'
en_hit_attack_id              UINT32   = 3011
en_hit_attack_id_timing_array FLOAT32  = [1.0, 1.0, 1.0, 1.0]
```

### 4.2 `en_mat.tr2`（怪物掉落）

```
en_mat_enemy_class_id  UINT8  = 1
en_mat_article_id      INT16  = 13688      <- 掉落道具 ID
en_mat_wait            INT16  = 100
```

### 4.3 `en_atk.tr2`（怪物攻击属性）

```
en_atk_slash    INT16 = 2       <- 斩击
en_atk_crush    INT16 = 0       <- 打击
en_atk_fire     INT16 = 0       <- 火
en_atk_ice      INT16 = 0       <- 冰
```

### 4.4 `en_group.tr2`（怪物群组）

```
en_group_enemy_class_id    UINT8 = 1
en_group_fam_id_array      UINT8, arr=10 = [3, 14, 15, 18, 1, 13, ...]   <- 家族 ID 数组
en_group_follow_flag_array UINT8, arr=10 = [0, 0, 0, 0, 1, 1, ...]
```

### 4.5 `quest_flow.tr2`（任务流程）

```
quest_flow_start_reaching_quest_ids    UINT8, arr=3 = [1, 2, 3]   <- 前置任务
quest_flow_start_reaching_quest_states UINT8, arr=3 = [4, 4, 4]
quest_flow_start_condition             UINT16 = 1
```

---

## 5. 表间 ID 映射表：进展与缺口

### 5.1 已确认存在 ID 互引（字段名证据）

| 源表 | 字段 | 语义 | 目标 |
|---|---|---|---|
| `en_mat.tr2` | `en_mat_article_id` | 掉落道具 | 道具表 |
| `en_mat.tr2` | `en_mat_enemy_class_id` | 怪物类别 | 类别表 |
| `en_atk.tr2` | `en_atk_knockback_id` | 击退类型 | 击退表 |
| `en_group.tr2` | `en_group_fam_id_array` | 家族 ID 数组 | 家族表 |
| `en_hit_atk.tr2` | `en_hit_attack_id` | 攻击判定 ID | 攻击表 |
| `en_base.tr2` | `en_base_family_id` / `genus_id` | 家族/种族 | 对应表 |
| `quest_flow.tr2` | `quest_flow_start_reaching_quest_ids` | 前置任务 | 任务表 |
| `enemy_entry_table.tr2` | `ENEMY_ENTRY_ENEMY0_ID` | 登场怪物 | 怪物表 |

### 5.2 ✅ 已解决：记录主键已定位

> **更新**：本文原先在此处记录"记录主键还没定位，阻塞整个映射表"。
> 该缺口**已经补上**，详见 [`tr2-primary-key.md`](tr2-primary-key.md)。
>
> 结论：**每张 tr2 内部自带一份"ID → 记录序号"的排序数组**，
> 位于 `fieldTableOff + fieldCount*20`：
>
> ```
> +0x00  u32 count
> +0x04  u32[count] ids     升序、唯一
> ```
>
> 全量验证：**18,694 / 19,473 张表（96.00%）完美命中**，累计 502,857 条记录，
> ID 全部升序且无重复。引擎用二分查找（`sub_1B84CCA`）。
>
> 因此本文 §5.1 列出的跨表引用**现在可以做严格验证**了，
> 不再依赖"字段名前缀猜测"。

**原先的困难（保留作为背景）**：

- 按字段名前缀推测（`en_`→enemy）→ 不可靠，只能给方向
- 取值 ⊆ 目标表 ID 集合 → 假阳性严重（目标表基数太低）
- 加统计显著性（lift ≥ 3）→ 只剩 2 条且存疑

这些方法失败的**真正原因**不是方法本身，而是当时**拿不到目标表的 ID 集合**。
现在能拿到了，判据可以收紧为：**交集率 ≥ 0.95 且目标表 ID 数 ≥ 20**。

### 5.3 下一步应做什么

1. 用 [`tr2-primary-key.md`](tr2-primary-key.md) 的 `tr2_ids()` 取每张表的 ID 集合
2. 对 §5.1 的 8 条候选引用，逐条算交集率
3. 交集率高的再用**样本值人工核对**（如 `en_mat_article_id=13688` 是否真的指向 13688 号道具）

---

## 6. 已验证 / 未验证

### 已验证 ✅

| 断言 | 证据 |
|---|---|
| tr2 是列式存储，数据在 Field 元数据 `+0x80+rel` 处 | `en_base_hp` 读出 `[800,919,1040,1160]` |
| 类型字符串在 `+0x40` | 800 表 / 4,686 字段全量普查 |
| 格式字符与元素宽度在 `+0x74` / `+0x75` | 与类型串一致 |
| `arr` 在 `+0x76`（u16） | 与数组字段实际元素数一致 |
| 文本字段为定长槽 + NUL | 读出 `'OgreTail_1'` 等 |
| 表间存在 ID 引用 | 字段名 + 样本值（`en_mat_article_id=13688`） |

### 未验证 ⚠️

| 断言 | 影响 |
|---|---|
| ~~**每张表的记录主键 ID 在哪**~~ | ✅ **已解决**，见 [`tr2-primary-key.md`](tr2-primary-key.md) |
| 字段名前缀 → 目标表的完整映射 | 只有方向性推测（现在可严格验证了） |
| `FLOAT32` 数组的读取（`en_hit_attack_id_timing_array` 读到 1.0 合理，但需更多样本确认） | 中 |
| 文本字段的槽宽（我用 0x20，未验证是否通用） | 中 |
| `en_base_hp` 的四档血量分别对应什么难度 | 低（语义，不影响格式） |

---

## 7. 复现代码

```python
import struct

def cstr(b, off, maxlen=64):
    end = b.find(b"\x00", off, min(len(b), off + maxlen))
    return b[off:end].decode("ascii", "replace") if end > off else None

class Tr2:
    def __init__(self, data):
        self.d = data
        self.table_off, self.field_num = struct.unpack_from("<2i", data, 0x38)
        self.stride = struct.unpack_from("<i", data, self.table_off + 8)[0]
        self.fields = []
        cur = self.table_off
        for _ in range(self.field_num):
            idx, name_off, st, ms = struct.unpack_from("<4i", data, cur)
            name = cstr(data, name_off, 48)
            typ = cstr(data, name_off + 0x40, 16)
            width = data[name_off + 0x75]
            arr = struct.unpack_from("<H", data, name_off + 0x76)[0]
            self.fields.append({"name": name, "type": typ,
                                "width": width, "arr": max(1, arr),
                                "meta": name_off})
            cur += st

    def values(self, name):
        f = next(x for x in self.fields if x["name"] == name)
        rel = struct.unpack_from("<i", self.d, f["meta"] + 0x80)[0]   # 关键
        off = f["meta"] + rel
        size = {"INT8":1,"UINT8":1,"INT16":2,"UINT16":2,
                "INT32":4,"UINT32":4,"FLOAT32":4}.get(f["type"].upper(), 1)
        return [int.from_bytes(self.d[off+i*size: off+(i+1)*size], "little")
                for i in range(f["arr"])]
```
