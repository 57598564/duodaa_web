# 绿色版内容发布客户端

用户说明见 [USER_GUIDE.md](USER_GUIDE.md)。Windows x64 交付文件由 `build_portable.py` 输出到仓库根目录的 `releases`，不提交二进制或个人配置。

## 开发运行

```sh
python -m pip install -r publisher/requirements.txt
python -m publisher.app
```

程序绑定随机本机端口，使用浏览器应用窗口显示界面。`publisher/data` 存放开发模式的设置与草稿；打包后使用 EXE 同目录的 `data`。

## 打包

```sh
python -m venv .tmp/publisher-build
.tmp/publisher-build/Scripts/python.exe -m pip install pyinstaller -r publisher/requirements.txt
.tmp/publisher-build/Scripts/python.exe publisher/build_portable.py
```

打包不依赖目标机器的 Python 或 Node，也不包含 Git。AMP 校验器已随源码保存在 `web/vendor/amp-validator.js`，在本地 Web Worker 中运行，不依赖外部校验服务。

## 测试

```sh
python -m unittest discover -s publisher/tests -v
```

测试在 `.tmp` 内创建隔离的网站仓库和本地 bare 远程，不连接 GitHub，不修改正式文章。覆盖 AMP 生成、SEO、图片尺寸、近期列表、前后篇导航、草稿路径配置、微信导入解析、发布／编辑、失败恢复、重复推送以及危险链接和 HTML 清理。

## 代码结构

- `app.py`：本机 HTTP 接口、目录选择和应用窗口。
- `web/`：离线可视化编辑界面、拖拽缩放和发布前 AMP 校验。
- `content.py`：正文清理、图片验证与微信导入。微信访问受限时返回可操作的错误，不绕过验证。
- `site.py`：在工具临时目录中生成发布计划，基于可配置的网站根目录更新站点。
- `gitops.py`：只提交计划中的文件；提交前失败恢复文件，推送失败保留提交以便重试。
- `storage.py`：可迁移的本机配置、草稿和资源存储。

站点生成复用 `scripts/convert_amp.py`，新增的参数保持原命令行转换方式兼容。编辑器源码 JSON 随文章保存在网站的 `content/articles` 中，确保另一台电脑拉取后仍能继续编辑；未发布草稿仅保存在本机。
