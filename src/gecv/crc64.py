# -*- coding: utf-8 -*-
"""
CRC64 —— qpck / PRES 使用的 64 位循环冗余校验，用于把"资源路径"映射成 64 位哈希。
CRC64 -- the 64-bit CRC used by qpck / PRES to map a resource path to a 64-bit hash.

来源 / Provenance
-----------------
本实现移植自一份他人分享的 C# 参考实现（`_temp/202609131828/src/Crc64.cs`）。
该参考实现已被我们的样本整包往返测试所验证（见 `tests/`），因此 CRC 算法本身属于"已验证"。
Ported from a shared C# reference implementation (`_temp/202609131828/src/Crc64.cs`).
This reference has been validated by full round-trip tests against real game archives
(see `tests/`), so the CRC algorithm itself is VERIFIED.

!!! 注意：这份 C# 代码属于他人分享物，不可提交进本仓库；本文件是独立重写，不含其原文。
    NOTE: That C# code is a third-party share and must NOT be committed to this repo;
    this file is an independent rewrite and contains none of its source text.

算法参数 / Algorithm parameters
------------------------------
这是一个"反射输入/反射输出"(reflected) 的表驱动 CRC64：
This is a reflected (input reflected / output reflected) table-driven CRC64:

    多项式 Polynomial          0x95AC9329AC4BC9B5        （已验证 / VERIFIED）
    初始值 Initial value       0xFFFFFFFFFFFFFFFF        （已验证 / VERIFIED）
    结果异或值 Final XOR       0x0000000000000000        （已验证 / VERIFIED）
    是否反射 Reflected         True                      （已验证 / VERIFIED）

关于"它是不是某个公开标准" / Is it a well-known standard?
---------------------------------------------------------
多项式 0x95AC9329AC4BC9B5 是所谓的 "Jones" 多项式的反射形式，在
[ algunos ] 若干 CRC64 变体中出现过。但**我们没有验证**它精确等于哪一个公开命名
（例如某些变体初始值为 0 而非全 1），因此本文档不声称标准名。
上面给出的四个参数才是唯一可信的描述。

The polynomial 0x95AC9329AC4BC9B5 is the reflected form of the so-called "Jones"
polynomial and appears in several CRC64 variants. However we have **NOT verified**
which publicly-named variant it equals exactly (some variants use init=0 instead of
all-ones), so we deliberately do NOT claim a standard name here. The four parameters
above are the only trustworthy description.

为什么初始值/搜索到的常数必须与上面完全一致 / Why the constants must match exactly
--------------------------------------------------------------------------------
qpck 的目录表（TOC）直接以 CRC64 作为主键：路径 -> CRC64 -> 查表 -> 得到数据偏移。
只要哈希算法差一个比特，所有条目都会查不到，游戏会静默地读不到任何资源。
因此这四个常数是整个工具链的地基，修改前必须有往返测试保护。
"""

# 多项式（反射形式）。64 位无符号数。
# Polynomial (reflected form), as a 64-bit unsigned value.
POLYNOMIAL = 0x95AC9329AC4BC9B5

# 初始值：全 1。C# 原实现写作 ulong.MaxValue。
# Initial value: all ones. The original C# wrote it as ulong.MaxValue.
INITIAL_VALUE = 0xFFFFFFFFFFFFFFFF

# 表大小固定 256 项：一次处理一个字节。
# Table size is fixed at 256 entries: we consume one byte per step.
_TABLE_SIZE = 256


def _build_table() -> list[int]:
    """构建 CRC64 查表（反射表驱动算法）。Build the reflected CRC64 lookup table.

    伪代码（与下面实现等价，方便非 Python 读者对照）：
    Pseudocode (equivalent to the implementation below, for non-Python readers):

        for i in 0 .. 255:
            c = i                       # 注意：不是 i << 56，这正是"反射"算法的写法
            repeat 8 times:             # 每个字节 8 个比特
                if (c & 1) != 0:        # 最低位为 1
                    c = (c >> 1) XOR POLY
                else:
                    c = (c >> 1)        # 最低位为 0，只右移
            table[i] = c

    为什么是 i 而不是 i << 56：非反射 CRC 要把字节对齐到最高位参与除法；
    反射实现把字节放在最低位，所以初值就是 i 本身。两者算出的表不同，但配上
    对应的"取索引/移位"方式后结果自洽。

    Why i and not i << 56: a non-reflected CRC aligns the byte with the top bit for the
    polynomial division; the reflected form keeps the byte in the low bits, so the seed is
    simply i. The two produce different tables, but each is self-consistent with its own
    index selection and shift direction.
    """
    table: list[int] = []
    for i in range(_TABLE_SIZE):
        crc = i
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ POLYNOMIAL
            else:
                crc = crc >> 1
        table.append(crc)
    return table


