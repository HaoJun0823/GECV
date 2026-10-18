# res 包的打包机制：谁套谁

> **回答的问题**：玩家服装、关卡场景、武器、道具、任务各自落在哪一层？
> 谁引用谁？为什么"套娃"这个直觉是错的、但又不完全错？
>
> **证据等级**：规模性结论来自两作全量数据普查（GER 91,179 / GE2RB 151,369 条命名资源；
> 11,005 / 19,806 个可达 PRES 节点）。引擎机制来自 `GER.exe` 反汇编。
> 未验证项在 §7 明确列出。

---

## 1. 先纠正前提：不是树，是 DAG

「system.res 是唯一入口，其余包层层嵌套」这个直觉，**实测不成立**。

| 指标 | GER | GE2RB |
|---|---:|---:|
| 可达 PRES 节点 | 11,005 | 19,806 |
| 引用边 | 208,954 | 297,266 |
| fan-in > 1 的节点 | 10,459（**95%**） | — |
| 深度 | 0–6 | — |

最极端的一张贴图被引用 **3,264 次**（`effect/Enemy/Share/PartDestruct/.../PartDestruct_02.gnf.blz`）。

> **正确的模型**：不是"大包套小包"的树，而是**每个包声明自己要什么的依赖清单（DAG）**。
> "套娃感"来自 PRES 引用子 PRES，但那只是**路径字符串的声明**，不是所有权包含。

**这对 mod 实践有直接后果**：改一张共享贴图，会同时影响上千个包。
反过来，覆盖资源不必打包 qpck —— 放同名真实文件同样生效（见 `topology.md` §6.1）。

---

## 2. 三层结构与各自的职责

```
qpck 归档        CRC64(路径) → 字节块。平铺、无目录、无语义。挂在文件系统前的缓存层。
   │
PRES 资源树      「我要哪些东西」的清单。8 dataset × N country × 32 字节 entry。
   │
叶子格式         tr2(表) / gnf(贴图) / ixo(模型) / is14(音频) / ssq / gmvl / obc …
```

**关键分界**：PRES 只管"东西在哪"，tr2 只管"数据是什么"。
两层用**不同的引用机制**，必须分开建模：

| 层 | 引用方式 | 能否从数据侧重建 |
|---|---|---|
| PRES → PRES | 路径字符串 → CRC64 | ✅ 已重建 20 万条边 |
| tr2 → tr2 | 整数 ID | ✅ 能，但需逐表建立命名空间 |
| 运行时 URID | 32 位 label/sect/index | ❌ **不落盘**（随机基线已证否，见 `reference-chain.md` §6） |

---

## 3. 模块级：谁套谁

把 PRES 按目录聚合成模块，统计跨模块引用边（`python -m tools.restopo modules`）。

### 3.1 GER 模块表

| 模块 | PRES 数 | 出边 | 入边 | 装的什么 |
|---|---:|---:|---:|---|
| `g999_Base` | 4,134 | 4,062 | **8,123** | 基础库：脚本 3,577 / NPC 模型 269 / UI 布局 48 |
| `event` | 2,040 | **14,269** | 3,889 | **过场动画**：Demo 模型、教学 UI，每个 demo 一套 |
| `field` | 899 | 1,062 | 6,245 | **关卡场景**：10 个场地 ×（Model/Light/After/Before） |
| `player` | 646 | 674 | 952 | **玩家**：服装 / 武器 / 捕食动作 |
| `effect` | 548 | 11 | 3,864 | 特效，被所有人引用 |
| `god_g000_Mission` | 529 | 2,040 | 529 | **任务调度层**：529 个任务，一任务一个 PRES |
| `npc` | 451 | 54 | 3,223 | NPC 模型（每人约 11 个部件 PRES） |
| `menu` | 437 | 12 | 497 | UI：任务委托书模型 403 |
| `enemy` | 351 | **0** | 2,050 | 怪物模型 |
| `mission` | 321 | 4,690 | 1,340 | 每关专属怪物模型 |

### 3.2 最强的五条依赖边

| 边数 | 父 → 子 | 含义 |
|---:|---|---|
| 5,154 | `event` → `field` | 过场动画要用场地 |
| 3,337 | `event` → `g999_Base` | 过场动画要用基础库 |
| 2,787 | `mission` → `effect` | 任务要用特效 |
| 2,685 | `event` → `npc` | 过场动画要 NPC |
| 1,903 | `mission` → `enemy` | 任务要怪物 |

