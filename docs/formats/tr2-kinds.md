# tr2 表种类全量统计

> **本文回答**：tr2 一共有多少种表？每种是干什么的？每种定义了多少属性？
>
> **属性语义暂不解释**，只做统计与分类。
>
> **证据**：GER 全部 **19,486 个 tr2 文件**，解析成功 19,473（失败 13）。

---

## 1. 先纠正一个概念：tr2 没有"表种类"枚举

**反汇编结论**：`src\app\tr2.c` 里 tr2 是一个**通用列式表容器**，
没有任何"表种类 / schema 注册表"之类的机制。证据：

| 检查 | 结果 |
|---|---|
| `tr2*` 全部 107 个函数符号 | 全是通用读写（`tr2GetRecordCore`、`tr2GetFieldHead`…），无按种类的分支 |
| exe 内 `Sect_*` 枚举 | 属于 **PRES entry 的访存类型**（`Sect_Table/Local/String/Refer`），不是 tr2 表种类 |
| `p_tr2_table->Sect == Sect_Table` 断言 | 只说明"这个 PRES 条目是表"，不区分是什么表 |

**所以"表种类"是开发者按文件名约定形成的**，不是引擎强制的 schema。
但实测显示：**同名的表在任何地方结构都完全一致**（见 §3 的"字段集变体 = 1"），
说明命名约定被严格遵守，可以当作权威分类依据。

---

## 2. 总体数据

| 指标 | 数值 |
|---|---|
| tr2 文件总数 | **19,486** |
| 解析成功 | 19,473 |
| 解析失败 | 13（疑似空/异常文件） |
| **不同表种类（按表名）** | **91** |
| **字段定义总数** | **561** |
| **数据行总数** | **503,658** |

---

## 3. 关键性质：每种表的字段集完全稳定

对每种表的**所有实例**比较字段名序列：

> **91 种表，全部 `字段集变体 = 1`。**

即：`en_base` 在 3,180 个不同位置出现，字段永远是那 73 个、顺序也相同。
这说明表结构是**编译期固定**的，不随 mission / 语言变化。

---

## 4. 按实例数量分组（＝作用域层级）

实例数直接揭示了表的业务层级：

### A 组：per-mission × 语言（≈530 × 6）—— 3 种

| 表名 | 实例 | 字段数 | 总行数 | 构成 |
|---|---|---|---|---|
| `Event` | **4,140** | 1 | 29,544 | 纯文本 |
| `en_base` | **3,180** | **73** | 8,196 | 文本 4 / 数值 69（含 13 个数组） |
| `en_trig_group` | 3,180 | 13 | 31,074 | 文本 2 / 数值 11 |

> `en_base` 是**属性最丰富的核心表**（73 个字段），描述怪物全部基础数值。

### B 组：大范围分裂（≈136 × 6）—— 2 种

| 表名 | 实例 | 字段数 | 总行数 |
|---|---|---|---|
| `anagura_progress` | 816 | 1 | **96,864**（行数最多） |
| `base_obj_name` | 816 | 4 | 66,096 |

### C 组：per-mission（≈530）—— 13 种

| 表名 | 实例 | 字段数 | 总行数 | 用途（按命名推断） |
|---|---|---|---|---|
| `caption_text` | 738 | 1 | 13,128 | 字幕文本 |
| `npc_hub` | 541 | 1 | 3,593 | NPC 集散 |
| `dig` | 530 | 5 | 2,454 | 挖掘 |
| `en_atk` | 530 | 11 | 16,687 | 怪物攻击 |
| `en_def` | 530 | 5 | 5,916 | 怪物防御 |
| `en_group` | 530 | 3 | 1,366 | 怪物群组 |
| `en_hit_atk` | 530 | 3 | 13,239 | 命中攻击判定 |
| `en_hit_def` | 530 | 3 | 5,902 | 命中防御判定 |
| `en_mat` | 530 | 3 | 4,535 | 掉落 |
| `en_oracle` | 530 | 3 | 3,618 | 神谕/子弹 |
| `virtual_motion` | 530 | 4 | **79,669** | 动作数据（行数第 3） |
| `enemy_entry_table` | 530 | 9 | 78 | 登场配置（行数极少） |
| `quest_flow` | 529 | 20 | 1,461 | 任务流程 |

> **这 13 种就是"一个 mission 的完整配置集"**：
> 怪物（base/atk/def/mat/oracle/hit_atk/hit_def/group/trig_group/entry）
> + 任务流程 + 动作 + 挖掘 + NPC。

### E 组：全局表 × 6 语言 —— 32 种

