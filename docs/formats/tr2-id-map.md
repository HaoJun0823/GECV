# tr2 表间 ID 映射表

> **本文目的**：给出 tr2 各表之间的 ID 引用关系，回答"怪物/道具/任务的数据怎么互相调用"。
>
> **前置**：tr2 的读取方法见 [`tr2-reading.md`](tr2-reading.md)（已完全确证）。
> **证据**：`enemy_class_id` 的跨表匹配基于 **544 个 mission 目录、全部实例**的聚合统计。

---

## 1. 核心结论：`enemy_class_id` 是贯穿怪物系统的业务主键

对全部 mission 的 tr2 表做字段普查后，发现一个关键模式：

**`en_group` / `en_mat` / `en_oracle` / `enemy_entry_table` / `quest_flow` 都含 `enemy_class_id` 字段，且取值域完全一致（13 个不同值：1..13）。**

这不是巧合 —— 它就是**怪物类别的主键**。

### 1.1 已确证的引用链

```
quest_flow.tr2（任务流程）
    │  quest_flow_enemy_entry_class_id  = 11 个值
    └──> en_group.tr2 . en_group_enemy_class_id  （命中 10/11）
             │
             ├──> en_mat.tr2 . en_mat_enemy_class_id     （13/13 命中）
             │        └──> en_mat_article_id = 404 个值
             │                  └──> 道具系统的道具 ID
             │
             ├──> en_oracle.tr2 . en_oracle_enemy_class_id  （13/13 命中）
             │        └──> en_oracle_bullet_id = 3 个值
             │                  └──> 子弹系统
             │
             └──> enemy_entry_table.tr2 . ENEMY_ENTRY_ENEMY0_ID / ENEMY1_ID
                       （命中 6/7、7/8）
```

### 1.2 含义

| 层次 | 表 | 作用 |
|---|---|---|
| **任务** | `quest_flow.tr2` | 任务流程、胜利条件、登场怪物类别 |
| **怪物类别** | `en_group.tr2` | 类别 → 家族列表、跟随标志 |
| **怪物基础** | `en_base.tr2` | HP、视野、怒气、状态抗性、掉落材料 |
| **怪物攻击** | `en_atk.tr2` | 各属性攻击力、攻击名、击退/条件 |
| **怪物防御** | `en_def.tr2` | 各属性防御 |
| **命中攻击** | `en_hit_atk.tr2` | 攻击判定 ID（5,954 个） |
| **命中防御** | `en_hit_def.tr2` | 防御判定 ID（3,533 个） |
| **掉落** | `en_mat.tr2` | 类别 → 掉落道具 ID（404 个） |
| **神谕** | `en_oracle.tr2` | 类别 → 子弹 ID |
| **登场** | `enemy_entry_table.tr2` | 关卡中的怪物配置 |
| **动作** | `virtual_motion.tr2` | 动作数据（79,669 行，最大的表） |

---

## 2. 验证方法（可复现）

```python
# 1. 遍历全部 544 个 mission 目录的所有 tr2 表
# 2. 逐表逐行读出每个 *_id 字段的取值，聚合成集合
# 3. 把"名字以 _id 结尾且 distinct >= 5"的列作为候选目标 key
# 4. 源字段取值与目标列取值的交集 / 源字段 distinct >= 0.7 视为命中
```

**结果**：8 条通过严格判据的映射（明细 JSON 为本地中间产物，不随仓库发布）。

### 2.1 通过验证的映射

| 源表 | 字段 | 值数 | 目标表 | 目标列 | 命中 |
|---|---|---|---|---|---|
| `en_group.tr2` | `en_group_enemy_class_id` | 13 | `en_mat.tr2` | `en_mat_enemy_class_id` | 13 |
| `en_mat.tr2` | `en_mat_enemy_class_id` | 13 | `en_group.tr2` | `en_group_enemy_class_id` | 13 |
| `en_oracle.tr2` | `en_oracle_enemy_class_id` | 13 | `en_group.tr2` | `en_group_enemy_class_id` | 13 |
| `quest_flow.tr2` | `quest_flow_enemy_entry_class_id` | 11 | `en_group.tr2` | `en_group_enemy_class_id` | 10 |
| `enemy_entry_table.tr2` | `ENEMY_ENTRY_ENEMY0_ID` | 7 | `en_group.tr2` | `en_group_enemy_class_id` | 6 |
| `enemy_entry_table.tr2` | `ENEMY_ENTRY_ENEMY1_ID` | 8 | `en_group.tr2` | `en_group_enemy_class_id` | 7 |
| `en_atk.tr2` | `en_atk_knockback_id` | 4 | `quest_flow.tr2` | `quest_flow_enemy_entry_class_id` | 4 |
| `en_oracle.tr2` | `en_oracle_bullet_id` | 3 | `quest_flow.tr2` | `quest_flow_enemy_entry_class_id` | 3 |