### 3.3 一个干净的判据

> **出边为 0 的模块是纯资源，出边大的模块是调度者。**

`enemy` 出边为 0 —— 怪物从不引用任何东西，只被引用。
`event` 出边 14,269 —— 过场动画是最大的消费者。
这条判据可以直接用来给未知模块定性。

---

## 4. 五类业务的落点

### 4.1 玩家服装 —— 三层嵌套，**唯一真正的"套娃"**

全部数据里嵌套最规整的一块，也是唯一能用"套娃"准确描述的地方：

```
god_menu.res                                       ← 第 1 层：菜单包（packageId 0x23E2）
  └─ god_menu_ChrTopMale_tbl.rtbl                  ← 第 2 层：引用表，1408 个槽
       └─ "player/Male/Body/0003/color1/Top.res"   ← 第 3 层：部件 PRES
            └─ ixo / gnf                           ← 第 4 层：真正的模型贴图
```

实测的 6 个 rtbl（`work/patched/bin/resconv_pc/src/god_menu/`）：

| rtbl 文件 | 大小 | 指向 |
|---|---:|---|
| `god_menu_ChrHeadMale_tbl.rtbl` | 6.05 MB | `player/Male/Hair/{0032}/{0000}/Head_XXXX_XXXXcN.res` |
| `god_menu_ChrTopMale_tbl.rtbl` | 360 KB | `player/Male/Body/{0003}/color{N}/Top.res` |
| `god_menu_ChrBottomMale_tbl.rtbl` | 360 KB | `player/Male/Body/{0003}/color{N}/Bottom.res` |
| 三个 `_reftbl` 后缀 + Female 版本 | 360 KB | 同上的另一种引用形式 |

服装资源量（GER）：**Male 5,582 / Female 5,577**，格式压倒性地是 `.res`
（5,452 / 5,445）—— 说明**每个服装部件自己又是一个 PRES**，这是四层嵌套的来源。

> 命名规律 `Hair/0009/0004/Head_0009_0004c1.res`：
> `0009` = 发型 ID，`0004` = 变体，`c1` = 颜色 1。
> 它与 tr2 表 `hair_style` 的 `hair_style_resource_id[2]` 形式上对应 ——
> **但这条换算尚未验证**，只是命名规律对得上（见 §7）。

### 4.2 武器 —— 部件组合，不是整包

```
player/Weapon/Arms_Base/Arms_Base_{Sword,Scythe,Pole}.res   ← 武器类型的骨架
player/Weapon/Part/Blade/Buster/{0002}/Color1/Blade.res     ← 刀刃部件
player/Weapon/Part/Blade/Buster/Base/{1009}/Base.res        ← 刀柄部件
```

GER 武器 PRES 只有 **69 个**，但资源 **2,136 条**（res 1,800 + gnf 206 + ixo 90）。
结构是 `Arms_Base(类型骨架) + Part/Blade/…/{型号}/{颜色}/(部件)` 的正交组合。

数据侧的证明在 `npc_tuning.tr2`：

```c
npc_tuning_blade_id         UINT16   ← 刀刃
npc_tuning_nozzle_id        UINT16   ← 枪口
npc_tuning_armor_id         UINT16   ← 装甲
npc_tuning_cloth_id         UINT16   ← 服装
npc_tuning_voice_id         UINT16
```

> **一件武器 = 4 个整数 ID 的组合，不是一条路径。**
> 这就是"武器怎么调用"难回答的根因：中间层是 ID，不是路径，
> 因此不能像 PRES 那样顺着字符串走下来。

### 4.3 关卡场景 —— 一个场地 4 个 PRES

```
data/GameData/field/{编号}_{名字}/
   ├─ Field.res      ← 主体（001_Step 的 Field.res 有 76 个直接子项）
   ├─ Before.res     ← 破坏前
   ├─ After.res      ← 破坏后
   ├─ Model/         ← 几何 + 贴图（.ixo / .gnf）
   └─ Light/         ← 光照（7 个 .ixo）
```

GER 10 个场地（field PRES 899），GE2RB 大幅扩张到 3,884。
`Field.res` 同时引用 `Before/After` 与一批 `.gnf.blz` —— **场地是自包含的**，不套别人。

### 4.4 道具 —— 在表里，不在 PRES 里

**道具几乎没有专属美术资源**，它是纯数据行，位于 `g999_Base/db/article/Tr2/`：

