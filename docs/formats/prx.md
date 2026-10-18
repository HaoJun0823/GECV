# `prx` —— 外部模块声明：PC 版为何没有 `.prx` 文件

> **状态**：已定论（此前在 `pres.md` §8.1 标注为"是否真被加载未验证"，本文给出裁决）
> **样本**：GER 4 个归档（bin_patch 101 / bin 92,090 / conf 5 / data 56,273）
> 　　　　GE2RB 4 个归档（482 / 144,142 / 5 / 110,013），两个 `*.exe_full.i64`

---

## 0. 一句话结论

**PC 版不存在 `.prx` 文件。** `.prx` 只是 PRES 数据集里的一条**模块名声明**
（主机版 PSP/PSV 时代遗留），PC 版把这些模块**静态链接进了 exe**。

对逆向与 mod 的直接意义：

| 原先的担忧 | 实际情况 |
|---|---|
| 游戏逻辑在动态加载的 `.prx` 里，hook 要等模块加载、基址不固定 | ❌ 不成立。逻辑**编译在 exe 里**，基址固定 |
| 需先解开 `.prx` 打包格式才能看到代码 | ❌ 不需要，直接逆向 exe |
| DLL hook 方案复杂度高 | ✅ 回落为常规 32 位进程 inline hook / detour |

---

## 1. 为什么会有这个疑问

exe 里有 57 个 `/xxx.prx` 字符串（两侧都是，如 `/god_g000_Field.prx`、
`/system.prx`、`/creature_ninetail.prx`），而 `pres.md` §8.1 又记载 PRES 的
dataset 1 全都是 `.prx`（GER 5,337 条 / GE2RB 9,509 条）。看起来像是
"有一堆外部模块要加载"。

但磁盘上**一个 `.prx` 文件都没有**，qpck 里也查不到。这两件事必须被解释清楚。

---

## 2. 证据一：`.prx` 不在任何 qpck 里（实测 ✅）

用本仓库自己的解析器按 CRC64 全量验证。**方法**：对模块名 × 路径前缀做笛卡尔积，
逐个算 `hash_path()` 去 TOC 查：

| 维度 | 取值 |
|---|---|
| 模块名（10 个） | `god_g000_Field` `god_g999_Base` `god_game` `system` `tree` `creature_ninetail` `god_menu` `prot` `boku_menu` `god_m001_Title` |
| 前缀（13 种） | `/` `""` `bin/` `/bin/` `data/` `/data/` `system/` `/system/` `bin/resconv_pc/` `res/` `/res/` `ps4/` `psvita/` |
| 归档（4 个 ×2 游戏） | `bin_patch.qpck` `bin.qpck` `conf.qpck` `data.qpck` |

**结果：130 种变体 × 2 个游戏，命中 0 条。**

对照组（证明方法本身有效）：名字表里**非 `.prx`** 的路径，前 2,000 条命中 **478 条**
（约 24%）。所以"0 命中"不是算错了哈希，是 `.prx` 真的不在归档里。

> 补充：`.prx` 也不在磁盘上——两个游戏安装目录递归扫描 `*.prx`，**0 个文件**。

### 2.1 名字表里的 `.prx` 长什么样

`work/names_ger_full.txt` 有 72 条、`work/names_ge2rb_full.txt` 有 83 条 `.prx`，
形式是**不带前导斜杠**的裸模块名：

```
system.prx
tree.prx
god_g000_Field.prx
creature_ninetail.prx
```

注意与 exe 内字符串 `/system.prx`（**带**前导斜杠）不同。这是归一化差异：
`pres.md` §10.1.2 已指出这类"无目录短名"本就不参与 qpck 寻址。

---

## 3. 证据二：装载器是**查静态表**，不是加载文件（反汇编 ✅）

`pres.md` 指出 `resReadInst`（`0x1DACE8B`）会调 `sub_1DAD501` 装载 prx 模块。
把它拆开看：

```c
// GER.exe sub_1DAD501  (size 0x11b)
sprintf(Buffer, "%s.%s", v7, v5);        // 拼出 "模块名.prx"
if (v1[12] & 2) sub_1B1DEAA("modLoad:%s\n", Buffer);
v8  = sub_1BB584B(v11, Buffer);
v10 = sub_1C21E17(v8, 1);                // → modLoadEx
if (v10 <= 0) { __debugbreak(); }        // 失败即断
a1[1] = v10;
```

**它只是把模块名拼成字符串，然后去查一张表，从不碰文件系统。**

往下追 `modLoadEx` 的链条：

```
sub_1C21E17  →  sub_1C21E37  →  sub_18ABA25
                                  └─ sub_18A9326  查表（字符串比较树/红黑树）
                                     查不到 ⇒ __debugbreak()
```