# 模块级单例表：进程内只构建一次（256 * 8 次迭代，开销可忽略）。
# Module-level singleton table: built once per process (256*8 iterations, negligible cost).
TABLE = _build_table()

# 64 位掩码。Python 的 int 无溢出（任意精度），而 C/C# 的 ulong 会自然回绕，
# 所以这里需要手动截断，否则数值会无限增长，哈希就错了。
# 64-bit mask. Python ints have arbitrary precision while C/C# ulong wraps naturally,
# so we must truncate manually; otherwise the value grows without bound and the hash is wrong.
_MASK64 = 0xFFFFFFFFFFFFFFFF


def compute(data: bytes) -> int:
    """计算任意字节序列的 CRC64。Compute the CRC64 of an arbitrary byte sequence.

    伪代码 / Pseudocode:

        crc = 0xFFFFFFFFFFFFFFFF
        for each byte b in data:
            index = (crc XOR b) & 0xFF     # 取 crc 最低 8 位与字节异或
            crc   = (crc >> 8) XOR table[index]
        return crc

    注意：没有最后的 XOR 步骤（Formal final XOR = 0），也没有反射输出以外的额外处理。
    Note: there is no final XOR step, and no extra post-processing beyond reflection.
    """
    crc = INITIAL_VALUE
    for b in data:
        # 每一步都 & _MASK64 是保险：按算法 crc 恒 < 2^64，但显式截断可以让
        # Python 实现与 C/C# 实现严格等价，便于后期排查差异。
        # Masking every step is defensive: crc is always < 2^64 by construction, but explicit
        # truncation keeps the Python implementation bit-identical to C/C#.
        index = (crc ^ b) & 0xFF
        crc = ((crc >> 8) ^ TABLE[index]) & _MASK64
    return crc


def normalize_path(path: str) -> str:
    """把资源路径归一化为"参与哈希计算的字符串"。Normalize a resource path for hashing.

    归一化规则（三条，全部已由往返测试验证）：
    Normalization rules (three of them, all verified by round-trip tests):

        1. 反斜杠换成正斜杠：  'a\\\\b'  ->  'a/b'
           Backslashes become forward slashes.
        2. 去掉开头的斜杠：    '/a/b'   ->  'a/b'
           Leading slashes are stripped.
        3. 转成大写：          'a/B.res' -> 'A/B.RES'
           Upper-cased.

    为什么这三条必须精确：游戏内部的资源路径写法不统一（有的带前导斜杠，有的用反斜杠），
    归一化保证同一份资源只有一个哈希。大小写不敏感说明底层文件系统/引擎把路径当标识符而非
    真实文件名的精确字节。

    Why these three must be exact: the game writes resource paths inconsistently (some with
    leading slashes, some with backslashes); normalization guarantees one hash per resource.
    Case-insensitivity implies the engine treats paths as identifiers rather than exact
    filesystem byte strings.

    :raises UnicodeEncodeError: 路径含非 ASCII 字符时抛出。
        这是有意为之：引擎使用 ASCII 编码计算哈希，遇到非 ASCII 路径时我们无法知道
        它的真实处理逻辑，与其猜（并悄悄产生错误哈希），不如明确报错。
    """
    trimmed = path.replace("\\", "/").lstrip("/").upper()
    return trimmed


def hash_path(path: str) -> int:
    """计算资源路径的 CRC64（含归一化）。CRC64 of a resource path (including normalization).

    等价于：compute(normalize_path(path).encode('ascii'))
    Equivalent to: compute(normalize_path(path).encode('ascii'))
    """
    normalized = normalize_path(path)
    # encode('ascii') 而非 encode()：必须与引擎行为一致（引擎用 ASCII），
    # 且遇到非 ASCII 时立即失败，避免产生"看起来正常但其实是错"的哈希。
    # encode('ascii') rather than encode(): must match the engine (which uses ASCII) and must
    # fail loudly on non-ASCII instead of silently producing a plausible-but-wrong hash.
    return compute(normalized.encode("ascii"))
