import base64
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup
from PIL import Image

from publisher.content import Media, sanitize_html, check_remote_url
from publisher.gitops import publish, retry_push
from publisher.site import Plan, articles, load_article
from publisher.storage import Store, AppError

REPO = Path(__file__).resolve().parents[2]


def fixture_site(directory):
    directory.mkdir(parents=True)
    for relative in ['index.html', 'blog/index.html', 'blog/archive.html', 'blog/about.html', 'assets/blog.css', 'assets/site.css', 'favicon.ico']:
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, target)
    shutil.copytree(REPO / 'blog/articles', directory / 'blog/articles')
    # Copy only the assets used by the few modern pages, rather than the complete historical library.
    for page in (directory / 'blog').rglob('*.html'):
        soup = BeautifulSoup(page.read_text(encoding='utf-8'), 'html.parser')
        for node in soup.select('amp-img, amp-anim'):
            value = node.get('src', '')
            if value.startswith('/assets/'):
                target = directory / value.lstrip('/')
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO / value.lstrip('/'), target)
    (directory / '.gitattributes').write_text('* text=auto\n*.html text eol=lf\n*.json text eol=lf\n*.xml text eol=lf\n', encoding='utf-8')


def run(directory, *args):
    return subprocess.run(['git', *args], cwd=directory, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace').stdout.strip()


class PublisherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='publisher-tests-', dir=REPO / '.tmp')
        cls.base = Path(cls.temp.name)
        cls.fixture = cls.base / 'fixture'
        fixture_site(cls.fixture)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.directory = self.base / str(abs(hash(self._testMethodName)))[:8]
        self.directory.mkdir()
        self.root = self.directory / 'site'
        shutil.copytree(self.fixture, self.root)
        self.store = Store(self.directory / 'portable-data')
        self.store.save_config({'site_root': str(self.root), 'git_name': 'Publisher Tests', 'git_email': 'tests@example.invalid'})
        image = io.BytesIO()
        Image.new('RGB', (640, 320), 'blue').save(image, format='PNG')
        self.image = image.getvalue()

    def document(self, **extra):
        media = Media(self.store).add(self.image)
        return {'title': '测试：数学与图像', 'author': '测试作者', 'published_at': '2026-09-09T12:00:00+08:00',
                'description': '这是一篇测试摘要。', 'source_url': 'https://mp.weixin.qq.com/s/example',
                'content_html': '<h2>标题</h2><p><strong>可视化编辑</strong>与公式 $$x^2+y^2=1$$。</p>'
                    f'<p><img src="{media["src"]}" style="width:240px;height:auto" alt="蓝色示意图"></p>', **extra}

    def git_init(self):
        run(self.root, 'init', '-b', 'main')
        run(self.root, 'config', 'user.name', 'Publisher Tests')
        run(self.root, 'config', 'user.email', 'tests@example.invalid')
        run(self.root, 'add', '.')
        run(self.root, 'commit', '-m', 'fixture')
        self.remote = self.directory / 'remote.git'
        run(self.directory, 'init', '--bare', str(self.remote))
        run(self.root, 'remote', 'add', 'origin', str(self.remote))
        run(self.root, 'push', '-u', 'origin', 'main')

    def test_plan_updates_navigation_recents_seo_and_images(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob('*.html')}
        plan = Plan(self.store, self.document())
        for path, data in before.items():
            self.assertEqual(Path(path).read_bytes(), data, 'Preview must not modify website files')
        soup = BeautifulSoup(plan.files[plan.article_path].decode(), 'html.parser')
        self.assertTrue(soup.html.has_attr('amp'))
        self.assertEqual(soup.select_one('amp-img')['width'], '240')
        self.assertEqual(soup.select_one('amp-img')['height'], '120')
        self.assertIsNotNone(soup.select_one('amp-mathml'))
        self.assertEqual(soup.select_one('amp-auto-ads')['data-ad-client'], self.store.config()['ad_client'])
        self.assertEqual(json.loads(soup.select_one('script[type="application/ld+json"]').string)['author']['name'], '测试作者')
        self.assertIn(plan.document['article_id'], plan.files['sitemap.xml'].decode())
        home = BeautifulSoup(plan.files['blog/index.html'].decode(), 'html.parser')
        self.assertEqual(home.select_one('.post h2').get_text(), plan.document['title'])
        self.assertEqual(home.select_one('.sidebar .list a').get_text(), plan.document['title'])
        older = articles(self.root)[0]
        older_path = 'blog/articles/' + older['article_id'] + '/index.html'
        older_soup = BeautifulSoup(plan.files[older_path].decode(), 'html.parser')
        self.assertEqual(older_soup.select_one('.nav-posts .prev')['href'], '/blog/articles/' + plan.document['article_id'] + '/')
        self.assertEqual(soup.select_one('.nav-posts .next')['href'], older['url'])
        # Export generated samples for official validator/browser smoke tests.
        output = REPO / '.tmp/publisher-samples'
        output.mkdir(exist_ok=True)
        for i, path in enumerate(plan.html_files):
            (output / f'{i}.html').write_bytes(plan.files[path])

    def test_publish_and_edit_use_only_generated_paths(self):
        self.git_init()
        plan = Plan(self.store, self.document())
        result = publish(self.store, plan)
        self.assertEqual(result['status'], 'published')
        self.assertEqual(run(self.root, 'status', '--porcelain'), '')
        self.assertEqual(run(self.remote, 'rev-parse', 'refs/heads/main'), result['commit'])
        loaded = load_article(self.root, plan.document['article_id'])
        self.assertIn('width:240px', loaded['content_html'])
        self.assertIn('/assets/images/', loaded['content_html'])
        loaded['title'] = '修改后的标题'
        edited = Plan(self.store, loaded)
        outcome = publish(self.store, edited)
        self.assertEqual(outcome['status'], 'published')
        self.assertEqual(edited.article_path, plan.article_path)
        self.assertEqual(len(articles(self.root)), len(articles(self.fixture)) + 1)

    def test_failed_push_can_retry_without_duplicate_commit(self):
        self.git_init()
        hook = self.remote / 'hooks/pre-receive'
        hook.write_text('#!/bin/sh\nexit 1\n', encoding='utf-8', newline='\n')
        plan = Plan(self.store, self.document())
        result = publish(self.store, plan)
        self.assertEqual(result['status'], 'push_failed')
        self.assertTrue((self.root / plan.article_path).exists())
        commit = run(self.root, 'rev-parse', 'HEAD')
        hook.unlink()
        result = retry_push(self.store, result['job_id'])
        self.assertEqual(result['status'], 'published')
        self.assertEqual(run(self.root, 'rev-parse', 'HEAD'), commit)

    def test_commit_failure_rolls_back_files(self):
        self.git_init()
        previous = (self.root / 'blog/index.html').read_bytes()
        hook = self.root / '.git/hooks/pre-commit'
        hook.write_text('#!/bin/sh\nexit 1\n', encoding='utf-8', newline='\n')
        plan = Plan(self.store, self.document())
        with self.assertRaises(AppError):
            publish(self.store, plan)
        self.assertEqual((self.root / 'blog/index.html').read_bytes(), previous)
        self.assertFalse((self.root / plan.article_path).exists())
        self.assertEqual(run(self.root, 'status', '--porcelain'), '')

    def test_dirty_repository_is_not_published(self):
        self.git_init()
        unrelated = self.root / 'personal-note.txt'
        unrelated.write_text('private work')
        plan = Plan(self.store, self.document())
        with self.assertRaisesRegex(AppError, '未提交'):
            publish(self.store, plan)
        self.assertEqual(unrelated.read_text(), 'private work')
        self.assertFalse((self.root / plan.article_path).exists())

    def test_stale_article_and_changed_preview_are_rejected(self):
        self.git_init()
        existing = articles(self.root)[0]
        document = load_article(self.root, existing['article_id'])
        page = self.root / 'blog/articles' / existing['article_id'] / 'index.html'
        page.write_bytes(page.read_bytes() + b'\n')
        with self.assertRaisesRegex(AppError, '已被其他操作更新'):
            Plan(self.store, document)

    def test_wechat_import_retains_text_styles_and_local_images(self):
        article = '<html><h1 id="activity-name">微信标题</h1><span id="js_name">测试公众号</span><div id="js_content"><p style="color:rgb(200,0,0)">正文内容</p><img data-src="https://mmbiz.qpic.cn/test.png" style="width:320px"><script>alert(1)</script></div></html>'
        def fetch(url, **kwargs):
            return article.encode() if kwargs.get('article') else self.image
        result = Media(self.store, fetch).import_article('https://mp.weixin.qq.com/s/example')
        self.assertEqual(result['title'], '微信标题')
        self.assertEqual(result['author'], '测试公众号')
        self.assertIn('/media/', result['content_html'])
        self.assertIn('color:rgb(200,0,0)', result['content_html'])
        self.assertNotIn('<script', result['content_html'])
        with self.assertRaises(AppError):
            Media(self.store, lambda *args, **kwargs: b'<html>captcha</html>').import_article('https://mp.weixin.qq.com/s/example')

    def test_portable_folder_can_be_reconfigured(self):
        other = self.directory / 'another-computer-site'
        shutil.copytree(self.fixture, other)
        self.store.save_config({'site_root': str(other)})
        self.assertEqual(Store(self.store.directory).root(), other.resolve())
        self.assertEqual(Plan(self.store, self.document()).root, other.resolve())

    def test_sanitization_and_wechat_url_boundaries(self):
        value = sanitize_html('<p onclick="evil()" style="color:red;position:fixed;background:url(https://evil/x)">text</p><a href="javascript:evil()">bad</a><iframe src="x"></iframe>')
        self.assertNotIn('onclick', value)
        self.assertNotIn('javascript:', value)
        self.assertNotIn('position:', value)
        self.assertNotIn('url(', value)
        self.assertNotIn('iframe', value)
        for url in ['http://localhost/s/a', 'https://mp.weixin.qq.com.evil.test/s/a', 'file:///tmp', 'https://mp.weixin.qq.com:999/s/a']:
            with self.assertRaises(AppError):
                check_remote_url(url, article=True)
        with patch('publisher.content.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 443))]):
            with self.assertRaises(AppError):
                check_remote_url('https://mp.weixin.qq.com/s/test', article=True)


if __name__ == '__main__':
    unittest.main()
