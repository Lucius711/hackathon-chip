#!/usr/bin/env python3
"""
CHI DE DEMO/TRINH DIEN cho ban to chuc xem so chay "co ve lai xe that" tren
dashboard - KHONG phai vi du SDK cho thi sinh (xem sdk/send_result_example.py
cho ban toi gian, dung de copy vao code that).

Gui lien tuc ket qua AI (speed/steering/lane/obstacle/confidence) toi carlogd
tai 127.0.0.1:8765, gia tri bien doi theo thoi gian (tang/giam toc do, danh
lai qua trai/phai, thinh thoang "phat hien vat can") thay vi 1 gia tri co
dinh - de demo tren dashboard trong sinh dong hon.

Dung:
    cd pi-daemon
    python demo_drive_loop.py
    python demo_drive_loop.py --duration 60 --rate-ms 50
Bam Ctrl+C de dung som.
"""
import argparse
import json
import math
import random
import socket
import time

CARLOGD_ADDR = ("127.0.0.1", 8765)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--duration", type=float, default=120.0,
                     help="chay bao nhieu giay (mac dinh 120s, Ctrl+C de dung som)")
    ap.add_argument("--rate-ms", type=int, default=80,
                     help="gui 1 goi moi bao nhieu ms (mac dinh 80ms ~ 12.5 lan/giay, "
                          "gan giong toc do suy luan AI camera thuc te)")
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    t0 = time.time()
    progress = 0.0
    obstacle_until = 0.0

    print(f"[demo_drive_loop] dang gui toi 127.0.0.1:8765 moi {args.rate_ms}ms "
          f"trong {args.duration}s - Ctrl+C de dung som.")
    try:
        while True:
            now = time.time()
            t = now - t0
            if t >= args.duration:
                break

            # Toc do dao dong 15..45 km/h theo hinh sin, cong nhieu nho cho
            # tu nhien - mo phong xe tang/giam toc lien tuc tren duong dua.
            speed = 30 + 15 * math.sin(t / 3.0) + random.uniform(-1.5, 1.5)
            speed = max(0.0, speed)

            # Goc lai dao dong -20..20 do, tan so khac de khong dong bo voi toc do.
            steering = 20 * math.sin(t / 1.7 + 0.5) + random.uniform(-2, 2)

            # Lech lan +-5cm, dao dong nhe quanh tim lan.
            lane_offset = 5 * math.sin(t / 2.3) + random.uniform(-0.5, 0.5)

            # Thinh thoang (~5% moi giay) "phat hien vat can" trong 1-2 giay,
            # giong xe thuc gap chuong ngai vat ngau nhien tren duong.
            if now > obstacle_until and random.random() < 0.05 * (args.rate_ms / 1000.0):
                obstacle_until = now + random.uniform(1.0, 2.0)
            obstacle = now < obstacle_until
            if obstacle:
                speed *= 0.4  # xe cham lai khi "thay" vat can, giong logic AI that

            confidence = random.uniform(0.75, 0.99) if not obstacle else random.uniform(0.5, 0.8)
            progress = min(1.0, progress + (args.rate_ms / 1000.0) / 20.0)  # ~20s/vong, tu lap lai
            if progress >= 1.0:
                progress = 0.0

            payload = {
                "speed_kmh": round(speed, 1),
                "steering_deg": round(steering, 1),
                "lane_offset_cm": round(lane_offset, 1),
                "obstacle": obstacle,
                "confidence": round(confidence, 2),
                "progress": round(progress, 3),
            }
            sock.sendto(json.dumps(payload).encode("utf-8"), CARLOGD_ADDR)
            time.sleep(args.rate_ms / 1000.0)
    except KeyboardInterrupt:
        pass
    print("\n[demo_drive_loop] da dung.")


if __name__ == "__main__":
    main()