全部是 `实例 = 6`（6 种语言各一份）。按用途再分：

**文本类（纯文本，字段 1~2 个）**

| 表名 | 字段 | 行数 |
|---|---|---|
| `game_text` | 1 | 4,326 |
| `action_text` | 1 | 1,362 |
| `oracle_text` | 1 | 1,116 |
| `lsd_str` | 1 | 882 |
| `oracle_cell_name` | 1 | 798 |
| `infra_lobby_text` | 1 | 594 |
| `common_text` | 2 | 546 |
| `tutorial_text` | 1 | 486 |
| `network_text` | 1 | 150 |
| `avatar_text` | 1 | 150 |
| `lobby_text` | 1 | 180 |
| `result_text` | 1 | 162 |
| `text` | 1 | 186 |
| `base_text` | 1 | 2,070 |
| `tutorial_text_PS4` | 1 | 42 |

**数据类（字段较多）**

| 表名 | 字段 | 行数 | 备注 |
|---|---|---|---|
| `showpiece` | 11 | **86,562** | 行数第 2 |
| `paskill_composition` | **22** | 312 | 技能合成（字段第 4 多） |
| `karma` | **14** | 378 | 业力（字段第 6） |
| `npc_class` | 11 | 228 | NPC 类别 |
| `paskill` | 11 | 312 | 技能 |
| `norn_topic` | 7 | 3,846 | |
| `bb_chip` | 6 | 270 | 子弹芯片 |
| `pc_caption` | 6 | 1,968 | |
| `oracle_cell_property_connect` | 5 | 78 | |
| `npc` | 4 | 228 | |
| `en_fam` | 3 | 606 | 怪物家族 |
| `mission_bgm` | 3 | 228 | 任务 BGM |
| `eq_label_main_str` | 2 | 3,924 | 装备标签 |
| `eq_label_sub_str` | 2 | 624 | |
| `enemy_link_skill` | 2 | 132 | |
| `src_icon_pc` | 2 | 1,350 | |
| `chrentry` | 2 | 894 | |

### F 组：全局单表（实例 = 1，无语言副本）—— 41 种

**装备/道具系统**

| 表名 | 字段 | 行数 |
|---|---|---|
| `article_composition` | 11 | 1,277 |
| `equipment_composition` | 9 | 921 |
| `article_shop` | 4 | 33 |
| `equipment_shop` | 5 | 80 |
| `bullet_shop` | 5 | 210 |
| `hair_style` | 4 | 43 |
| `avatar_material` | 5 | 783 |
| `article_ext` | 2 | 5 |
| `article_convert` | 1 | 0 |
| `eq_label_main_cond` | 7 | 326 |

**剧情/进度**

| 表名 | 字段 | 行数 |
|---|---|---|
| `sub_progress` | 7 | 220 |
| `sub_progress_episode_type` | 4 | 20 |
| `sub_progress_episode_type_a` | **23** | 19 |
| `sub_progress_episode_type_b` | 9 | 1 |
| `story_main_flag` | 1 | 20 |
| `story_sub_flag` | 2 | 25 |
| `episode_enable_list` | 2 | 1 |
| `episode_text` | 1 | 90 |
| `import_text` | 1 | 39 |
| `gift_text` | 1 | 33 |

**血怒（Blood Rage）系统**

| 表名 | 字段 | 行数 |
|---|---|---|
| `bloodrage_pledge` | 11 | 84 |
| `bloodrage_efficacy` | 4 | 14 |
| `bloodrage_enemy` | 5 | 93 |
| `bloodrage_rare_pledge` | 5 | 17 |
| `bloodrage_difficulty_rate` | 1 | 15 |
| `bloodrage_text` | 1 | 47 |

**技能/NPC 调优**

| 表名 | 字段 | 行数 |
|---|---|---|
| `skill` | 4 | 234 |
| `npc_tuning` | **14** | 102 |
| `pa_learn_condition` | 5 | 13 |
| `pa_learn_condition_group` | 3 | 16 |
| `lsd` | 9 | 194 |
| `omiyage` | 4 | 55 |
| `npc_call_npc` | 5 | 21 |
| `npc_call_text` | 1 | 5 |
| `enemy_genus` | 1 | 10 |
| `mission_dlc_ext` | 2 | 19 |

**示例表（开发遗留）**

| 表名 | 字段 | 行数 |
|---|---|---|
| `Sample2` | 5 | 16 |
| `Sample_Varray` | 3 | 4 |
| `Sample_VarrayText` | 2 | 7 |
| `Sample_DigTable` | 5 | 56 |

**异常**

