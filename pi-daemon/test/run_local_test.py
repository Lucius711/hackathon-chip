#!/usr/bin/env python3
"""
Test tu dong toan bo carlogd tren MAY BAN (khong can Pi/mang thi dau that):
tu dung 1 "ingest gia" (decode bang CHINH protocol.py that), tu chay
carlogd.py that, tu gia lap thi sinh gui ket qua AI khong deu nhip (giong
code thi sinh viet cau tha), roi kiem tra: sequence_no lien tuc, team_id/
run_id dung, JSON dung schema.

Dung:
    python3 run_local_test.py --protocol-dir /duong/dan/toi/Car/simulator

Mac dinh doan protocol.py o ../../hackathon-server/Car/simulator (cau truc
pho bien: hackathon-chip-logic/ va hackathon-server/ nam chung thu muc cha).
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DAEMON_DIR = os.path.dirname(HERE)  # pi-daemon/


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol-dir", default=os.path.join(
        HERE, "..", "..", "..", "hackathon-server", "Car", "simulator"))
    ap.add_argument("--duration", type=float, default=4.0)
    args = ap.parse_args()

    protocol_dir = os.path.abspath(args.protocol_dir)
    if not os.path.isfile(os.path.join(protocol_dir, "protocol.py")):
        print(f"KHONG tim thay protocol.py trong '{protocol_dir}'.\n"
              f"Chay lai voi: --protocol-dir /duong/dan/toi/Car/simulator")
        sys.exit(2)
    sys.path.insert(0, protocol_dir)
    import protocol  # noqa: E402

    work_dir = os.path.join(HERE, "_run")
    os.makedirs(work_dir, exist_ok=True)
    state_file = os.path.join(work_dir, "state.json")
    control_sock = os.path.join(work_dir, "control.sock")
    for f in (state_file, control_sock):
        try:
            os.remove(f)
        except FileNotFoundError:
            pass

    ingest_port = 19999
    local_submit_port = 18765
    team_id = 5
    run_id = 77

    # --- 1) "ingest gia" lang nghe va decode bang protocol.py THAT ---
    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listener.bind(("127.0.0.1", ingest_port))
    listener.settimeout(0.5)

    # --- 2) chay carlogd.py that ---
    env = dict(os.environ)
    env.update({
        "CARLOGD_TEAM_ID": str(team_id),
        "CARLOGD_INGEST_HOST": "127.0.0.1",
        "CARLOGD_INGEST_PORT": str(ingest_port),
        "CARLOGD_LOCAL_PORT": str(local_submit_port),
        "CARLOGD_CONTROL_SOCKET": control_sock,
        "CARLOGD_STATE_FILE": state_file,
        "CARLOGD_PROTOCOL_DIR": protocol_dir,
    })
    daemon = subprocess.Popen([sys.executable, "carlogd.py"], cwd=DAEMON_DIR,
                               env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True)
    time.sleep(0.5)

    # --- 3) marshal: START run_id ---
    subprocess.run([sys.executable, "carlogctl.py", "start", str(run_id)],
                    cwd=DAEMON_DIR, env=env, check=True)

    # --- 4) gia lap thi sinh: gui khong deu nhip (30ms, cham hon 10ms that) ---
    submit_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    t_end = time.time() + args.duration
    t_mid = time.time() + args.duration / 2.0
    i = 0
    sent_bad_burst = False
    RECOVERY_MARKER_SPEED = 999.0  # gia tri "khong the nham lan" de kiem tra carlogd
    # con song (van xu ly duoc goi hop le) SAU khi nhan mot loat goi sai kieu.
    while time.time() < t_end:
        if not sent_bad_burst and time.time() >= t_mid:
            # --- 4b) chen 1 loat goi "cau tha" (sai kieu du lieu, KHONG phai
            # sai JSON/thieu truong - da co du 5 key) giua chung, dung kieu
            # loi tung lam chet thread nhan UDP cua carlogd truoc bugfix (xem
            # test/send_bad_ai_examples.py de biet chi tiet tung truong hop):
            bad_payloads = [
                {"speed_kmh": "abc", "steering_deg": 0, "lane_offset_cm": 0,
                 "obstacle": False, "confidence": 0.5},
                {"speed_kmh": 10, "steering_deg": 0, "lane_offset_cm": 0,
                 "obstacle": False, "confidence": None},
                {"speed_kmh": 10, "steering_deg": 0, "lane_offset_cm": 0,
                 "obstacle": "false", "confidence": 0.5},  # phai duoc hieu la False, khong phai True
                {"speed_kmh": 10, "steering_deg": [1, 2], "lane_offset_cm": 0,
                 "obstacle": False, "confidence": 0.5},
            ]
            for bp in bad_payloads:
                submit_sock.sendto(json.dumps(bp).encode(), ("127.0.0.1", local_submit_port))
                time.sleep(0.03)
            # Goi "marker" hop le NGAY SAU loat goi rac - neu thread nhan UDP
            # cua carlogd da chet vi loat goi tren, marker nay se KHONG BAO GIO
            # toi duoc STATE.latest_ai va se khong xuat hien trong log nhan duoc.
            marker_payload = {"speed_kmh": RECOVERY_MARKER_SPEED, "steering_deg": 0,
                               "lane_offset_cm": 0, "obstacle": False, "confidence": 0.5}
            submit_sock.sendto(json.dumps(marker_payload).encode(), ("127.0.0.1", local_submit_port))
            sent_bad_burst = True
            time.sleep(0.03)
            continue
        payload = {"speed_kmh": 20 + i % 5, "steering_deg": -5.0,
                   "lane_offset_cm": 1.0, "obstacle": False, "confidence": 0.9}
        submit_sock.sendto(json.dumps(payload).encode(), ("127.0.0.1", local_submit_port))
        i += 1
        time.sleep(0.03)

    time.sleep(0.5)
    daemon_alive_after_bad_burst = daemon.poll() is None
    subprocess.run([sys.executable, "carlogctl.py", "stop"], cwd=DAEMON_DIR, env=env)

    # --- 5) thu goi va doi chieu ---
    seen = []
    while True:
        try:
            raw, _ = listener.recvfrom(65535)
        except socket.timeout:
            break
        try:
            seen.append(protocol.decode(raw))
        except Exception as e:
            print("LOI decode:", e)

    daemon.terminate()
    try:
        daemon.wait(timeout=2)
    except subprocess.TimeoutExpired:
        daemon.kill()

    print(f"\nnhan {len(seen)} goi hop le")
    ok = True
    if not seen:
        print("FAIL: khong nhan duoc goi nao.")
        ok = False
    else:
        seqs = sorted(p["sequence_no"] for p in seen)
        gaps = [b - a for a, b in zip(seqs, seqs[1:]) if b - a != 1]
        print(f"sequence_no: {seqs[0]} .. {seqs[-1]} (khoang trong: {gaps or 'khong co'})")
        bad_team = [p for p in seen if p["team_id"] != team_id]
        bad_run = [p for p in seen if p["run_id"] != run_id]
        print(f"team_id sai: {len(bad_team)}, run_id sai: {len(bad_run)}")
        print("mau goi dau:", seen[0])

        got_recovery_marker = any(
            abs(p["ai_result"].get("speed_kmh", -1) - RECOVERY_MARKER_SPEED) < 0.01
            for p in seen)
        print(f"carlogd con song sau loat goi AI sai kieu: {daemon_alive_after_bad_burst}")
        print(f"nhan duoc goi hop le NGAY SAU loat goi rac (marker={RECOVERY_MARKER_SPEED}): "
              f"{got_recovery_marker}")

        ok = (not gaps and not bad_team and not bad_run
              and daemon_alive_after_bad_burst and got_recovery_marker)

    print("\n=> " + ("PASS" if ok else "FAIL"))

    print("\n----- log cua carlogd (neu can debug) -----")
    print(daemon.stdout.read() if daemon.stdout else "(khong doc duoc)")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