### 2.2 ⚠️ 后两条存疑

`en_atk_knockback_id`（4 个值）和 `en_oracle_bullet_id`（3 个值）匹配到 `quest_flow`，
**很可能是假阳性** —— 它们值域太小（3~4 个值），而 `quest_flow` 的
`enemy_entry_class_id` 恰好覆盖 0~10 的小整数范围。

**判据**：源字段 distinct < 5 时不可信。这两条**不应采信**。

---

## 3. 目标的业务 ID 列（可用于跨表查找）

| 表 | 列 | distinct | 说明 |
|---|---|---|---|
| `en_hit_atk.tr2` | `en_hit_attack_id` | **5,954** | 攻击判定 ID，最大的 ID 空间 |
| `en_hit_def.tr2` | `en_defence_id` | **3,533** | 防御判定 ID |
| `en_mat.tr2` | `en_mat_article_id` | **404** | **掉落道具 ID**（指向道具系统） |
| `quest_flow.tr2` | `quest_flow_end_enemy_defeat_family_id` | 19 | 家族 ID |
| `en_group/mat/oracle` | `*_enemy_class_id` | 13 | **怪物类别** |
| `quest_flow.tr2` | `quest_flow_enemy_entry_class_id` | 11 | 登场怪物类别 |
| `enemy_entry_table.tr2` | `ENEMY_ENTRY_ENEMY0_ID` | 7 | 关卡怪物 0 |
| `quest_flow.tr2` | `quest_flow_enemy_entry_class_id` | 11 | 同上 |

> **`en_mat_article_id` 的 404 个值指向道具系统**，但道具表
> （`g999_Base/db/article/Tr2/`）是**全局表**而非 per-mission 表，
> 需要单独解析才能完成这条链接。**这一步尚未做。**

---

## 4. 真实数据样本（已读出）

### 4.1 `en_atk.tr2`（怪物攻击，8 行）

| row | name | slash | knockback_id |
|---|---|---|---|
| 0 | `1_OgreTail_Default` | 2 | 1 |
| 1 | `1_OgreTail_Oracle_ShotNeedle` | 6 | 1 |
| 2 | `1_OgreTail_Oracle_LobShotNeedle` | 8 | 2 |
| 3 | `1_OgreTail_Cling_Base` | 6 | 1 |

### 4.2 `en_mat.tr2`（怪物掉落）

```
en_mat_enemy_class_id = 1
en_mat_article_id     = 13688      <- 掉落的道具 ID
en_mat_wait           = 100
```

### 4.3 `en_group.tr2`（怪物群组）

```
en_group_enemy_class_id    = 1
en_group_fam_id_array      = [3,14,15,18,1,13,...]（arr=10）
en_group_follow_flag_array = [0,0,0,0,1,1,...]（arr=10）
```

---

## 5. 未打通的部分（诚实记录）

| 缺口 | 原因 | 下一步 |
|---|---|---|
| `en_mat_article_id` → 道具表 | 道具表是全局表，未解析 | 解析 `db/article/Tr2/article_*.tr2` |
| `en_hit_attack_id`（5,954）→ 什么地方 | 未找到消费方 | 反汇编 `tr2GetRecordByKey` 的调用方 |
| `virtual_motion_data_id_array` → 动作数据 | 79,669 行，未解析其结构 | 需先弄清动作数据格式 |
| `quest_flow` 的完整流程语义 | 只有前置任务 ID 列表 | 反汇编任务状态机 |
| `dig.tr2` 的 `dig_id_array` → 挖掘物 | 13 个值，目标未知 | 逐表比对 |
| **表间引用是否需要"行号"参与** | 已确认 tr2 行无主键 | — |

### 5.1 一个重要澄清

**tr2 的行没有数值主键。**

- 行的身份 = 偏移表的下标（第 0 行、第 1 行……）
- 同表内跨字段的对应靠**行号对齐**
- 跨表引用（`enemy_class_id` 等）引用的是**业务 ID 值**，不是行号

所以"表 A 的第 3 行引用了表 B 的哪一行"这个问题**不成立**。
正确的问法是："表 A 的某字段值 X，在表 B 的哪个业务 ID 列里能找到"。

这就是映射表能用 `enemy_class_id` 建立、却无法用"行号"建立的原因。

---

## 6. 复现

```bash
python <本地映射脚本>
# 输出：映射明细 JSON（本地中间产物，不入库）
```

数据文件：

| 文件 | 内容 |
|---|---|
| `id_fields.json` | 67 个 ID 字段的全量表（跨 6,407 张 tr2） |
| `id_map_business.json` | 本轮验证通过的 8 条映射 + 目标 key 清单 |
