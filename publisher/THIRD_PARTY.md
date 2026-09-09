# 第三方组件

绿色版包含 Python 运行时，以及 Beautiful Soup、Pillow、tinycss2、soupsieve、webencodings、typing_extensions 和 Tcl/Tk。许可证副本见 `licenses`；对应项目源码可从各自官网或 PyPI 项目页面取得。

编辑界面使用浏览器原生编辑能力，没有需要在线授权的编辑器。窗口使用电脑现有的浏览器，Git 不随工具分发。

离线 AMP 校验器来自 AMP Project 官方：

- 下载地址：<https://cdn.ampproject.org/v0/validator_wasm.js>
- 源码：<https://github.com/ampproject/amphtml/tree/main/validator>
- 许可证：Apache License 2.0，Copyright The AMP HTML Authors。
- 本项目保留校验器原始代码，不修改其规则。分发副本下载于 2026-09-09。

可执行文件通过 PyInstaller 构建，使用其允许分发应用程序的 Bootloader Exception；详见 <https://pyinstaller.org/en/stable/license.html>。开发依赖 PyInstaller 本身不作为编辑功能组件运行。
