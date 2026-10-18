# 格式文档索引

> 按"读者想知道什么"分组，而不是按文件名排。

## 先读这一篇

| 文档 | 回答什么问题 |
|---|---|
| [`pres-illustrated.md`](formats/pres-illustrated.md) | **看不懂字段？这里有两个完整文件的逐字节解读（tbl / rtbl）** |
| [`design-rationale.md`](formats/design-rationale.md) | **rtbl / tbl / kst1 / tr2 各自是干什么的？为什么这样设计？为什么不合并？** |
| [`packaging.md`](packaging.md) | **哪些包是玩家服装？哪些是关卡场景？武器/道具/任务在哪一层？** |

`pres-illustrated.md` 适合"想建立直觉"，`design-rationale.md` 适合"理解设计意图"。
读完这两篇能建立全局观：**PRES/tbl/rtbl 管"资源在哪"，kst1/tr2 管"数据是什么"**。

## 资源层（东西在哪）

| 文档 | 内容 |
|---|---|
| [`qpck.md`](formats/qpck.md) | 归档容器：`CRC64(路径) → 字节块`，内容寻址、无文件名 |
| [`pres.md`](formats/pres.md) | 资源树：8 组 × 语言分组、3 种条目类型、pool 布局、**tbl/rtbl 结构** |
| [`prx.md`](formats/prx.md) | **PC 版为何没有 `.prx` 文件**：它只是模块名声明，代码静态链接在 exe 内（含 hook 影响） |

## 数据层（数据是什么）

| 文档 | 内容 |
|---|---|
| [`kst1.md`](formats/kst1.md) | 键值数据库：u32 key → 定长记录，两级位图索引 |
| [`tr2.md`](formats/tr2.md) | 表格数据总述（较早期，部分结论已被下列文档修正） |
| [`tr2-primary-key.md`](formats/tr2-primary-key.md) | **记录主键（ID 索引）—— 已定论，全量 96% 命中** |
| [`tr2-reading.md`](formats/tr2-reading.md) | **tr2 列式读取的正确方法**（已实测） |
| [`tr2-kinds.md`](formats/tr2-kinds.md) | tr2 表类型分类 |
| [`tr2-id-map.md`](formats/tr2-id-map.md) | 表间 ID 映射的进展 |
| [`tr2_ida_confirmed.md`](formats/tr2_ida_confirmed.md) | tr2 的 IDA 证据 |
| [`tr2_re_evidence.md`](formats/tr2_re_evidence.md) | tr2 逆向过程记录 |

> ⚠️ **tr2 文档的阅读顺序**：`tr2-reading.md` 修正了 `tr2_ida_confirmed.md` 的若干结论
> （详见其 §1）。以 `tr2-reading.md` 为准。

## 拓扑

| 文档 | 内容 |
|---|---|
| [`topology.md`](topology.md) | 资源拓扑总述 |
| [`topology-graph.md`](topology-graph.md) | 引用模型与三层拓扑图方案 |
| [`reference-chain.md`](reference-chain.md) | 引用链的完整追踪 |
| [`packaging.md`](packaging.md) | **res 包谁套谁：服装 / 场景 / 武器 / 道具 / 任务各自的落点** |

---

## 当前最关键的未解项

| 项 | 阻塞什么 | 详见 |
|---|---|---|
| ~~tr2 的记录主键在哪~~ | ✅ **已解决**：Field 表之后的 ID 排序数组 | `tr2-primary-key.md` |
| ~~PC 上 `prx` 是否被引擎加载~~ | ✅ **已定论**：不加载外部文件，模块代码静态链接在 exe | `prx.md` |
| tbl 的 g4/g6 宿主包装函数 | 完整解释全部 tbl | `pres.md` §8.5.6 |
| 各 tbl 固定形状族的字段语义 | 改表 | `pres.md` §8.5.2 |
| 表间引用关系的严格验证 | 业务拓扑图 | 待做（主键已可支撑） |

## 四个格式的状态总表

| 格式 | 读取 | 写入 | 语义 |
|---|---|---|---|
| qpck | ✅ 字节级往返 | ✅ | ✅ |
| PRES | ✅ 8,586 棵树全解 | ❌ | ✅ 结构全解 |
| tbl | ✅ 载荷 + 宿主机制 | — | ⚠️ 字段含义未知 |
| rtbl | ✅ 189,794 槽全验 | — | ⚠️ 槽序号语义未知 |
| kst1 | ✅ 18 文件全验 | — | ✅ |
| tr2 | ✅ 列式读取已通 | — | ✅ **主键已定位**（`tr2-primary-key.md`） |
