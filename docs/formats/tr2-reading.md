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

### 2.3 元数据区（位于 name_offset 处）

| 相对偏移 | 类型 | 字段 | 实例（`en_base_hp`） |
|---|---|---|---|
| `+0x00` | char[0x34] | 字段名（NUL 结尾） | `en_base_hp` |
| `+0x34` | 3 字节 | 版本标记 | `02 DF 07` |
| **`+0x40`** | char[16] | **类型字符串** | `UINT32` |
| `+0x74` | u8 | 格式字符 | `L` |
| `+0x75` | u8 | 元素宽度 | `4` |
| `+0x76` | u16 | 数组元素数 `arr` | `4` |
| `+0x78` | — | 属性/标志 | — |
| **`+0x80`** | i32 | **数据相对偏移 `rel`** | `0x8C` (140) |
| `+0x84` | — | — | — |
| **`+0x80 + rel`** | — | **该字段的数据起点** | `0x870+140 = 0x8FC` |

### 2.4 决定性验证

对 `en_base.tr2` 的 `en_base_hp`（`UINT32`, `arr=4`）：

```
元数据区 @0x870，rel=0x8C(140)  =>  数据 @0x8FC
读到: 0x320=800, 0x397=919, 0x410=1040, 0x488=1160
```

**四个递增的整数 —— 这正是怪物血量的四档数值，完全合理。**

同表其它字段：

| 字段 | 类型 | arr | 读到的值 |
|---|---|---|---|
| `en_base_name` | ASCII | 1 | `'OgreTail_1'` |
| `en_base_res_name` | ASCII | 1 | `'MS_101N_ouga'` |
| `en_base_display_name` | UTF-8 | 1 | `'Bewegliches Ziel'`（德语"移动靶"） |
| `en_base_hp` | UINT32 | 4 | `[800, 919, 1040, 1160]` |

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

### 5.2 ⚠️ 为什么映射表**尚未建立**

这是本轮**未完成**的部分，如实记录原因。

**尝试过的三种方法，都不成立：**

| 方法 | 结果 | 失败原因 |
|---|---|---|
| 按字段名前缀推测（`en_`→enemy） | 不可靠 | 只能给出"大概方向"，无法确认具体表与具体列 |
| 取值 ⊆ 目标表 ID 集合 | 假阳性严重 | 目标表基数太低（如 `en_def.tr2` 仅 4 个不同值），任何小整数都"命中" |
| 加入统计显著性（lift ≥ 3） | 只剩 2 条，且存疑 | 仍受低基数影响；且 `quest_flow` 的值域太小 |

**根本原因**：我**还没有找到每张表的"记录主键 ID"在哪里**。

- 我目前能读的是**字段数据值**（如攻击力 172、道具 ID 13688）
- 但"这张表有哪些记录、每条记录的 ID 是多少"——也就是 Record 的 key —— **还没定位**
- 没有这个，就无法建立"ID → 记录"的映射，也就无法验证跨表引用

### 5.3 下一步应做什么（明确的技术路线）

要用 IDA 确认 tr2 的记录主键：

1. 反编译 `tr2GetRecordByKey` / `tr2FetchRecord` 相关函数（在 `src\app\tr2.c`）
2. 确认 `tr2GetRecordCore` 里 `RecordIndex` 的构造方式
3. 找到"ID 列"是哪个字段（很可能是 Field 表的第 0 项，或元数据里某个固定槽）

**已知线索**（来自 `tr2_ida_confirmed.md`）：
- 诊断串 `"aRecordIndex[i=%d].nID = aIDs[j=%d]"` 说明存在 `aRecordIndex` 数组，每项有 `nID`
- `tr2GetRecordHead` 在 `src\app\tr2.c` 第 158 行
- `tr2GetRecordCore` = `0x1B8855F`（GER）

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
| **每张表的记录主键 ID 在哪** | **阻塞整个映射表** |
| 字段名前缀 → 目标表的完整映射 | 只有方向性推测 |
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
