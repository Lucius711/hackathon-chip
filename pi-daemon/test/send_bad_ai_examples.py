#!/usr/bin/env python3
"""
Kich ban KIEM THU (khong phai vi du SDK cho thi sinh thuc - xem
sdk/send_result_example.py cho ban dung de copy vao code that). File nay mo
phong mot thi sinh "cau tha" - code AI cua ho thinh thoang gui du lieu sai
dinh dang/sai kieu (bug thuong gap: ep kieu nham, gui null khi chua co gia
tri, serialize boolean thanh chuoi "false"...) - de kiem tra carlogd.py CO
CON SONG va tiep tuc nhan du lieu HOP LE sau nhung goi rac do khong.

Truoc bugfix (xem README/thao luan): 1 goi voi truong dung ten nhung SAI KIEU
(vd "speed_kmh": "abc") se lam chet han thread nhan UDP cua carlogd - dich vu
van bao "active (running)" nhung tu do KHONG con nhan duoc ket qua AI moi nao
nua ca luot. Sau bugfix: goi loai nay bi bo qua (co canh bao in ra stderr moi
5s), cac goi hop le gui SAU do van duoc nhan binh thuong.

Dung (carlogd.py phai dang chay san, vd qua run_carlogd_demo.ps1 hoac
test/run_local_test.py):

    python3 test/send_bad_ai_examples.py
    python3 test/send_bad_ai_examples.py --port 18765   # neu carlogd dang dung port khac (vd trong run_local_test.py)

Cach kiem tra bang mat: mo song song cua so dang chay carlogd (hoac
`journalctl -u carlogd -f` neu chay that tren Pi) - phai thay dong CANH BAO
"goi AI sai kieu du lieu... bi bo qua", KHONG thay traceback/Exception nao,
va sau khi script nay chay xong, carlogd van dang "active"/van in duoc dong
thong ke "da_gui=..." dinh ky - chung to thread nhan UDP khong bi chet.
"""
import argparse
import json
import socket
import time

CARLOGD_ADDR_DEFAULT_PORT = 8765

# Cac goi "cau tha" - moi dong la 1 kieu loi rieng ma code thi sinh thuc te
# de mac phai. Tat ca deu co du 5 KEY bat buoc (qua duoc buoc kiem tra
# REQUIRED_AI_FIELDS) nhung sai o GIA TRI/KIEU - dung loai loi ma bug cu
# (float() khong bat exception) se lam chet thread.
BAD_PAYLOADS = [
    # (mo ta, payload)
    ("speed_kmh la chuoi khong phai so",
     {"speed_kmh": "abc", "steering_deg": 0, "lane_offset_cm": 0, "obstacle": False, "confidence": 0.5}),
    ("confidence la null (thi sinh chua kip gan gia tri)",
     {"speed_kmh": 10, "steering_deg": 0, "lane_offset_cm": 0, "obstacle": False, "confidence": None}),
    ("steering_deg la list (loi ep kieu trong code thi sinh)",
     {"speed_kmh": 10, "steering_deg": [1, 2], "lane_offset_cm": 0, "obstacle": False, "confidence": 0.5}),
    ("obstacle la chuoi 'false' (van phai hieu dung la False, khong phai True)",
     {"speed_kmh": 10, "steering_deg": 0, "lane_offset_cm": 0, "obstacle": "false", "confidence": 0.5}),
    ("obstacle la chuoi rac khong xac dinh duoc true/false",
     {"speed_kmh": 10, "steering_deg": 0, "lane_offset_cm": 0, "obstacle": "khong-ro", "confidence": 0.5}),
    ("lane_offset_cm la dict (loi nghiem trong, gan nhu chac chan la bug code)",
     {"speed_kmh": 10, "steering_deg": 0, "lane_offset_cm": {}, "obstacle": False, "confidence": 0.5}),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=CARLOGD_ADDR_DEFAULT_PORT,
                     help=f"cong LOCAL_SUBMIT_PORT cua carlogd dang chay (mac dinh {CARLOGD_ADDR_DEFAULT_PORT})")
    ap.add_argument("--gap-s", type=float, default=0.3, help="khoang cach giua moi goi (giay)")
    args = ap.parse_args()

    addr = (args.host, args.port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(payload, note):
        sock.sendto(json.dumps(payload).encode("utf-8"), addr)
        print(f"  gui: {note}\n    -> {payload}")
        time.sleep(args.gap_s)

    good_before = {"speed_kmh": 20.0, "steering_deg": -5.0, "lane_offset_cm": 1.0,
                   "obstacle": False, "confidence": 0.9}
    good_after = {"speed_kmh": 42.0, "steering_deg": 7.5, "lane_offset_cm": -2.0,
                  "obstacle": True, "confidence": 0.6}

    print(f"[send_bad_ai_examples] dang gui toi {args.host}:{args.port}\n")
    print("1) Gui 1 goi HOP LE lam moc so sanh (marker=20.0 km/h):")
    send(good_before, "goi hop le (truoc)")

    print("\n2) Gui lan luot cac goi CAU THA (moi loai la 1 bug thuong gap):")
    for note, payload in BAD_PAYLOADS:
        send(payload, note)

    print("\n3) Gui lai 1 goi HOP LE (marker=42.0 km/h) - neu carlogd van song,")
    print("   gia tri nay phai xuat hien trong log/dashboard NGAY SAU cac goi rac o tren:")
    send(good_after, "goi hop le (sau) - marker=42.0")

    print("\nXong. Kiem tra cua so carlogd: phai thay dong CANH BAO ve goi sai kieu,")
    print("KHONG duoc thay traceback/Exception, va carlogd phai van dang gui du lieu binh thuong.")


if __name__ == "__main__":
    main()
