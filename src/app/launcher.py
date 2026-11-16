"""One-click local launch: reuse the running dashboard and its warm collector."""
import argparse
import webbrowser
from src.app.background import dashboard_running,ensure_background


def main(argv=None):
    parser=argparse.ArgumentParser(description='Mở LOPM và tự khởi động bộ thu SSI FastConnect')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--background',action='store_true',help='Chạy nền, không mở trình duyệt')
    parser.add_argument('--foreground',action='store_true',help='Chạy trực tiếp trong terminal để kiểm tra')
    args=parser.parse_args(argv)
    if not 1<=args.port<=65535:parser.error('Cổng không hợp lệ')
    try:
        if args.foreground:
            from src.app.server import main as serve
            serve(['--port',str(args.port),*(['--open-browser'] if not args.background else [])])
        elif ensure_background(args.port):
            if not args.background:webbrowser.open(f'http://127.0.0.1:{args.port}/',new=2)
            print('LOPM đang chạy nền. Đóng cửa sổ hoặc tab web vẫn tiếp tục thu SSI.')
        else:
            print('Chưa mở được máy chủ. Kiểm tra cổng đang dùng và data/logs.');return 1
    except OSError:
        print('Chưa mở được máy chủ. Kiểm tra cổng đang dùng hoặc cửa sổ LOPM đang chạy.')
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
