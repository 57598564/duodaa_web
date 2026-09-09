"""Loopback-only desktop UI. All content and credentials stay on this computer."""
import argparse
import base64
import json
import mimetypes
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import traceback
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from bs4 import BeautifulSoup

from .content import Media, MEDIA_ID, sanitize_html
from .gitops import publish, retry_push, repo_status
from .site import Plan, articles, load_article, serialize
from .storage import Store, AppError, inside, write_json


class Application:
    def __init__(self, store):
        self.store = store
        self.token = secrets.token_urlsafe(32)
        self.jobs, self.plans = {}, {}
        self.guard = threading.Lock()
        self.active = None
        self.last_seen = time.monotonic()

    def start_job(self, kind, function):
        with self.guard:
            if self.active:
                raise AppError('已有任务正在运行，请稍后再试。')
            key = uuid.uuid4().hex
            self.active = key
            self.jobs[key] = {'job_id': key, 'kind': kind, 'status': 'running', 'message': '正在准备…'}
        def worker():
            def progress(message):
                self.jobs[key]['message'] = message
            try:
                result = function(progress)
                self.jobs[key].update(status='done', result=result)
            except Exception as error:
                self.jobs[key].update(status='error', error=str(error))
                with (self.store.directory / 'publisher.log').open('a', encoding='utf-8') as log:
                    log.write(traceback.format_exc() + '\n')
            finally:
                with self.guard:
                    self.active = None
        threading.Thread(target=worker, daemon=True).start()
        return {'job_id': key}

    def prepare(self, document, progress):
        plan = Plan(self.store, document, progress)
        self.plans[plan.id] = plan
        # Limit large in-memory plans; on-disk previews remain available until the tool exits.
        while len(self.plans) > 4:
            self.plans.pop(next(iter(self.plans)))
        return plan.summary()

    def plan(self, key):
        if key not in self.plans:
            raise AppError('预览已过期，请重新生成。')
        return self.plans[key]

    def history(self):
        result = []
        root = self.store.config()['site_root']
        for file in sorted((self.store.directory / 'jobs').glob('*.json'), key=lambda path: path.stat().st_mtime, reverse=True):
            value = json.loads(file.read_text(encoding='utf-8'))
            if value.get('site_root') == root:
                result.append(value)
        return result[:20]