| 表名 | 字段 | 行数 | 说明 |
|---|---|---|---|
| `.tr2` | **75** | 80 | 表名为空，字段 75 个全是 UINT8。疑似测试/占位文件 |

---

## 5. 属性数量排行（字段最多的表）

| 字段数 | 表名 | 实例 | 行数 |
|---|---|---|---|
| **75** | `.tr2`（表名异常） | 1 | 80 |
| **73** | `en_base` | 3,180 | 8,196 |
| **23** | `sub_progress_episode_type_a` | 1 | 19 |
| **22** | `paskill_composition` | 6 | 312 |
| **20** | `quest_flow` | 529 | 1,461 |
| **14** | `karma` | 6 | 378 |
| **14** | `npc_tuning` | 1 | 102 |
| **13** | `en_trig_group` | 3,180 | 31,074 |
| **11** | `en_atk` | 530 | 16,687 |
| **11** | `showpiece` | 6 | 86,562 |
| **11** | `npc_class` | 6 | 228 |
| **11** | `paskill` | 6 | 312 |
| **11** | `article_composition` | 1 | 1,277 |
| **11** | `bloodrage_pledge` | 1 | 84 |

### 5.1 `en_base` 的 73 个字段（属性最完整的表）

仅列名字，语义未解释。`[arr=N]` 表示数组字段。

```
 1. en_base_name                                     ASCII
 2. en_base_res_name                                 ASCII
 3. en_base_display_name                             UTF-8
 4. en_base_entry_limit                              UINT8
 5. en_base_hp                                       UINT32  [arr=4]
 6. en_base_family_id                                UINT8
 7. en_base_genus_id                                 UINT8
 8. en_base_sight_area                               FLOAT32
 9. en_base_hearing_area                             FLOAT32
10. en_base_entry_y_offset                           FLOAT32
11. en_base_int_param_array                          INT32   [arr=8]
12. en_base_float_param_array                        FLOAT32 [arr=8]
13. en_base_hate_array                               FLOAT32 [arr=29]
14. en_base_down_array                               UINT16
15. en_base_sympathy_bind_time_array                 UINT16
16. en_base_influence_effect_distance_array          FLOAT32
17. en_base_badstatus_poison_value                   UINT16
18. en_base_badstatus_poison_add_value               UINT16
19. en_base_badstatus_poison_time                    UINT16
20. en_base_badstatus_poison_down                    FLOAT32
21. en_base_badstatus_hold_value                     UINT16
22. en_base_badstatus_hold_add_value                 UINT16
23. en_base_badstatus_hold_time                      UINT16
24. en_base_badstatus_vsgod_value                    UINT16
25. en_base_badstatus_vsgod_add_value                UINT16
26. en_base_badstatus_vsgod_time                     UINT16
27. en_base_badstatus_defense_worse_value            UINT16
28. en_base_badstatus_defense_worse_add_value        UINT16
29. en_base_badstatus_defense_worse_time             UINT16
30. en_base_badstatus_attack_better_value            UINT16
31. en_base_badstatus_attack_better_add_value        UINT16
32. en_base_badstatus_attack_better_time             UINT16
33. en_base_badstatus_stun_grenade_dist              FLOAT32
34. en_base_badstatus_stun_grenade_angle             FLOAT32
35. en_base_badstatus_unheared_time                  UINT16
36. en_base_hate_total                               INT32
37. en_base_rage_time                                UINT16
38. en_base_appear_after_wait_time                   UINT16
39. en_base_disappear_wait_time                      UINT16
40. en_base_near_death_threshold                     INT8
41. en_base_bite_stock_threshold                     INT8    [arr=2]
42. en_base_bite_stock_rate                          INT8    [arr=2]
43. en_base_bite_recover_life_percent                INT8    [arr=4]
44. en_base_bite_recover_percent_flicker             INT8    [arr=4]
45. en_base_material_acquirable_count                INT8
46. en_base_angry_attack_scale                       INT16
47. en_base_angry_accumulate_bonus_threshold         INT8
48. en_base_angry_accumulate_bonus_factor            UINT8
49. en_base_bad_condition_factor                     INT16   [arr=10]
50. en_base_append_material_id                       INT16   [arr=5]
51. en_base_append_material_weight                   INT8    [arr=5]
52. en_base_link_skill_type_id_array                 INT8
53. en_base_link_skill_param_array                   FLOAT32 [arr=22]
54. en_base_link_skill_condition_type_array          INT8
55. en_base_intensify_sight_area                     FLOAT32
56. en_base_intensify_hearing_area                   FLOAT32
57. en_base_intensify_rage_time                      UINT16
58. en_base_intensify_angry_accumulate_bonus_factor  FLOAT32
59. en_base_influencer_flag                          UINT8
60. en_base_sympathy_bind_finish_accelerate_offset   UINT16
61. en_base_sight_area_attack_no_target              FLOAT32
62. en_base_sight_area_attack_target                 FLOAT32
63. en_base_intensify_sight_area_attack_no_target    FLOAT32
64. en_base_intensify_sight_area_attack_target       FLOAT32
65. en_base_hearing_area_attack_no_target            FLOAT32
66. en_base_hearing_area_attack_target               FLOAT32
67. en_base_intensify_hearing_area_attack_no_target  FLOAT32
68. en_base_intensify_hearing_area_attack_target     FLOAT32
69. en_base_group_sight                              FLOAT32
70. en_base_assault_stagger_hp                       UINT32  [arr=4]
71. en_base_map_name                                 ASCII
72. en_base_map_marker_type                          UINT8
73. en_base_danger_level                             UINT8
```

