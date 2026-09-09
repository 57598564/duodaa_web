from pathlib import Path
import json
import os
import re
import shutil
import sys
import threading
import uuid
from urllib.parse import urlsplit


class AppError(Exception):
    pass


def inside(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise AppError('文件路径超出所选目录。')
    return path


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep temporary names short: content-addressed images already have long names on Windows.
    temporary = path.with_name('.tmp-' + uuid.uuid4().hex[:12])
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8'))


class Store:
    def __init__(self, directory=None):
        if directory is None:
            base = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
            directory = base / 'data'
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        for child in ['drafts', 'media', 'jobs', 'previews']:
            (self.directory / child).mkdir(exist_ok=True)
        self.lock = threading.RLock()

    def config(self):
        defaults = {'site_root': '', 'site_url': 'https://duodaa.com', 'site_name': '哆嗒数学网',
                    'ad_client': 'ca-pub-9319230211682138', 'git_path': '', 'remote': 'origin',
                    'author': '', 'git_name': '', 'git_email': '', 'recent_count': 5}
        file = self.directory / 'settings.json'
        if file.exists():
            defaults.update(json.loads(file.read_text(encoding='utf-8')))
        return defaults

    def save_config(self, values):
        config = self.config()
        config.update({key: values[key] for key in config if key in values})
        root = Path(config['site_root']).expanduser().resolve()
        if not (root / 'blog/articles').is_dir() or not (root / 'blog/index.html').is_file():
            raise AppError('请选择网站主文件夹，目录中应包含 blog/articles 和 blog/index.html。')
        config['site_root'] = str(root)
        url = urlsplit(config['site_url'])
        if url.scheme != 'https' or not url.hostname or url.username or url.path not in ('', '/') or url.query or url.fragment:
            raise AppError('网站地址请填写完整 HTTPS 域名，例如 https://duodaa.com。')
        config['site_url'] = config['site_url'].rstrip('/')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', config['remote']):
            raise AppError('Git 远程名称格式不正确。')
        if not re.fullmatch(r'ca-pub-\d{16}', config['ad_client']):
            raise AppError('广告发布商 ID 格式不正确。')
        config['recent_count'] = max(1, min(20, int(config['recent_count'])))
        write_json(self.directory / 'settings.json', config)
        return config

    def root(self):
        value = self.config()['site_root']
        if not value:
            raise AppError('请先在设置中选择网站主文件夹。')
        root = Path(value).resolve()
        if not (root / 'blog/articles').is_dir():
            raise AppError('网站目录已移动或不可用，请重新选择。')
        return root

    def save_draft(self, draft):
        with self.lock:
            key = draft.get('draft_id') or uuid.uuid4().hex
            if not re.fullmatch(r'[a-f0-9]{32}', key):
                raise AppError('草稿编号无效。')
            draft['draft_id'] = key
            draft['site_root'] = str(self.root())
            write_json(self.directory / 'drafts' / (key + '.json'), draft)
            return draft

    def drafts(self):
        root = self.config()['site_root']
        result = []
        for path in (self.directory / 'drafts').glob('*.json'):
            draft = json.loads(path.read_text(encoding='utf-8'))
            if draft.get('site_root') == root:
                result.append({'draft_id': draft['draft_id'], 'title': draft.get('title') or '未命名草稿',
                               'updated': path.stat().st_mtime})
        return sorted(result, key=lambda item: item['updated'], reverse=True)

    def draft(self, key):
        if not re.fullmatch(r'[a-f0-9]{32}', key):
            raise AppError('草稿编号无效。')
        value = json.loads((self.directory / 'drafts' / (key + '.json')).read_text(encoding='utf-8'))
        if value.get('site_root') != str(self.root()):
            raise AppError('这份草稿属于另一个网站目录。')
        return value


def find_git(config):
    candidate = config.get('git_path') or shutil.which('git')
    if not candidate:
        raise AppError('未找到 Git。请在设置中指定电脑已有的 git.exe。')
    path = Path(candidate).expanduser().resolve()
    if not path.is_file():
        raise AppError('指定的 Git 程序不存在。')
    return str(path)
