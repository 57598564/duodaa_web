"""PyInstaller entry point (kept separate for package-relative imports)."""
from publisher.app import main

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        import json
        import sys
        from pathlib import Path
        if '--self-test' in sys.argv:
            target = Path(sys.argv[sys.argv.index('--self-test') + 1])
            target.write_text(json.dumps({'error': str(error)}, ensure_ascii=False), encoding='utf-8')
            raise SystemExit(1)
        folder = Path(sys.executable).parent / 'data'
        folder.mkdir(exist_ok=True)
        (folder / 'startup-error.log').write_text(str(error), encoding='utf-8')
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(error), '哆嗒内容发布工具', 0x10)