### 3.1 模块注册表：固定 25 槽（实测 ✅）

`sub_18ABA25` / `sub_1C21CC7` / `sub_1C21F17` 都用同一对边界：

| 符号 | 地址（GER） | 说明 |
|---|---|---|
| `dword_1719A70` | 表基址 | |
| `dword_1719E58` | 表尾 | 尾 − 基 = `0x3E8` = **1000 字节** |
| 步长 | `v2 += 10`（10 个 int = **40 字节**） | ⇒ **25 个槽位** |

两点关键观察：

1. **表的 xref 全在 `.data` 段**，且只有 3 个查询/管理函数在用它
   （`sub_1C21CC7` 查找、`sub_1C21D57` 引用计数、`sub_1C21F17` 登记）。
   **没有任何"从磁盘读入模块后注册"的调用路径。**
2. 表内容在静态映像里是**全零**（`0x1719A70` 起 64 字节读回全 0），
   符合"运行前填充的登记表"，而非"已编译进去的模块数据"。

> ⚠️ 未解项：`sub_1C21F17` 里 `40 * v1 == -24222288` 这个常量（IDA 渲染形态，
> 疑似编译期折叠的表基址表达式），确切含义**未解**。不影响上面的结论。

### 3.2 GE2RB 侧完全同构（实测 ✅）

| 职能 | GER.exe | GE2RB.exe |
|---|---|---|
| prx 装载入口 | `sub_1DAD501` | `sub_1BCC557` |
| 函数体大小 | `0x11b` | `0x11b`（**完全一致**） |
| 结构 | 逐行同构 | 逐行同构 |
| `modLoad:%s` 字符串 | `0x1234d10` | `0x116cf08` |
| `modLoadEx` 字符串 | `0x11e6354` | `0x10f5904` |
| 装载时写入的全局 | `dword_171D320` | `dword_16AEFB0` |

两侧**保留了同一套 PSP/PSV 时代遗留的模块加载器代码**，行为一致。

---

## 4. 证据三：所谓 `.prx` 模块的代码，就在 exe 里（实测 ✅ 决定性）

如果 `god_g000_Field.prx` 真是外部模块，它的源码不该出现在 exe 中。实测：

| 游戏 | `src\god_g000_Field\*` 源码路径与 `god_g000_Field_*` 符号 |
|---|---|
| **GER** | `player_proc_guard.c`、`npc_core.c`、`npc_ctrl.c`、`npc_routing.c`、`npc_purpose.c`、`player_shoot.c`、`player_aragami_bullets.c`、`player_burst.c`、`player_action_common.c`、`player_proc_hang.c`、`player_st.c`、`site_pc.c`、`site_enm.c`、`pause.c`、`god_g000_Field_Player`、`god_g000_Field_StatusPc_Get*`、`god_g000_Field_SiteEnm` … |
| **GE2RB** | `blood_rage.cpp`、`blood_rage_database.cpp`、`blood_rage_manager.cpp`、`blood_rage_network.cpp`、`blood_rage_pledge.cpp`、`blood_rage_rare_pledge_condition.cpp`、`blood_rage_state.cpp`、`blood_rage_tutorial.cpp`、`blood_rage_ui_parts_support.cpp`、`npc_enemy_watcher.cpp`、`mission_manager.cpp`、`quest_object.cpp`、`voice_manager.cpp` … |

**`god_g000_Field` 这个"prx 模块"的代码编译在两个 exe 里。**
`.prx` 是主机版的产物形态；PC 版把这一层合并进了主程序。

---

## 5. 定性：`.prx` 是什么

| 层面 | 结论 | 证据等级 |
|---|---|---|
| `.prx` 是文件吗 | **不是**。qpck 里 0 命中、磁盘上 0 个 | 实测 |
| `.prx` 是什么 | PRES dataset 1 里的**模块名声明**（短名、无目录） | 实测 + `pres.md` §10.1.2 |
| PC 上被"加载"吗 | **不加载外部文件**。装载器只是拿模块名查静态表 | 反汇编 |
| 那模块代码在哪 | **静态链接在 exe 内** | 实测（§4） |
| 为何还留着这套代码 | 跨平台共用源码（`res.c` 保留了主机版分支） | 推测 |

> 这条与 `pres.md` §11 的观察一致：引擎**保留了完整的 3/4/5/6/C/D 类型码逻辑**，
> 但 PC 资产从不触发——`res.c` 是跨平台共用代码。`.prx` 同理。

---

## 6. 对 mod / 移植的直接影响

### 6.1 hook 条件变简单了

