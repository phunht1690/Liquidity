"""User-owned hidden host; no administrator rights, passwords or trading calls.

The host survives launcher/browser closure. Windows autostart is current-user
logon, not a service that can record while the computer is off or asleep.
"""
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import subprocess
import sys
import time
from urllib.request import urlopen
import uuid

from src.data.ssi_feed import PROJECT,VN
from src.data.ssi_runtime import write_json_atomic

DIRECTORY=PROJECT/'data/ssi'
STATE=DIRECTORY/'background_host.json'
CONTROL=DIRECTORY/'background_control.json'
RUN_NAME='LOPM SSI Collector'
RUN_KEY=r'Software\Microsoft\Windows\CurrentVersion\Run'


def read_json(path):
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}


def dashboard_running(port):
    try:
        with urlopen(f'http://127.0.0.1:{port}/api/health',timeout=2) as response:data=json.load(response)
        return data.get('app')=='lopm_vn30' and data.get('auto_update') is True
    except (OSError,ValueError):return False


def hidden_python():
    executable=Path(sys.executable)
    candidate=executable.with_name('pythonw.exe')
    return candidate if os.name=='nt' and candidate.is_file() else executable


def autostart_command(port=8765):
    return subprocess.list2cmdline([str(hidden_python()),str(PROJECT/'scripts/run_background.py'),'--port',str(port)])


def autostart_installed(port=8765):
    if os.name!='nt':return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,RUN_KEY) as key:value,_=winreg.QueryValueEx(key,RUN_NAME)
        return value==autostart_command(port)
    except OSError:return False


def install_autostart(port=8765):
    if os.name!='nt':raise ValueError('Tự khởi động hiện hỗ trợ Windows.')
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,RUN_KEY) as key:
        try:old,_=winreg.QueryValueEx(key,RUN_NAME)
        except FileNotFoundError:old=None
        if old and str(PROJECT/'scripts/run_background.py').lower() not in old.lower():
            raise ValueError('Đang có cấu hình LOPM của thư mục khác; không ghi đè.')
        winreg.SetValueEx(key,RUN_NAME,0,winreg.REG_SZ,autostart_command(port))


def remove_autostart(port=8765):
    if os.name!='nt':return
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,RUN_KEY,0,winreg.KEY_READ|winreg.KEY_SET_VALUE) as key:
            value,_=winreg.QueryValueEx(key,RUN_NAME)
            if str(PROJECT/'scripts/run_background.py').lower() in value.lower():winreg.DeleteValue(key,RUN_NAME)
    except FileNotFoundError:pass


def background_status(port=8765):
    state=read_json(STATE)
    alive=state.get('port')==port and state.get('status')!='stopped' and 0<=time.monotonic()-state.get('heartbeat',0)<30
    return {'running':alive,'autostart':autostart_installed(port),'start_at':'windows_user_logon',
        'status':state.get('status','stopped') if alive else 'stopped'}


@contextmanager
def host_lock(path):
    """An OS lock, released even if the host crashes; never trust a saved PID."""
    path.parent.mkdir(parents=True,exist_ok=True)
    file=path.open('a+b');locked=False
    try:
        file.seek(0,2)
        if file.tell()==0:file.write(b'0');file.flush()
        file.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            locked=True
        except OSError:pass
        yield locked
    finally:
        if locked:
            file.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(file.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(file.fileno(),fcntl.LOCK_UN)
        file.close()


def _popen(arguments,**kwargs):
    env=os.environ.copy();env['PYTHONIOENCODING']='utf-8';env['LOPM_BACKGROUND']='1'
    return subprocess.Popen([str(hidden_python()),'-X','utf8','-B',*arguments],cwd=PROJECT,env=env,
        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0),**kwargs)


def ensure_background(port=8765,timeout=15):
    state=background_status(port)
    if not state['running']:
        _popen(['-m','src.app.background','--port',str(port)])
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if dashboard_running(port):return True
        time.sleep(.2)
    return False


