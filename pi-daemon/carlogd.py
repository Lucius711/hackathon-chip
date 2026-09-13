#!/usr/bin/env python3
"""
carlogd - service NEN chay tren Raspberry Pi gan tren xe. Day la TOAN BO phan
"ket noi mang + gui log dung dinh dang DB" ma ban to chuc phai chuan bi san -
thi sinh SSH vao xe KHONG duoc dung/sua file nay (xem provision/README.md ve
phan quyen Linux).

Thi sinh chi can gui ket qua AI cua ho (JSON) toi MOT CONG UDP NOI BO
(127.0.0.1:LOCAL_PORT), bang bat ky ngon ngu nao (Python/C/Node/Go/bash+nc...)
- vi du xem trong sdk/. carlogd se:
  1. Nhan JSON do, chi giu lai ban MOI NHAT (khong quan tam thi sinh gui
     nhanh/cham/khong deu bao nhieu).
  2. Cu moi 10ms, lay ban moi nhat dang co, TU DIEN run_id/team_id/
     sequence_no/car_timestamp (thi sinh KHONG the thay doi 4 truong nay),
     dong goi dung schema Car/simulator/protocol.py, gui that ra
     ingest_server.py qua mang thi dau.
  3. Neu thi sinh CHUA gui gi (code cua ho crash, hoac chua chay), van gui
     mot goi "an toan" (obstacle=true, speed=0) moi 10ms thay vi bo qua chu
     ky - tranh tao khoang trong sequence_no gia (xem README chinh, muc
     fairness).
  4. sequence_no lien tuc, khong lap/nhay, song sot qua restart service
     giua run (luu xuong STATE_FILE dinh ky) - dung trach nhiem nhu
     fairness_guard.c ben firmware ESP32 truoc do, chi khac ngon ngu.

Dieu khien run_id/team_id: xem carlogctl.py (chi marshal dung, qua Unix
socket co phan quyen rieng - contestant KHONG goi duoc).
"""
import json
import os
import socket
import stat
import sys
import threading
import time
import urllib.error
import urllib.request

import config

# ---------------------------------------------------------------------------
#  Trang thai dung chung, bao ve bang lock (1 thread nhan tu contestant,
#  1 thread nhan lenh marshal, 1 vong lap gui chinh 10ms).
# ---------------------------------------------------------------------------
class SharedState:
    def __init__(self):
        self.lock = threading.Lock()
        self.run_id = None          # None = chua co run nao dang mo
        self.team_id = config.TEAM_ID
        self.next_seq = 0
        self.latest_ai = None       # dict gan nhat contestant gui, hoac None
        self.last_send_ms = None

    def load_persisted(self):
        try:
            with open(config.STATE_FILE) as f:
                data = json.load(f)
            if data.get("run_id") is not None:
                with self.lock:
                    self.run_id = data["run_id"]
                    self.next_seq = data.get("next_seq", 0)
                print(f"[carlogd] khoi phuc trang thai: run_id={self.run_id} "
                      f"next_seq={self.next_seq} (co the la resume sau crash/restart)")
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[carlogd] CANH BAO: doc STATE_FILE loi ({e}), bo qua.", file=sys.stderr)

    def persist(self):
        tmp = config.STATE_FILE + ".tmp"
        with self.lock:
            data = {"run_id": self.run_id, "next_seq": self.next_seq}
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, config.STATE_FILE)  # ghi nguyen tu, khong bao gio hong file giua chung


STATE = SharedState()


# ---------------------------------------------------------------------------
#  1) Nhan ket qua AI tu thi sinh - UDP noi bo, MO cho moi user tren may (do
#     chinh la muc dich: thi sinh viet ngon ngu gi cung goi duoc).
# ---------------------------------------------------------------------------
REQUIRED_AI_FIELDS = {"speed_kmh", "steering_deg", "lane_offset_cm", "obstacle", "confidence"}
_TRUE_STRINGS = {"true", "1", "yes", "on"}
_FALSE_STRINGS = {"false", "0", "no", "off"}


