from pathlib import Path
from types import SimpleNamespace
import json
import time
import pytest

from src.app import background,launcher


@pytest.fixture
def runtime(monkeypatch,tmp_path):
    monkeypatch.setattr(background,'DIRECTORY',tmp_path)
    monkeypatch.setattr(background,'STATE',tmp_path/'host.json')
    monkeypatch.setattr(background,'CONTROL',tmp_path/'command.json')
    monkeypatch.setattr(background,'autostart_installed',lambda port:False)
    return tmp_path


def test_os_lock_prevents_duplicate_hosts_and_releases_after_close(runtime):
    with background.host_lock(runtime/'lock') as first:
        assert first
        with background.host_lock(runtime/'lock') as second:assert not second
    with background.host_lock(runtime/'lock') as third:assert third


def test_stop_is_scoped_to_current_instance_and_not_an_old_saved_pid(runtime):
    background.write_json_atomic(background.CONTROL,{'command':'stop','host_token':'old'})
    assert not background.stop_requested('new')
    assert background.stop_requested('old')
    background.write_json_atomic(background.STATE,{'pid':1234,'port':8765,'heartbeat':time.monotonic()-31,'status':'running'})
    assert not background.background_status()['running']


def test_launch_returns_when_healthy_without_spawning_another_host(runtime,monkeypatch):
    background.write_json_atomic(background.STATE,{'port':8765,'heartbeat':time.monotonic(),'status':'running'})
    monkeypatch.setattr(background,'_popen',lambda *a:pytest.fail('Duplicate host'))
    monkeypatch.setattr(background,'dashboard_running',lambda port:True)
    assert background.ensure_background()


def test_launcher_background_does_not_open_browser_or_block_in_server(monkeypatch):
    ensured=[]
    monkeypatch.setattr(launcher,'ensure_background',lambda port:ensured.append(port) or True)
    monkeypatch.setattr(launcher.webbrowser,'open',lambda *a,**k:pytest.fail('Background opened browser'))
    assert launcher.main(['--background'])==0 and ensured==[8765]


def test_hidden_process_has_no_window_or_inherited_terminal(monkeypatch,runtime):
    captured=[]
    monkeypatch.setattr(background.subprocess,'Popen',lambda args,**kwargs:captured.append((args,kwargs)))
    background._popen(['-m','src.app.server','--port','8765'])
    args,options=captured[0]
    assert options['stdout']==options['stderr']==options['stdin']==background.subprocess.DEVNULL
    assert options['env']['LOPM_BACKGROUND']=='1'
    assert options['creationflags'] & background.subprocess.CREATE_NO_WINDOW
    assert '--open-browser' not in args


def test_supervisor_gracefully_stops_only_server_it_started(runtime,monkeypatch):
    created=[];waited=[];checks=[]
    class Child:
        def poll(self):return None
        def wait(self,timeout):waited.append(timeout)
    def spawn(args):created.append(args);return Child()
    monkeypatch.setattr(background,'dashboard_running',lambda port:False)
    monkeypatch.setattr(background,'_popen',spawn)
    monkeypatch.setattr(background,'stop_requested',lambda token:checks.append(1) or len(checks)>1)
    assert background.supervise(8765)==0
    assert len(created)==1 and '--managed-token' in created[0]
    assert waited==[12]
    assert background.read_json(background.STATE)['status']=='stopped'


def test_stop_does_not_terminate_server_started_elsewhere(runtime,monkeypatch):
    checks=[]
    monkeypatch.setattr(background,'dashboard_running',lambda port:True)
    monkeypatch.setattr(background,'_popen',lambda *a:pytest.fail('Existing server duplicated'))
    monkeypatch.setattr(background,'_end_owned',lambda *a:pytest.fail('External PID terminated'))
    monkeypatch.setattr(background,'stop_requested',lambda token:checks.append(1) or len(checks)>1)
    assert background.supervise(8765)==0


def test_autostart_command_quotes_workspace_with_spaces_and_no_credentials():
    command=background.autostart_command()
    assert 'run_background.py' in command and '--port 8765' in command
    assert 'API_KEY' not in command and '.env' not in command


def test_registry_install_and_remove_only_touch_current_user_lopm_entry(monkeypatch):
    store={};opened=[]
    class Key:
        def __enter__(self):return self
        def __exit__(self,*a):pass
    def open_key(root,path,*args):opened.append((root,path));return Key()
    def query(key,name):
        if name not in store:raise FileNotFoundError()
        return store[name],1
    registry=SimpleNamespace(HKEY_CURRENT_USER=1,REG_SZ=1,KEY_READ=1,KEY_SET_VALUE=2,
        CreateKey=open_key,OpenKey=open_key,QueryValueEx=query,
        SetValueEx=lambda key,name,reserved,kind,value:store.__setitem__(name,value),
        DeleteValue=lambda key,name:store.pop(name))
    monkeypatch.setitem(__import__('sys').modules,'winreg',registry)
    background.install_autostart()
    assert background.autostart_installed() and list(store)==[background.RUN_NAME]
    background.remove_autostart()
    assert not store and all(root==registry.HKEY_CURRENT_USER and path==background.RUN_KEY for root,path in opened)
    store[background.RUN_NAME]='another-project run_background.py'
    with pytest.raises(ValueError):background.install_autostart()
    background.remove_autostart();assert store
