"""Smoke-test the editor inside real WebView2 without changing user drafts."""
import json
from pathlib import Path
import sys
import time
import socket
import subprocess
import tempfile
import urllib.request

APP = Path(__file__).resolve().parents[1] / 'agent-app'
sys.path.insert(0, str(APP))


def check_window(url):
    import webview
    webview.settings['ALLOW_DOWNLOADS'] = True
    result = {'ok': False}
    window = webview.create_window('AISI desktop verification', url, width=1200, height=800, hidden=True)

    def check():
        try:
            if not window.events.loaded.wait(30):
                raise RuntimeError('WebView2 did not load')
            deadline = time.monotonic() + 90
            while not window.evaluate_js("typeof S !== 'undefined' && Object.keys(S.catalog).length === 30"):
                if time.monotonic() > deadline:
                    raise RuntimeError('Editor did not initialize')
                time.sleep(.2)
            window.evaluate_js("window.desktopCheckDone=false; demo().finally(()=>window.desktopCheckDone=true); true")
            while not window.evaluate_js('window.desktopCheckDone'):
                if time.monotonic() > deadline:
                    raise RuntimeError('Example did not finish')
                time.sleep(.2)
            state = window.evaluate_js("({run:S.result?.id, code:document.getElementById('codeEditor').value.length, image:document.getElementById('figureImage').naturalWidth, download:document.getElementById('bundleDownload').getAttribute('href'), message:document.getElementById('toast').textContent})")
            result.update(state)
            assert state.get('run') and state['code'] > 100 and state['image'] > 0 and state['download'], state
            layout = window.evaluate_js("({sidebar:!!document.getElementById('appSidebar'),history:document.querySelectorAll('.sidebar-run').length,account:document.getElementById('connectionSummary').textContent,inside:document.getElementById('datasetSelect').closest('#appSidebar')!==null})")
            assert layout['sidebar'] and layout['history'] > 0 and layout['inside'], layout
            window.evaluate_js("document.getElementById('toggleSidebar').click(); true")
            assert window.evaluate_js("document.body.classList.contains('sidebar-collapsed')"), 'Sidebar did not collapse'
            window.evaluate_js("document.getElementById('expandSidebar').click(); true")
            assert not window.evaluate_js("document.body.classList.contains('sidebar-collapsed')"), 'Sidebar did not expand'
            result['sidebar'] = layout
            window.evaluate_js("document.getElementById('editFigure').click(); true")
            assert window.evaluate_js("document.getElementById('figureEditDialog').open"), 'Edit dialog did not open'
            while not window.evaluate_js("!!document.querySelector('#figureTextCanvas [data-role=note]')"):
                if time.monotonic() > deadline:
                    raise RuntimeError('Selectable PDF text did not load')
                time.sleep(.2)
            actual=window.evaluate_js("({font:document.getElementById('canvasOriginal').textContent,size:Number(document.getElementById('canvasSize').value),note:document.querySelector('#figureTextCanvas [data-role=note]').textContent})")
            assert actual['size'] > 5 and 'AUC' in actual['note'], actual
            result['actual_typography']=actual
            window.evaluate_js("""
                document.getElementById('editTitle').value='Desktop edited title';
                document.getElementById('editTitle').dispatchEvent(new Event('input'));
                document.getElementById('editX').value='False positive rate';
                document.getElementById('editX').dispatchEvent(new Event('input'));
                document.getElementById('fontTitle').value='16';
                document.getElementById('fontNote').value='9';
                const family=document.getElementById('canvasFont'); family.value='Times New Roman'; family.dispatchEvent(new Event('change'));
                document.querySelector('#figureTextCanvas [data-role=note]').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));
                const form=document.getElementById('figureEditForm');
                if(!form.checkValidity())throw Error('Edit form has invalid default values');
                window.desktopEditDone=false;
                const submit=form.onsubmit;form.onsubmit=event=>submit(event).finally(()=>window.desktopEditDone=true);
                form.requestSubmit();
                true
            """)
            while not window.evaluate_js('window.desktopEditDone'):
                if time.monotonic() > deadline:
                    raise RuntimeError('Figure edit did not finish')
                time.sleep(.2)
            edited = window.evaluate_js("({run:S.result?.id, info:S.result?.figure_edit_info, edits:S.result?.figure_edits, error:document.getElementById('figureEditError').textContent})")
            assert edited['run'] != state['run'], edited
            assert edited['info']['title'] == 'Desktop edited title', edited
            assert edited['info']['note_moved'] and edited['edits']['note_hjust']==.5, edited
            assert edited['edits']['note_family']=='Times New Roman', edited
            assert edited['info']['font_sizes']['title_size'] == 16, edited
            result['figure_edit'] = edited
            # History navigation must complete while the other controls are locked.
            window.evaluate_js("window.desktopHistoryDone=false; document.getElementById('historySelect').value=" + json.dumps(state['run']) + "; document.getElementById('historySelect').onchange().finally(()=>window.desktopHistoryDone=true); true")
            while not window.evaluate_js('window.desktopHistoryDone'):
                if time.monotonic() > deadline:
                    raise RuntimeError('History navigation did not finish')
                time.sleep(.1)
            restored = window.evaluate_js("({run:S.result?.id,busy:S.busy,title:S.result?.figure_edit_info?.title||null})")
            assert restored['run'] == state['run'] and not restored['busy'] and restored['title'] is None, restored
            result['history_restored'] = True
            window.evaluate_js("window.desktopDownloadChecked=false; fetch(document.getElementById('bundleDownload').href).then(r=>{window.desktopDownloadChecked=r.ok}); true")
            while not window.evaluate_js('window.desktopDownloadChecked'):
                if time.monotonic() > deadline:
                    raise RuntimeError('Bundle download failed')
                time.sleep(.2)
            result.update(ok=True, **state, native_downloads=webview.settings['ALLOW_DOWNLOADS'])
        except Exception as exc:
            result['error'] = str(exc)
        finally:
            window.destroy()

    webview.start(check, gui='edgechromium', private_mode=True,
                  icon=str(APP/'static/brand/aisi-icon.ico'))
    (APP/'workspace/desktop-verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['ok'] else 1


def main():
    # Use a separate backend so checks cannot adopt or interrupt a user job.
    store = Path(tempfile.mkdtemp(prefix='desktop-check-', dir=APP/'workspace'))
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    code = ('import sys; from pathlib import Path; import core, main, uvicorn; '
            'core.STORE=main.STORE=Path(sys.argv[1]); '
            'uvicorn.run(main.app, host="127.0.0.1", port=int(sys.argv[2]))')
    with (store/'server.log').open('w') as log:
        process = subprocess.Popen([sys.executable, '-c', code, str(store), str(port)],
                                   cwd=APP, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for _ in range(80):
                try:
                    with opener.open(url+'/api/state', timeout=1):
                        break
                except OSError:
                    time.sleep(.25)
            else:
                raise RuntimeError(f'Test backend failed; see {store}')
            return check_window(url)
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == '__main__':
    sys.exit(main())