| 表 | 行数 | 内容 |
|---|---:|---|
| `article_composition` | 1,277 | 道具合成配方（输入 2 → 产出 1） |
| `equipment_composition` | 921 | 装备合成配方（输入 5 → 产出 1） |
| `article_shop` | 33 | 商店售卖 |
| `equipment_shop` | 80 | 装备商店 |
| `article_ext` | 5 | 扩展属性 |

模型贴图复用 `player/Weapon/**`。**"道具包"这个概念在本作不成立** —— 道具是数据库记录。

### 4.5 任务 —— 双层：调度 PRES + 每关 8 张表

```
src/god_g000_Mission/{编号}_{名字}.res        ← 第 1 层：任务调度（GER 529 个）
   └─ 引用该关的：教程 UI、特效、怪物模型

data/GameData/mission/{关卡}/db/enemy/Tr2/*.tr2  ← 第 2 层：每关 8 张表
   ├─ en_base          怪物基础（73 字段）
   ├─ en_atk / en_def  攻击 / 防御
   ├─ en_mat           掉落素材（→ article）
   ├─ en_oracle        神机子弹（→ bullet）
   ├─ en_group / en_trig_group
   ├─ quest_flow       任务流程（20 字段：开始 / 高潮 / 结束条件）
   └─ enemy_entry_table / virtual_motion
```

GER 任务域 **7,303 条资源**，其中 tr2 **6,371 条（87%）** ——
任务是**数据驱动**的，美术资源很少。另有 `gmvl` 541 条是关卡几何。

---

## 5. 两作对比：结构一致，规模翻倍

| 域 | GER | GE2RB | 变化 |
|---|---:|---:|---|
| 命名资源总数 | 91,179 | 151,369 | ×1.66 |
| 任务 | 7,303 | 18,255 | ×2.5 |
| 场景 | 2,811 | 11,585 | **×4.1** |
| 特效 | 1,825 | 5,738 | ×3.1 |
| 玩家服装 Male | 5,582 | 4,181 | ↓（合并了） |
| 武器 | 2,136 | 1,940 | ≈ |
| tr2 表 | 19,486 | 39,632 | ×2.0 |

**结构完全一致，GE2RB 主要是内容量翻倍**（场景 ×4 最显著，符合"新增大量场地"）。
这与"两作 10 个 packageId 完全相同"互相印证：
**这套打包机制是引擎级的固定框架，不随游戏内容变化。**

---

## 6. 引擎侧确认（IDA 证据）

取自 `GER.exe_full.i64`：

| 项 | 地址 | 说明 |
|---|---|---|
| `resReadReferRes` | `0x1DAD9FE` | 引用型条目解析，含**子 res 递归分支**（`sub_1DAA5E0` 判定 + `sub_1DAB7DC` 取路径） |
| 断言 `pDat->Sect == Sect_Refer` | `0x1234534` | 确认 dataset 语义为引用段 |
| 断言 `pDat->PtrType == PtrType_FilePath` | `0x12344b8` | 确认 B 类型条目存的是**文件路径** |
| 断言 `hdrbuf.NumLocale == Locale_Num` | `0x1234590` | 确认 country 层就是语言分组 |

这三条断言把"PRES 的引用段存路径、按语言分组"从数据侧推测升级为**引擎侧确证**。

---

## 7. 未解决 / 明确不确定

按诚实原则列出：

| 项 | 状态 |
|---|---|
| `*_id` → 具体哪张表的映射 | **只有前缀规律**（`en_`→enemy、`art_`→article、`bb_`→bullet），未建立完整映射表 |
| `hair_style_resource_id` → `Hair/0009/0004/` 路径的换算 | **未验证**，仅命名规律对得上 |
| 约 24,400 个入口不可达 PRES 的触发源 | 只知按需加载，不知触发条件 |
| `gmvl`（关卡几何）/ `ssq` / `obc` 格式 | 未解析 |
| 10 个 packageId 包 vs 8 个全局槽 | 推测按需注册，**未运行时验证** |

---

## 8. 复现

`work/` 不入版本库，拓扑图与名字表需你先自行生成；`restopo` 只负责解读。

```bash
# 模块级「谁套谁」
python -m tools.restopo modules --graph GER.v2.graph.json --top 25 --packages

# 业务域普查
python -m tools.restopo domains --names names_ger_full.txt --samples 4
```

两个子命令都是只读分析，不修改输入。
