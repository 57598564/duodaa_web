"""Run with the dedicated build venv; bundles Python and the editor, never Git."""
from pathlib import Path
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / 'releases' / 'DuodaaPublisher'
RELEASE.mkdir(parents=True, exist_ok=True)
build_env = os.environ.copy()
build_env['PYINSTALLER_CONFIG_DIR'] = str(ROOT / '.tmp/pyinstaller-cache')
subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed',
                '--name', 'DuodaaPublisher', '--paths', str(ROOT),
                '--distpath', str(RELEASE), '--workpath', str(ROOT / '.tmp/publisher-pyinstaller'),
                '--specpath', str(ROOT / '.tmp'), '--manifest', str(ROOT / 'publisher/portable.manifest'),
                '--add-data', str(ROOT / 'publisher/web') + ';web',
                '--add-data', str(ROOT / 'scripts/convert_amp.py') + ';engine',
                '--hidden-import', 'tkinter', '--hidden-import', 'tkinter.filedialog',
                '--collect-all', 'PIL', str(ROOT / 'publisher/launch.py')], check=True, cwd=ROOT, env=build_env)
shutil.copyfile(ROOT / 'publisher/USER_GUIDE.md', RELEASE / '使用说明.md')
shutil.copyfile(ROOT / 'publisher/THIRD_PARTY.md', RELEASE / '第三方组件说明.md')
licenses = RELEASE / 'licenses'
licenses.mkdir(exist_ok=True)
for name in ['beautifulsoup4', 'Pillow', 'tinycss2', 'soupsieve', 'webencodings', 'typing_extensions']:
    distribution = importlib.metadata.distribution(name)
    for file in distribution.files or []:
        if any(part.lower().startswith(('license', 'copying')) for part in file.parts):
            source = Path(distribution.locate_file(file))
            if source.is_file():
                shutil.copyfile(source, licenses / (name + '-' + source.name))
for name in ['LICENSE.txt', 'LICENSE_PYTHON.txt']:
    source = Path(sys.base_prefix) / name
    if source.exists():
        shutil.copyfile(source, licenses / ('Python-' + name))
shutil.copyfile(ROOT / 'publisher/web/vendor/LICENSE-AMP.txt', licenses / 'AMP-Apache-2.0.txt')
for component in ['tcl8.6', 'tk8.6']:
    source = Path(sys.base_prefix) / 'Library/lib' / component / 'license.terms'
    if source.is_file():
        shutil.copyfile(source, licenses / (component + '-license.terms'))
archive = ROOT / 'releases' / 'DuodaaPublisher-Windows-x64-portable.zip'
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
    for file in sorted(RELEASE.rglob('*')):
        if file.is_file() and 'data' not in file.relative_to(RELEASE).parts:
            bundle.write(file, 'DuodaaPublisher/' + file.relative_to(RELEASE).as_posix())
print(json.dumps({'exe': str(RELEASE / 'DuodaaPublisher.exe'), 'zip': str(archive), 'bytes': archive.stat().st_size}))
