# 哆嗒数学网静态站点

全站采用 AMP HTML，可直接部署，不需要后端或构建服务。首页用 SVG 展示 16 种函数，支持 AMP 轮播；文章图片无损提取、去重，公式使用 `amp-mathml`。

日常更新可使用 [绿色版内容客户端](publisher/USER_GUIDE.md)：配置网站主文件夹后，可视化编写或导入微信文章，一键生成 AMP 页面、更新列表及导航，并通过本机已有的 Git 提交、推送。源码与打包方式见 [客户端开发说明](publisher/README.md)。

## 本地预览

```sh
python -m http.server 8765
```

访问 `http://localhost:8765/`。AMP 运行库、公式组件及广告需要联网。

## 广告与 SEO

- AMP 运行库和 `amp-auto-ads` 扩展位于每页 `<head>`，广告元素位于 `<body>` 开头，发布商 ID 为 `ca-pub-9319230211682138`。
- `ads.txt` 位于根目录。上线后需在 AdSense 中确认站点审核和 AMP 自动广告设置；是否实际展示由 AdSense 决定。
- 每页包含标题、摘要、canonical、Open Graph 和 JSON-LD；规范域名为 `https://duodaa.com`。如域名变化，需更新生成脚本并重新生成这些信息。
- `sitemap.xml` 包含 546 个内容 URL，可提交到搜索引擎站长平台。`robots.txt` 已声明站点地图。
- `_redirects` 保留旧 `/blog/index.php/archives/:id/` 地址，并补齐无末尾斜杠版本；不再把所有未知地址重写成首页。支持此约定的静态托管平台会用 `404.html` 返回真正的 404。其他服务器需配置同等重定向与 404 行为。

## 更新与验证

Python 工具需要 `beautifulsoup4` 和 `Pillow`。发布文件已经生成，以下步骤仅供后续维护：

```sh
# 对新导出的普通 HTML 提取图片、统一样式；现有 AMP 页面会跳过。
python scripts/optimize_static.py
# 修改 f.js 中的函数后，重新生成首页与 SVG。
node scripts/build_home.cjs
python scripts/convert_amp.py
python scripts/build_sitemap.py
python scripts/check_site.py
node scripts/check_curves.cjs
```

官方 AMP 校验：

```sh
npm install --prefix .tmp/amp-check amphtml-validator --ignore-scripts --no-audit --no-fund
python scripts/download_amp_checks.py
node scripts/validate_amp.cjs
```

`f.js` 仅供构建时生成曲线使用，页面不执行自定义 JavaScript。`assets/*.css` 是转换前的样式源，AMP 页面将样式去重并内联到 `style amp-custom`，遵守 75 KB 限制。编辑现有 AMP 页面时需同步维护对应源码或重新导入原始 HTML；转换脚本不会覆盖已转换页面的正文和 SEO 信息。

历史 Flash 播放器改为原视频链接；原始文件中已失效的本机图片地址使用文字占位。图片原始字节保留，未进行有损压缩。