def preview_html(plan, token):
    soup = BeautifulSoup(plan.files[plan.article_path].decode('utf-8'), 'html.parser')
    for tag in soup.select('script, style[amp-boilerplate], noscript, amp-auto-ads'):
        tag.decompose()
    soup.html.attrs.pop('amp', None)
    for image in soup.select('amp-img, amp-anim'):
        image.name = 'img'
        image['style'] = f'max-width:100%;height:auto;width:{image.get("width", "640")}px'
        source = image.get('src', '')
        if source.startswith('/'):
            image['src'] = f'/preview-resource/{plan.id}' + source + '?token=' + token
        for attr in ['layout']:
            image.attrs.pop(attr, None)
    for formula in soup.select('amp-mathml'):
        formula.name = 'span'
        formula.string = formula.get('data-formula', '')
    for anchor in soup.select('a[href]'):
        anchor['target'] = '_blank'
        anchor['rel'] = 'noopener noreferrer'
        if anchor['href'].startswith('/'):
            anchor['href'] = plan.config['site_url'] + anchor['href']
    style = soup.new_tag('style')
    style.string = '.content img{max-width:100%;height:auto}.source-note{overflow-wrap:anywhere}'
    soup.head.append(style)
    return serialize(soup)


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, app):
        self.app = app
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = 'DuodaaPublisher/1.0'

    def log_message(self, format, *args):
        # URL query strings contain local access tokens; never write them to logs.
        pass

    @property
    def app(self):
        return self.server.app

    def reply(self, data, status=200, content_type='application/json; charset=utf-8'):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; worker-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def authorized(self):
        query = parse_qs(urlsplit(self.path).query)
        supplied = self.headers.get('X-App-Token') or query.get('token', [''])[0]
        if not secrets.compare_digest(supplied, self.app.token):
            raise AppError('访问凭据失效，请从客户端重新打开窗口。')
        self.app.last_seen = time.monotonic()

    def do_GET(self):
        try:
            path = urlsplit(self.path).path
            if path.startswith(('/api/', '/media/', '/site-asset/', '/preview/', '/preview-resource/')):
                self.authorized()
            if path == '/api/state':
                config = self.app.store.config()
                valid = bool(config['site_root']) and (Path(config['site_root']) / 'blog/articles').is_dir()
                self.reply({'config': config, 'root_valid': valid, 'repo': repo_status(config) if valid else {},
                            'drafts': self.app.store.drafts(), 'history': self.app.history(), 'active_job': self.app.active})
            elif path == '/api/heartbeat':
                self.reply({'ok': True})
            elif path == '/api/articles':
                self.reply(articles(self.app.store.root()))
            elif path.startswith('/api/article/'):
                self.reply(load_article(self.app.store.root(), path.rsplit('/', 1)[1]))
            elif path.startswith('/api/draft/'):
                self.reply(self.app.store.draft(path.rsplit('/', 1)[1]))
            elif path.startswith('/api/job/'):
                key = path.rsplit('/', 1)[1]
                if key not in self.app.jobs:
                    raise AppError('任务不存在。')
                self.reply(self.app.jobs[key])
            elif path.startswith('/media/'):
                key = path[7:]
                if not MEDIA_ID.fullmatch(key):
                    raise AppError('图片地址无效。')
                self.serve_file(self.app.store.directory / 'media' / key)
            elif path.startswith('/site-asset/'):
                relative = path[len('/site-asset/'):]
                if not relative.startswith('assets/'):
                    raise AppError('只能读取网站图片。')
                self.serve_image(inside(self.app.store.root(), relative))
            elif path.startswith('/preview-resource/'):
                _, _, key, relative = path.split('/', 3)
                plan = self.app.plan(key)
                if not relative.startswith('assets/'):
                    raise AppError('资源路径无效。')
                target = inside(plan.folder, relative)
                if not target.exists():
                    target = inside(plan.root, relative)
                self.serve_image(target)
            elif path.startswith('/preview/'):
                plan = self.app.plan(path.rsplit('/', 1)[1])
                self.reply(preview_html(plan, self.app.token), content_type='text/html; charset=utf-8')
            else:
                base = Path(sys._MEIPASS) / 'web' if getattr(sys, 'frozen', False) else Path(__file__).parent / 'web'
                relative = 'index.html' if path == '/' else path.lstrip('/')
                self.serve_file(inside(base, relative))
        except (AppError, ValueError, FileNotFoundError) as error:
            self.reply({'error': str(error)}, 400)
        except Exception as error:
            self.reply({'error': str(error)}, 500)

    def serve_image(self, path):
        if path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico'):
            raise AppError('仅可读取图片资源。')
        self.serve_file(path)

    def serve_file(self, path):
        if not path.is_file():
            self.reply({'error': '文件不存在'}, 404)
            return
        mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        if path.suffix == '.js':
            mime = 'application/javascript'
        self.reply(path.read_bytes(), content_type=mime + ('; charset=utf-8' if mime.startswith('text/') else ''))

    def do_POST(self):
        try:
            self.authorized()
            origin = self.headers.get('Origin')
            expected = f'http://127.0.0.1:{self.server.server_port}'
            if origin and origin != expected:
                raise AppError('不允许从其他网站操作客户端。')
            length = int(self.headers.get('Content-Length', '0'))
            if length > 32 * 1024 * 1024 or length < 0:
                raise AppError('请求过大。')
            data = json.loads(self.rfile.read(length) or b'{}')
            path = urlsplit(self.path).path
            if path == '/api/settings':
                if self.app.active:
                    raise AppError('任务运行时不能切换网站目录。')
                self.reply(self.app.store.save_config(data))
            elif path == '/api/browse':
                def browse(progress):
                    import tkinter as tk
                    from tkinter import filedialog
                    dialog = tk.Tk()
                    dialog.withdraw()
                    dialog.attributes('-topmost', True)
                    try:
                        selected = filedialog.askdirectory(title='选择网站内容的主文件夹', parent=dialog, initialdir=self.app.store.config()['site_root'] or None)
                    finally:
                        dialog.destroy()
                    return {'path': selected}
                self.reply(self.app.start_job('browse', browse))
            elif path == '/api/drafts':
                data['content_html'] = sanitize_html(data.get('content_html', ''))
                self.reply(self.app.store.save_draft(data))
            elif path == '/api/media':
                self.reply(Media(self.app.store).upload(data.get('data_url', '')))
            elif path == '/api/import':
                self.reply(self.app.start_job('import', lambda progress: Media(self.app.store).import_article(data['url'], progress)))
            elif path == '/api/localize':
                self.reply(self.app.start_job('localize', lambda progress: {'content_html': Media(self.app.store).localize(data['content_html'], progress)}))
            elif path == '/api/prepare':
                self.reply(self.app.start_job('prepare', lambda progress: self.app.prepare(data, progress)))
            elif path == '/api/publish':
                plan = self.app.plan(data.get('plan_id'))
                if data.get('digest') != plan.digest or sorted(data.get('validated_files', [])) != sorted(plan.html_files):
                    raise AppError('请先完成所有待发布页面的 AMP 校验。')
                self.reply(self.app.start_job('publish', lambda progress: publish(self.app.store, plan, progress)))
            elif path == '/api/retry':
                self.reply(self.app.start_job('retry', lambda progress: retry_push(self.app.store, data['job_id'], progress)))
            elif path == '/api/shutdown':
                if self.app.active:
                    raise AppError('任务尚未完成，暂时不能退出。')
                self.reply({'ok': True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self.reply({'error': '接口不存在'}, 404)
        except (AppError, KeyError, ValueError, OSError) as error:
            self.reply({'error': str(error)}, 400)
        except Exception as error:
            self.reply({'error': str(error)}, 500)


def open_window(url):
    candidates = []
    for base in [os.environ.get('PROGRAMFILES', ''), os.environ.get('PROGRAMFILES(X86)', ''), os.environ.get('LOCALAPPDATA', '')]:
        candidates += [Path(base) / 'Microsoft/Edge/Application/msedge.exe', Path(base) / 'Google/Chrome/Application/chrome.exe']
    for browser in candidates:
        if browser.is_file():
            subprocess.Popen([str(browser), '--app=' + url, '--new-window'], creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            return
    webbrowser.open(url)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--data-dir')
    parser.add_argument('--self-test', help='Write a packaged-runtime self-test result to this file and exit.')
    args = parser.parse_args()
    if args.self_test:
        import tkinter
        from .site import amp_engine
        from PIL import Image
        base = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).parent
        result = {'python': sys.version, 'tcl': tkinter.Tcl().eval('info patchlevel'),
                  'amp_engine': callable(amp_engine().convert), 'editor': (base / 'web/index.html').is_file(),
                  'validator': (base / 'web/vendor/amp-validator.js').is_file()}
        write_json(Path(args.self_test), result)
        return
    store = Store(args.data_dir)
    app = Application(store)
    server = Server(('127.0.0.1', args.port), app)
    url = f'http://127.0.0.1:{server.server_port}/#{app.token}'
    write_json(store.directory / 'instance.json', {'url': url, 'pid': os.getpid()})
    if args.no_browser:
        print('Publisher listening on port', server.server_port, flush=True)
    else:
        open_window(url)
    def watchdog():
        while True:
            time.sleep(20)
            if not app.active and time.monotonic() - app.last_seen > 150:
                server.shutdown()
                return
    threading.Thread(target=watchdog, daemon=True).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
        (store.directory / 'instance.json').unlink(missing_ok=True)


if __name__ == '__main__':
    main()
