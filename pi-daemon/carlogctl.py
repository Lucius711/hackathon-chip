#!/usr/bin/env python3
"""
carlogctl - cong cu CHI MARSHAL dung (khong phai thi sinh) de mo/dong mot
luot chay cho carlogd dang chay tren xe. Noi qua Unix socket co phan quyen
0660 (group "carlog") - tai khoan SSH cua thi sinh KHONG o trong group do nen
khong goi duoc lenh nay du doc duoc code carlogd.py/carlogctl.py.

Dung:
    python3 carlogctl.py start 42     # bat dau phat cho run_id=42 (lay tu
                                       # POST /api/runs tren trang admin)
    python3 carlogctl.py stop
    python3 carlogctl.py status
"""
import socket
import sys

import config


def send_cmd(text):
    sock = None
    if hasattr(socket, "AF_UNIX"):
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(config.CONTROL_SOCKET)
        except OSError:
            sock = None
    if sock is None:
        # Unix socket khong co/khong ket noi duoc -> thu TCP loopback fallback
        # (carlogd.py tu chuyen sang cai nay khi may khong ho tro AF_UNIX
        # that su, vd Python tren Windows). Tren Pi that neu ca hai deu that
        # bai thi carlogd chua chay, khong phai loi may khong ho tro AF_UNIX.
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(("127.0.0.1", config.CONTROL_TCP_FALLBACK_PORT))
        except OSError:
            print(f"LOI: khong ket noi duoc control server qua Unix socket "
                  f"'{config.CONTROL_SOCKET}' lan TCP 127.0.0.1:{config.CONTROL_TCP_FALLBACK_PORT} "
                  f"- carlogd co dang chay khong? (kiem tra: systemctl status carlogd, "
                  f"hoac xem cua so dang chay run_carlogd_demo.ps1)")
            sys.exit(1)
    sock.sendall(text.encode())
    print(sock.recv(4096).decode().strip())
    sock.close()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "start":
        if len(sys.argv) != 3 or not sys.argv[2].isdigit():
            print("dung: carlogctl.py start <run_id>")
            sys.exit(1)
        send_cmd(f"START {sys.argv[2]}")
    elif cmd == "stop":
        send_cmd("STOP")
    elif cmd == "status":
        send_cmd("STATUS")
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
