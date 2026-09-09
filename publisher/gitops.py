"""Scoped Git publication with rollback before commit and retry after push failure."""
import json
import os
import re
import subprocess
import uuid
from contextlib import contextmanager
from pathlib import Path

from .site import digest
from .storage import AppError, atomic_write, find_git, inside, write_json


def git(config, *args, check=True, timeout=90):
    env = os.environ.copy()
    env['GIT_TERMINAL_PROMPT'] = '0'
    command = [find_git(config), '-c', 'core.quotepath=false']
    if config.get('git_name'):
        command += ['-c', 'user.name=' + config['git_name']]
    if config.get('git_email'):
        command += ['-c', 'user.email=' + config['git_email']]
    command += list(args)
    try:
        result = subprocess.run(command, cwd=config['site_root'], env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8', errors='replace',
                                timeout=timeout, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired as error:
        raise AppError('Git 操作超时，请检查网络、SSH 密钥或登录状态。') from error
    if check and result.returncode:
        message = (result.stderr or result.stdout).strip()
        message = re.sub(r'(https?://)[^/\s]+@', r'\1[已隐藏]@', message)
        raise AppError(message or 'Git 操作失败。')
    return result.stdout.strip() if check else result


def repo_status(config):
    try:
        root = Path(config['site_root']).resolve()
        top = Path(git(config, 'rev-parse', '--show-toplevel')).resolve()
        if root != top:
            raise AppError('所选目录不是 Git 仓库根目录，请选择网站主文件夹。')
        branch = git(config, 'symbolic-ref', '--quiet', '--short', 'HEAD')
        status = git(config, 'status', '--porcelain', '--untracked-files=normal')
        remote = git(config, 'remote', 'get-url', config['remote'], check=False)
        return {'ok': True, 'branch': branch, 'dirty': bool(status), 'changes': status.splitlines(),
                'remote_configured': remote.returncode == 0,
                'git_name': git(config, 'config', 'user.name', check=False).stdout.strip(),
                'git_email': git(config, 'config', 'user.email', check=False).stdout.strip()}
    except (AppError, OSError) as error:
        return {'ok': False, 'error': str(error)}


@contextmanager
def repo_lock(config):
    directory = Path(git(config, 'rev-parse', '--absolute-git-dir'))
    lock = directory / 'duodaa-publisher.lock'
    try:
        with lock.open('x', encoding='utf-8') as handle:
            handle.write(str(os.getpid()))
    except FileExistsError as error:
        raise AppError('这个仓库已有发布任务。如上次异常退出，请确认没有任务运行后删除 .git/duodaa-publisher.lock。') from error
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def publish(store, plan, progress=lambda value: None):
    config = store.config()
    if config != plan.config or store.root() != plan.root:
        raise AppError('网站配置已改变，请重新预览后发布。')
    state = {'job_id': uuid.uuid4().hex, 'site_root': str(plan.root), 'remote': config['remote'],
             'title': plan.document['title'], 'article_id': plan.document['article_id'], 'status': 'preparing'}
    state_path = store.directory / 'jobs' / (state['job_id'] + '.json')
    with repo_lock(config):
        status = repo_status(config)
        if not status.get('ok'):
            raise AppError(status.get('error', 'Git 仓库不可用。'))
        if status['dirty']:
            raise AppError('网站目录有未提交的改动。请先提交或处理这些改动，再上传文章；工具不会把其他文件混入提交。')
        if not status['remote_configured']:
            raise AppError(f'仓库未配置 {config["remote"]} 远程，请先配置 Git 远程地址。')
        if not (config.get('git_name') or status['git_name']) or not (config.get('git_email') or status['git_email']):
            raise AppError('请在设置中填写 Git 提交姓名和邮箱，或使用已配置身份的 Git。')
        state['branch'] = status['branch']
        state['parent'] = git(config, 'rev-parse', 'HEAD')
        progress('正在检查远程分支')
        git(config, 'fetch', '--no-tags', config['remote'])
        remote_ref = f'refs/remotes/{config["remote"]}/{state["branch"]}'
        remote = git(config, 'rev-parse', '--verify', remote_ref, check=False)
        if remote.returncode == 0:
            counts = git(config, 'rev-list', '--left-right', '--count', 'HEAD...' + remote_ref).split()
            if int(counts[1]) > 0:
                raise AppError('远程分支有本地尚未同步的提交，请先在 Git 中同步后重新打开文章。')
        for relative, expected in plan.before.items():
            file = inside(plan.root, relative)
            actual = digest(file.read_bytes()) if file.exists() else None
            if actual != expected:
                raise AppError(f'{relative} 在预览后发生了变化，请重新预览。')
        backup = store.directory / 'jobs' / state['job_id']
        backup.mkdir()
        state['files'] = list(plan.files)
        state['existing'] = [name for name, value in plan.before.items() if value is not None]
        for relative in state['existing']:
            atomic_write(inside(backup, relative), inside(plan.root, relative).read_bytes())
        write_json(state_path, state)
        pathspec = backup / 'paths.txt'
        pathspec.write_bytes(b'\0'.join(name.encode('utf-8') for name in plan.files) + b'\0')
        try:
            progress('正在写入文章、图片和相关页面')
            for relative, data in plan.files.items():
                atomic_write(inside(plan.root, relative), data)
            if git(config, 'rev-parse', 'HEAD') != state['parent']:
                raise AppError('Git 分支在发布过程中发生了变化，请重新检查。')
            progress('正在创建本地 Git 提交')
            git(config, 'add', '--pathspec-from-file=' + str(pathspec), '--pathspec-file-nul')
            git(config, 'commit', '--only', '-m', 'content: ' + plan.document['title'],
                '--pathspec-from-file=' + str(pathspec), '--pathspec-file-nul', timeout=180)
            state['commit'] = git(config, 'rev-parse', 'HEAD')
            state['status'] = 'committed'
            write_json(state_path, state)
        except Exception:
            # A timeout after a successful commit must never roll back committed files.
            head = git(config, 'rev-parse', 'HEAD')
            if head != state['parent']:
                state.update(status='needs_review', error='分支已变化，文件和备份已保留，请检查仓库。')
                write_json(state_path, state)
                raise AppError(state['error'])
            git(config, 'restore', '--staged', '--pathspec-from-file=' + str(pathspec), '--pathspec-file-nul', check=False)
            for relative, data in plan.files.items():
                target = inside(plan.root, relative)
                if target.exists() and target.read_bytes() == data:
                    if relative in state['existing']:
                        atomic_write(target, inside(backup, relative).read_bytes())
                    else:
                        target.unlink()
            state['status'] = 'rolled_back'
            write_json(state_path, state)
            raise
        progress('本地提交完成，正在推送到远程')
        return push_state(store, config, state, progress)


def push_state(store, config, state, progress=lambda value: None):
    file = store.directory / 'jobs' / (state['job_id'] + '.json')
    try:
        git(config, 'push', state['remote'], state['commit'] + ':refs/heads/' + state['branch'], timeout=180)
        state['status'] = 'published'
        state.pop('error', None)
        progress('上传成功')
    except (AppError, OSError) as error:
        state['status'] = 'push_failed'
        state['error'] = str(error)
        progress('已生成文件并本地提交，远程推送失败，可以重试')
    write_json(file, state)
    return state


def retry_push(store, key, progress=lambda value: None):
    if not re.fullmatch(r'[a-f0-9]{32}', key):
        raise AppError('任务编号无效。')
    file = store.directory / 'jobs' / (key + '.json')
    state = json.loads(file.read_text(encoding='utf-8'))
    config = store.config()
    if state.get('site_root') != str(store.root()) or state.get('status') != 'push_failed':
        raise AppError('此任务不属于当前网站，或无需重试。')
    with repo_lock(config):
        if git(config, 'rev-parse', 'HEAD') != state['commit']:
            raise AppError('本地分支已有新的提交，请在 Git 中检查并推送。')
        progress('正在重试推送已有提交')
        return push_state(store, config, state, progress)