**统计**：ASCII/UTF-8 文本 4 个，数值 69 个（其中数组 13 个：
`hp[4]`、`int_param[8]`、`float_param[8]`、`hate[29]`、`bite_stock_threshold[2]`、
`bite_stock_rate[2]`、`bite_recover_life[4]`、`bite_recover_flicker[4]`、
`bad_condition_factor[10]`、`append_material_id[5]`、`append_material_weight[5]`、
`link_skill_param[22]`、`assault_stagger_hp[4]`）。

### 5.2 `quest_flow` 的 20 个字段

```
 1. quest_flow_start_elapse_time                     UINT32
 2. quest_flow_start_condition                       UINT16
 3. quest_flow_start_reaching_quest_ids              UINT8
 4. quest_flow_start_reaching_quest_states           UINT8
 5. quest_flow_climax_elapse_time                    UINT32
 6. quest_flow_climax_condition                      UINT16
 7. quest_flow_climax_enemy_vitality                 UINT8
 8. quest_flow_end_elapse_time                       UINT32
 9. quest_flow_end_condition                         UINT16
10. quest_flow_end_enemy_defeat_number               UINT8
11. quest_flow_end_enemy_defeat_family_id            UINT8
12. quest_flow_enemy_entry_delay                     UINT8
13. quest_flow_enemy_entry_class_id                  UINT8
14. quest_flow_enemy_entry_number                    UINT8
15. quest_flow_enemy_entry_volume                    ASCII
...（共 20 个）
```

> 注意 `quest_flow` 的结构呈现清晰的 **start / climax / end 三段式**
> （开始条件、高潮条件、结束条件），每段各有 elapse_time + condition。

---

## 6. 数据量排行（行数最多的表）

| 行数 | 表名 | 字段 | 说明 |
|---|---|---|---|
| **96,864** | `anagura_progress` | 1 | 进度日志（单字段） |
| **86,562** | `showpiece` | 11 | 展示品/收藏 |
| **79,669** | `virtual_motion` | 4 | 动作关键帧 |
| **66,096** | `base_obj_name` | 4 | 对象名 |
| **31,074** | `en_trig_group` | 13 | 怪物触发组 |
| **29,544** | `Event` | 1 | 事件文本 |
| 16,687 | `en_atk` | 11 | 怪物攻击 |
| 13,239 | `en_hit_atk` | 3 | 命中判定 |
| 13,128 | `caption_text` | 1 | 字幕 |
| 8,196 | `en_base` | 73 | 怪物基础 |

---

## 7. 统计口径说明

- **"字段数"**：该表的 Field 数量（每个 Field 是一列）。
- **"字段构成"**：按类型串粗分 —— `ASCII`/`UTF-8`/`UTF-16LE` 记为"文本"，
  其余（数值类型）记为"数值"；某字段 `arr > 1` 标记为"数组"。
- **"总行数"**：该种表全部实例的行数之和。
- **"字段集变体"**：同种表的多个实例之间，字段名序列的不同版本数。全部为 1 表示完全一致。

---

## 8. 尚未做

| 项 | 说明 |
|---|---|
| 561 个字段的**语义** | 按要求暂不解释，只统计 |
| 各字段的类型分布明细 | `kinds.json`（本地中间产物，含每字段 name/type/arr） |
| tr2 表之间的完整引用图 | 部分已做，见 `tr2-id-map.md` |
| 13 个解析失败的 tr2 | 未逐一定位原因 |

---

## 9. 数据文件

| 文件 | 内容 |
|---|---|
| `kinds.json`（本地） | 91 种表的完整定义：实例数、字段数、行数、每个字段的 name/type/arr |
