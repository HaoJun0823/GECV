# -*- coding: utf-8 -*-
"""
GECV —— God Eater (PC) 逆向工程与 Mod 工具链的 Python 包。
GECV —— God Eater (PC) reverse-engineering and mod-tooling toolkit (Python).

设计约定 / Design conventions
----------------------------
1. 二进制解析一律"手写显式解析"：用 struct.unpack 逐个字段读，并在每个关键位置做显式校验。
   不使用 construct / kaitai 这类声明式库。
   原因：逆向场景下"到底错在第几个字节"是最重要的信息，声明式库的错误信息（如 StreamError）
   无法定位到偏移，会掩盖格式误解。
   Binary parsing is done by explicit hand-written struct.unpack calls with per-field validation.
   We deliberately avoid declarative libraries (construct/kaitai): in reverse engineering,
   knowing *which byte* failed is the most valuable piece of information, while those libraries
   only report opaque errors that hide real format misunderstandings.

2. 注释与文档双语（中文在前，英文在后）。
   Comments and docs are bilingual (Chinese first, English second).

3. 每个格式都必须同时提供 unpack（解包）与 pack（打包）。
   Every format must provide both unpack and pack.

4. 事实必须区分"已验证"与"未验证"，禁止把推测写成定论。
   Facts must be labelled VERIFIED vs UNVERIFIED; never present guesses as facts.
"""

__version__ = "0.1.0"