def _coerce_obstacle(value):
    """Chap nhan bool that (JSON true/false) hoac string "true"/"false" - MOT
    SO ngon ngu/thu vien JSON cua thi sinh (script tu viet, hoac ep kieu tay)
    co the serialize boolean thanh chuoi. KHONG duoc dung bool(value) truc
    tiep: bool("false") == True trong Python vi chuoi khong rong la truthy -
    day tung la 1 bug (obstacle=False bi ghi nham thanh True khi gui duoi
    dang chuoi)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in _TRUE_STRINGS:
            return True
        if low in _FALSE_STRINGS:
            return False
        raise ValueError(f"gia tri obstacle khong hop le: {value!r}")
    if isinstance(value, (int, float)):
        return bool(value)
    raise ValueError(f"kieu du lieu obstacle khong ho tro: {type(value).__name__}")


def _coerce_ai_payload(obj):
    """Chuyen doi + kiem tra KIEU du lieu cho 5 truong bat buoc (+ progress
    tuy chon). Nem TypeError/ValueError neu thi sinh gui sai KIEU (vd chuoi
    khong phai so, null, list...) de ai_submit_server() bat va bo qua dung
    GOI DO - khong duoc de loi nay thoat ra ngoai va lam chet thread nhan UDP
    (bug cu: float("abc") hoac float(None) raise exception khong ai bat, lam
    thread nay chet vinh vien - carlogd van bao "active" nhung tu do KHONG
    con nhan duoc ket qua AI moi nao nua cho ca luot chay)."""
    result = {
        "speed_kmh": float(obj["speed_kmh"]),
        "steering_deg": float(obj["steering_deg"]),
        "lane_offset_cm": float(obj["lane_offset_cm"]),
        "obstacle": _coerce_obstacle(obj["obstacle"]),
        "confidence": float(obj["confidence"]),
    }
    if isinstance(obj.get("progress"), (int, float)):
        result["progress"] = float(obj["progress"])
    return result


def ai_submit_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", config.LOCAL_SUBMIT_PORT))
    print(f"[carlogd] dang nhan ket qua AI tu thi sinh tai 127.0.0.1:{config.LOCAL_SUBMIT_PORT}")
    bad_count = 0
    last_warn = time.monotonic()
    while True:
        raw, _ = sock.recvfrom(65535)
        try:
            obj = json.loads(raw.decode("utf-8"))
        except Exception:
            continue  # JSON thi sinh gui sai dinh dang - lang le bo qua, khong lam sap dich vu
        if not isinstance(obj, dict) or not REQUIRED_AI_FIELDS.issubset(obj.keys()):
            continue  # thieu truong bat buoc (hoac khong phai object JSON) - bo qua, giu ban cu
        try:
            parsed = _coerce_ai_payload(obj)
        except (TypeError, ValueError):
            # Du co du 5 truong nhung SAI KIEU (vd "speed_kmh": "abc" hoac
            # null) - bo qua dung goi nay, giu nguyen ban cu, KHONG lam chet
            # thread (xem docstring _coerce_ai_payload).
            bad_count += 1
            now = time.monotonic()
            if now - last_warn >= 5.0:
                print(f"[carlogd] CANH BAO: {bad_count} goi AI sai kieu du lieu tu thi sinh "
                      f"bi bo qua tu lan canh bao truoc (kiem tra lai code doi ban) - vi du "
                      f"goi vua roi: {raw[:200]!r}", file=sys.stderr)
                last_warn = now
                bad_count = 0
            continue
        with STATE.lock:
            STATE.latest_ai = parsed


# ---------------------------------------------------------------------------
#  2) Dieu khien tu marshal - Unix domain socket, PHAN QUYEN o cap file he
#     dieu hanh (xem provision/README.md): chi user/group "carlog" doc/ghi
#     duoc, tai khoan SSH cua thi sinh KHONG nam trong group do nen khong
#     goi duoc lenh startrun/stoprun du co doc duoc code carlogd.py.
# ---------------------------------------------------------------------------
def control_server():
    sock_path = config.CONTROL_SOCKET
    srv = None
    if hasattr(socket, "AF_UNIX"):
        try:
            os.unlink(sock_path)
        except FileNotFoundError:
            pass
        try:
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(sock_path)
            os.chmod(sock_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP)  # 0660
        except OSError as e:
            print(f"[carlogd] CANH BAO: khong bind duoc Unix socket '{sock_path}' ({e}) -> "
                  f"chuyen sang TCP loopback (chi de demo/dev tren Windows).")
            srv = None
    if srv is not None:
        srv.listen(4)
        print(f"[carlogd] dieu khien marshal tai {sock_path} (0660 - chi group 'carlog')")
    else:
        # May nay khong ho tro AF_UNIX that su (vd Python ban cai tu Microsoft
        # Store tren Windows) - CHI dung TCP loopback nay de demo/dev, KHONG
        # dung cho thi dau that: khong co phan quyen he dieu hanh nhu Unix
        # socket 0660, bat ky ai tren cung may deu goi duoc START/STOP.
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", config.CONTROL_TCP_FALLBACK_PORT))
        srv.listen(4)
        print(f"[carlogd] dieu khien marshal qua TCP 127.0.0.1:{config.CONTROL_TCP_FALLBACK_PORT} "
              f"(fallback demo Windows - KHONG dung cho thi dau that)")

    while True:
        conn, _ = srv.accept()
        try:
            line = conn.recv(256).decode("utf-8", "ignore").strip()
            parts = line.split()
            if not parts:
                conn.sendall(b"ERR: rong\n")
            elif parts[0] == "START" and len(parts) == 2 and parts[1].isdigit():
                run_id = int(parts[1])
                next_seq = _start_run_locked(run_id)
                conn.sendall(f"OK: bat dau run_id={run_id} tu sequence_no={next_seq}\n".encode())
            elif parts[0] == "STOP":
                with STATE.lock:
                    STATE.run_id = None
                conn.sendall(b"OK: da dung\n")
            elif parts[0] == "STATUS":
                with STATE.lock:
                    msg = f"run_id={STATE.run_id} next_seq={STATE.next_seq} team_id={STATE.team_id}\n"
                conn.sendall(msg.encode())
            else:
                conn.sendall(b"ERR: lenh khong hop le (START <id> | STOP | STATUS)\n")
        except Exception as e:
            try:
                conn.sendall(f"ERR: {e}\n".encode())
            except Exception:
                pass
        finally:
            conn.close()


def resume_sequence_for(run_id):
    """Neu run_id nay da tung gui mot phan (service bi restart giua chung -
    vd Pi mat dien, marshal go nham START lai), tiep tuc dung tu sequence_no
    cu - KHONG bao gio quay lai 0 cho run_id da co du lieu (giu dung khoa
    chinh (run_id, sequence_no) o bang logs, tranh ON CONFLICT DO NOTHING
    am tham nuot goi moi giong het goi cu)."""
    try:
        with open(config.STATE_FILE) as f:
            data = json.load(f)
        if data.get("run_id") == run_id:
            seq = data.get("next_seq", 0)
            print(f"[carlogd] resume_sequence_for({run_id}): tiep tuc tu sequence_no={seq}")
            return seq
    except Exception:
        pass
    print(f"[carlogd] resume_sequence_for({run_id}): run_id moi, bat dau tu sequence_no=0")
    return 0


def _start_run_locked(run_id):
    """Dung chung boi control_server (lenh tay tu carlogctl.py) VA api_poll_loop
    (tu dong theo nut bam tren web) - cung 1 logic START, tranh viet 2 lan."""
    next_seq = resume_sequence_for(run_id)
    with STATE.lock:
        STATE.run_id = run_id
        STATE.next_seq = next_seq
    return next_seq


# ---------------------------------------------------------------------------
#  2b) TUY CHON: tu dong theo lenh "Bat dau ghi log" marshal bam tren web,
#      thay vi phai go tay carlogctl.py start <run_id> tren xe. CHI bat khi
#      config.API_BASE + config.API_KEY duoc dat (mac dinh TAT - giu nguyen
#      hanh vi go tay).
#
#      KHONG dung tai khoan admin/viewer (dang nhap JWT) - dung 1 chia khoa
#      RIENG cho DUNG doi nay (header X-Car-Api-Key, xem
#      teams.car_api_key trong init_basic_int.txt). Khac voi tai khoan
#      viewer (doc duoc MOI doi qua GET /api/runs, /api/runs/{id}/logs...),
#      endpoint /api/teams/{id}/car-status CHI tra dung 2 gia tri toi thieu
#      (run_id dang chay + co duoc duyet bat dau chua) cho DUNG id trong
#      URL - du chia khoa nay bi lo (thi sinh doc duoc trong config.py tren
#      xe cua chinh doi ho), ho cung khong the xem duoc du lieu/telemetry
#      cua doi khac.
#
#      CO CHE CU (dang nhap bang tai khoan role 'viewer' qua /api/auth/login
#      roi goi GET /api/teams/{id}/runs) van GIU LAI o duoi day
#      (_api_login/_api_get_team_runs) de tham khao/dung lai neu can, nhung
#      KHONG con duoc api_poll_loop() goi nua - danh doi la lo qua tai
#      khoan viewer se xem duoc du lieu CA doi khac (xem thao luan trong
#      chat), nen mac dinh chuyen han sang _api_get_car_status() ben duoi.
# ---------------------------------------------------------------------------
_api_token = None
_api_token_exp = 0.0


def _api_login():
    """CO CHE CU - khong con duoc goi mac dinh, giu lai tham khao (xem ghi
    chu o tren). Dang nhap bang tai khoan role 'viewer' (API_USER/
    API_PASSWORD trong config.py)."""
    global _api_token, _api_token_exp
    body = json.dumps({"username": config.API_USER, "password": config.API_PASSWORD}).encode("utf-8")
    req = urllib.request.Request(
        config.API_BASE.rstrip("/") + "/api/auth/login", data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    _api_token = data["token"]
    # Dang nhap lai som hon 5 phut truoc khi het han, phong tru sai lech dong ho.
    _api_token_exp = time.time() + max(60, (int(data.get("expiresInMinutes", 60)) - 5) * 60)


def _api_get_team_runs():
    """CO CHE CU - khong con duoc goi mac dinh, giu lai tham khao (xem ghi
    chu o tren). Tra ve TOAN BO luot cua 1 doi qua tai khoan viewer (doc
    duoc ca luot cua doi khac neu goi endpoint khac - xem CarStatusController
    de biet vi sao doi sang co che moi)."""
    global _api_token
    if _api_token is None or time.time() >= _api_token_exp:
        _api_login()
    req = urllib.request.Request(
        f"{config.API_BASE.rstrip('/')}/api/teams/{config.TEAM_ID}/runs",
        headers={"Authorization": f"Bearer {_api_token}"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _api_get_car_status():
    req = urllib.request.Request(
        f"{config.API_BASE.rstrip('/')}/api/teams/{config.TEAM_ID}/car-status",
        headers={"X-Car-Api-Key": config.API_KEY})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_poll_loop():
    if not config.API_BASE:
        return  # tinh nang TAT (mac dinh) - khong lam gi ca, khong goi mang.
    print(f"[carlogd] dang theo doi nut 'Bat dau ghi log' tren web qua {config.API_BASE} "
          f"moi {config.API_POLL_INTERVAL_S}s (team_id={config.TEAM_ID})")
    while True:
        try:
            status = _api_get_car_status()
            run_id = status.get("runId")
            requested = status.get("carStartRequestedAt")
            active_run_id = run_id if (run_id is not None and requested) else None
            with STATE.lock:
                cur = STATE.run_id
            if active_run_id is not None and active_run_id != cur:
                next_seq = _start_run_locked(active_run_id)
                print(f"[carlogd] (tu dong theo web) bat dau run_id={active_run_id} "
                      f"tu sequence_no={next_seq}")
            elif active_run_id is None and cur is not None:
                with STATE.lock:
                    STATE.run_id = None
                print("[carlogd] (tu dong theo web) da dung (luot khong con 'running')")
        except urllib.error.HTTPError as e:
            print(f"[carlogd] CANH BAO: web tu choi car-status (HTTP {e.code} - kiem tra "
                  f"CARLOGD_API_KEY/CARLOGD_TEAM_ID co dung khong), thu lai sau.", file=sys.stderr)
        except (urllib.error.URLError, KeyError, ValueError) as e:
            print(f"[carlogd] CANH BAO: theo doi web loi ({e}), thu lai sau.", file=sys.stderr)
        time.sleep(config.API_POLL_INTERVAL_S)


# ---------------------------------------------------------------------------
#  3) Vong lap gui chinh - nhip CO DINH 10ms, DAY LA NOI DUY NHAT "biet" ve
#     thoi gian va la noi DUY NHAT ghi run_id/team_id/sequence_no vao goi tin
#     that gui di. Import THANG protocol.py that cua du an (khong viet lai
#     schema o day) - xem PROTOCOL_DIR trong config.py.
# ---------------------------------------------------------------------------
if not os.path.isfile(os.path.join(config.PROTOCOL_DIR, "protocol.py")):
    print(f"[carlogd] LOI: khong tim thay protocol.py trong CARLOGD_PROTOCOL_DIR="
          f"'{config.PROTOCOL_DIR}'.\n"
          f"  -> Chua dat bien moi truong CARLOGD_PROTOCOL_DIR dung duong dan toi "
          f"Car/simulator (mac dinh la duong dan Linux '/opt/hackathon/Car/simulator', "
          f"khong ton tai tren Windows). Dung run_carlogd_demo.ps1 de tu dat san bien nay, "
          f"hoac tu $env:CARLOGD_PROTOCOL_DIR='duong/dan/toi/Car/simulator' truoc khi chay.")
    sys.exit(1)
sys.path.insert(0, config.PROTOCOL_DIR)
import protocol  # noqa: E402  (import sau khi them sys.path - co y)

SAFE_DEFAULT_AI = {
    "speed_kmh": 0.0, "steering_deg": 0.0, "lane_offset_cm": 0.0,
    "obstacle": True, "confidence": 0.0,
}


def sender_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_addr = (config.INGEST_HOST, config.INGEST_PORT)
    interval_s = config.TELEMETRY_INTERVAL_MS / 1000.0
    deadline = time.perf_counter()
    stats = {"sent": 0, "no_run": 0, "encode_err": 0}
    last_print = time.monotonic()

    while True:
        deadline += interval_s
        remain = deadline - time.perf_counter()
        if remain > 0:
            time.sleep(remain)
        else:
            deadline = time.perf_counter()  # tut lai qua xa (may bi treo) - dat lai moc, khong don don

        with STATE.lock:
            run_id = STATE.run_id
            team_id = STATE.team_id
            if run_id is None:
                stats["no_run"] += 1
                continue  # chua co run nao dang mo - im lang, KHONG tieu sequence_no
            seq = STATE.next_seq
            STATE.next_seq += 1
            ai = dict(STATE.latest_ai) if STATE.latest_ai is not None else dict(SAFE_DEFAULT_AI)

        car_timestamp = int(time.time() * 1000)  # gio thuc, DA dong bo NTP qua systemd-timesyncd
        try:
            payload = protocol.encode(run_id, team_id, seq, car_timestamp, ai)
        except Exception as e:
            stats["encode_err"] += 1
            print(f"[carlogd] LOI dong goi run_id={run_id} seq={seq}: {e}", file=sys.stderr)
            continue

        try:
            sock.sendto(payload, server_addr)
            stats["sent"] += 1
        except OSError as e:
            print(f"[carlogd] sendto loi (bo qua goi nay): {e}", file=sys.stderr)

        if seq % config.STATE_PERSIST_EVERY == 0:
            STATE.persist()

        now = time.monotonic()
        if now - last_print >= 5.0:
            print(f"[carlogd] da_gui={stats['sent']} khong_co_run={stats['no_run']} "
                  f"loi_dong_goi={stats['encode_err']} run_id_hientai={run_id}")
            last_print = now


def main():
    STATE.load_persisted()
    threading.Thread(target=ai_submit_server, daemon=True).start()
    threading.Thread(target=control_server, daemon=True).start()
    threading.Thread(target=api_poll_loop, daemon=True).start()
    print("[carlogd] san sang. Marshal dung carlogctl.py (hoac nut 'Bat dau ghi log' "
          "tren web, neu da cau hinh CARLOGD_API_BASE) de START/STOP mot luot chay.")
    sender_loop()


if __name__ == "__main__":
    main()