def request_stop(port=8765,timeout=20):
    state=read_json(STATE)
    if not background_status(port)['running']:return True
    write_json_atomic(CONTROL,{'command':'stop','host_token':state.get('host_token')})
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if not background_status(port)['running']:return True
        time.sleep(.2)
    return False


def stop_requested(token):
    command=read_json(CONTROL)
    return command.get('command')=='stop' and command.get('host_token')==token


def configure_logging():
    directory=PROJECT/'data/logs';directory.mkdir(parents=True,exist_ok=True)
    handler=RotatingFileHandler(directory/'background.log',maxBytes=1024*1024,backupCount=2,encoding='utf-8')
    logging.basicConfig(level=logging.INFO,handlers=[handler],format='%(asctime)s %(levelname)s %(message)s')


def supervise(port):
    with host_lock(DIRECTORY/'background.lock') as acquired:
        if not acquired:return 0
        token=uuid.uuid4().hex;child=None;last_start=0;unhealthy_since=None
        def publish(status):
            write_json_atomic(STATE,{'host_token':token,'pid':os.getpid(),'port':port,'status':status,
                'heartbeat':time.monotonic(),'updated_at':datetime.now(VN).isoformat(),
                'server_owned':child is not None and child.poll() is None})
        try:
            while not stop_requested(token):
                healthy=dashboard_running(port)
                if child is not None and child.poll() is not None:child=None
                if not healthy:
                    if child is None and time.monotonic()-last_start>=5:
                        child=_popen(['-m','src.app.server','--port',str(port),'--managed-token',token])
                        last_start=time.monotonic()
                    if unhealthy_since is None:unhealthy_since=time.monotonic()
                    if child and time.monotonic()-unhealthy_since>90:
                        _end_owned(child);child=None;unhealthy_since=None
                else:unhealthy_since=None
                publish('running' if healthy else 'starting')
                for _ in range(25):
                    if stop_requested(token):break
                    time.sleep(.2)
        except (KeyboardInterrupt,OSError):logging.error('Bộ chạy nền dừng; mở lại LOPM để tiếp tục.')
        finally:
            # The managed server sees the same nonce-bound stop request and
            # shuts down its own worker first. Never terminate an external PID.
            write_json_atomic(CONTROL,{'command':'stop','host_token':token})
            if child:
                try:child.wait(timeout=12)
                except subprocess.TimeoutExpired:_end_owned(child)
            publish('stopped')
    return 0


def _end_owned(child):
    if child.poll() is not None:return
    try:
        if os.name=='nt':
            subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=5)
        else:child.terminate()
        child.wait(timeout=5)
    except (OSError,subprocess.TimeoutExpired):pass


def main(argv=None):
    parser=argparse.ArgumentParser(description='Bộ chạy nền LOPM, chỉ đọc SSI')
    parser.add_argument('--port',type=int,default=8765)
    actions=parser.add_mutually_exclusive_group()
    for action in ('install-autostart','remove-autostart','stop','status'):actions.add_argument('--'+action,action='store_true')
    args=parser.parse_args(argv)
    if not 1<=args.port<=65535:parser.error('Cổng không hợp lệ')
    if args.install_autostart:
        install_autostart(args.port)
        print('Đã bật bộ thu sau khi đăng nhập Windows.');return 0
    if args.remove_autostart:
        remove_autostart(args.port)
        print('Đã tắt tự khởi động. Bộ thu đang chạy vẫn tiếp tục.');return 0
    if args.status:
        print(json.dumps(background_status(args.port),ensure_ascii=False));return 0
    if args.stop:
        stopped=request_stop(args.port)
        print('Đã dừng bộ thu nền.' if stopped else 'Bộ thu đang dừng; kiểm tra lại sau vài giây.')
        return 0 if stopped else 1
    configure_logging()
    return supervise(args.port)


if __name__=='__main__':raise SystemExit(main())