| 项 | GER | GE2RB |
|---|---|---|
| 位数 | 32-bit PE (`0x014C`) | 同 |
| `.reloc` 段 | **无**（`characteristics = 0x0123`） | 同 ⇒ **基址固定** |
| `dinput8.dll` → `DirectInput8Create` | `0x247b040` | `0x249f040` |
| `d3d9.dll` → `Direct3DCreate9` | `0x247b01c` | 有 |

两者都导入 `dinput8.dll`，Ultimate ASI Loader 的 dinput8 代理注入**两侧直接可用**。
且无重定位表 ⇒ 可用固定 VA 下钩子。

### 6.2 但"融合两游戏"的实质工作量没变少

以 GER 的 `PredatorArts::Learning::*` → GE2RB 为例：

| | GER.exe | GE2RB.exe |
|---|---|---|
| `src\god\predatorarts_learning_{condition,manager}.cpp` | 有 | **0 命中** |
| `PredatorArts::`（含 `Checker::ApplyLearning`、四类 `Condition::IsAchieved`） | 有 | **0 命中** |
| `PlayerPredatorArts_{CallBladeAttack,CallShoot,AragamiBullets_Commit}` | 有 | **0 命中** |
| `"Predator Style"` / `"Predator Pack 1/2"` UI 文案 | 有 | 有（**仅文案**） |

反过来，GE2RB 的 `BloodRage` 实现层（`blood_rage*.cpp` 共 7 个文件、
`Pledge` 相关符号 973 个）在 GER 里同样 **0 命中**——GER 只有
`Musen::Event::BloodRage` 的事件类，没有实现文件。

**结论**：两侧是**双向各缺**，不是单向残留。移植的实质是在宿主 exe 里
**从零重实现一整个子系统**，而不是"把某个模块拷过去"。

---

## 7. 顺带厘清：两个 exe 的谱系关系

排查过程中顺带确定了几条常被问错的事实：

| 断言 | 裁决 | 依据 |
|---|---|---|
| "GER 比 GE2RB 新" | ⚠️ **仅编译时刻成立，无代际含义** | PE TimeDateStamp：GER `0x58057C38` = 2016-10-18 01:34:48Z；GE2RB `0x5805E49B` = 2016-10-18 09:00:11Z。**同一天相隔 7.5 小时**，同一发布批次 |
| "GER 是在 GE2RB 代码基础上继续开发的" | ❌ **不成立** | 构建树互斥：GER = `c:\jenkins_noav\iskra1_build_2\iskra1\main\src`（ISKRA1 / Jenkins）；GE2RB = `c:\p4_noav\iskra2_build_2\iskra2\main\src`（ISKRA2 / Perforce）。GER 中搜 `iskra2\|p4_noav` **0 命中**；GE2RB 中搜 `iskra1\|jenkins` **0 命中** |
| 两者共享引擎主干 | ✅ 成立 | 段布局一致（`.xcode`/`.xtext`/`.xpdata`/`.srdata`/`.arch`）；`src\god\*.cpp` 共有 23+ 个模块；`Babel::Creature::*`、`Predator Style`、`Layout_*` 导出两侧都有 |

即：**同一引擎上的两条平行分支**，谁也不是谁的祖先。

---

## 8. 复现方法

```powershell
$env:PYTHONPATH = "src"
```

```python
from gecv.qpck import QpckArchive
from gecv.crc64 import hash_path

arc = QpckArchive(r"<游戏目录>\bin.qpck", strict=False)
arc.contains_hash(hash_path("god_g000_Field.prx"))   # ⇒ False（任何前缀变体皆然）
```

IDA 侧：

- `sub_1DAD501`（GER）/ `sub_1BCC557`（GE2RB）——prx 装载入口
- `sub_1C21E37`（GER）——`modLoadEx`，打印 `%s : 0x%08x : %s`
- `dword_1719A70` / `dword_1719E58`（GER）——模块注册表边界

---

## 9. 仍未解决

| 项 | 现状 |
|---|---|
| 模块表的 25 个槽位在运行期被填成什么 | 未验证。需运行时断点 `sub_1C21F17` 观察 |
| `40 * v1 == -24222288` 常量含义 | 未解（疑似编译期折叠的表基址） |
| PC 上模块表是否在某处被真实填充 | 未验证。§4 表明模块代码已静态链接，此问题对 mod 不阻塞 |
| `.prx` 声明条目与 `system.prx` 的对应关系 | 未逐个对照（`pres.md` §8.1 遗留项） |

> 前三项不影响"PC 无 `.prx` 文件、逻辑在 exe 内"这个主结论——该结论由
> §2（实测 0 命中）、§3（反汇编查表）、§4（源码在 exe）三条独立证据支撑。
