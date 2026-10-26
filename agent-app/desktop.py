"""Native Windows window for the existing editor; no changes to analysis code."""
import ctypes
from ctypes import wintypes
import logging
import os

from launch import ROOT, URL, ensure_server

TITLE = 'AISI-figure'


def activate_existing():
    if os.name != 'nt':
        return False
    user32 = ctypes.windll.user32
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    handle = user32.FindWindowW(None, TITLE)
    if not handle:
        return False
    user32.ShowWindow(handle, 9)
    user32.SetForegroundWindow(handle)
    return True


def run():
    if activate_existing():
        return
    workspace = ROOT / 'workspace'
    workspace.mkdir(exist_ok=True)
    logging.basicConfig(filename=workspace/'desktop.log', encoding='utf-8', level=logging.INFO)
    try:
        import webview
        if os.name == 'nt':
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('AISI.Lab.Figure')
        ensure_server()
        webview.settings['ALLOW_DOWNLOADS'] = True
        webview.create_window(TITLE, URL, width=1200, height=800, min_size=(900, 650), maximized=True,
                              text_select=True, background_color='#FFFFFF')
        webview.start(gui='edgechromium', private_mode=False,
                      storage_path=str(workspace/'desktop-profile'),
                      icon=str(ROOT/'static/brand/aisi-icon.ico'),
                      localization={'global.saveFile': '保存文件', 'global.cancel': '取消',
                                    'windows.fileFilter.allFiles': '所有文件'})
    except Exception:
        logging.exception('Desktop startup failed')
        if os.name == 'nt':
            ctypes.windll.user32.MessageBoxW(None,
                '桌面版启动失败，请查看 agent-app/workspace/desktop.log。', TITLE, 0x10)
        else:
            raise


if __name__ == '__main__':
    run()
