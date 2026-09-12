"""
Cau hinh carlogd - moi Raspberry Pi (moi doi) chi sua file nay MOT LAN khi
lap rap xe. Doc gia tri tu bien moi truong neu co (giong config.py cua
Car/simulator), khong thi dung mac dinh o day.
"""
import os

# Co dinh cho tung xe - id doi (trung teams.id trong DB). Day la truong DUY
# NHAT ve danh tinh ma carlogd tin tuong dua vao file cau hinh; run_id thi
# PHAI qua carlogctl.py START (marshal go) chu khong doc tu day, vi run_id
# doi theo tung luot con team_id thi co dinh theo xe.
TEAM_ID = int(os.environ.get("CARLOGD_TEAM_ID", "0"))

# Dia chi ingest_server.py THAT tren mang thi dau.
INGEST_HOST = os.environ.get("CARLOGD_INGEST_HOST", "10.0.0.1")
INGEST_PORT = int(os.environ.get("CARLOGD_INGEST_PORT", "9999"))

# Cong UDP NOI BO (127.0.0.1) de code cua thi sinh gui ket qua AI toi - MO
# cho moi user tren may, day la cong "cong khai noi bo" duy nhat thi sinh
# can biet.
LOCAL_SUBMIT_PORT = int(os.environ.get("CARLOGD_LOCAL_PORT", "8765"))

# Unix socket dieu khien START/STOP/STATUS - CHI marshal dung (xem
# provision/README.md ve phan quyen 0660 + group). Tren Pi that (Linux) day la
# hang rao bao mat that su. Neu may khong ho tro AF_UNIX (mot so ban dung
# Python tren Windows, vd ban cai tu Microsoft Store) carlogd/carlogctl se tu
# chuyen sang TCP loopback o cong duoi day - CHI dung de demo/dev tren
# Windows, KHONG co phan quyen he dieu hanh nhu Unix socket.
CONTROL_SOCKET = os.environ.get("CARLOGD_CONTROL_SOCKET", "/run/carlogd/control.sock")
CONTROL_TCP_FALLBACK_PORT = int(os.environ.get("CARLOGD_CONTROL_TCP_PORT", "8766"))

# File luu (run_id, next_seq) de song sot qua restart/mat dien giua luot.
STATE_FILE = os.environ.get("CARLOGD_STATE_FILE", "/var/lib/carlogd/state.json")
STATE_PERSIST_EVERY = 50  # luu xuong dia moi 50 goi (~0.5s) - can bang do ben flash the SD

# Nhip gui chuan - PHAI khop config mac dinh cua ingest_server.py/protocol.py.
TELEMETRY_INTERVAL_MS = 10

# Thu muc chua protocol.py THAT cua du an (Car/simulator) - carlogd import
# thang tu day, khong tu viet lai schema.
PROTOCOL_DIR = os.environ.get("CARLOGD_PROTOCOL_DIR", "/opt/hackathon/Car/simulator")

# ---------------------------------------------------------------------------
# TUY CHON: xe tu dong bat dau ghi log khi marshal bam nut "Bat dau ghi log"
# tren web admin, THAY VI phai go tay carlogctl.py start <run_id> tren xe.
# Van la marshal chu dong bam (khong tu dong ngay luc mo luot tren web) -
# chi bot buoc go lenh, khong bo qua buoc xac nhan xe san sang.
#
# De TAT tinh nang nay (mac dinh, giu nguyen hanh vi cu - chi dieu khien qua
# carlogctl.py), de trong CARLOGD_API_BASE.
# De BAT (co che DANG DUNG - carlogd.py#_api_get_car_status): dat 3 bien
# duoi day, vi du:
#   CARLOGD_API_BASE=http://10.0.0.1:8080
#   CARLOGD_API_KEY=<chia khoa RIENG cua doi nay - xem teams.car_api_key
#                     trong init_basic_int.txt, KHAC voi tai khoan
#                     admin/viewer dang nhap web va KHAC username/mat khau
#                     WiFi. Chi cho phep doc trang thai cua DUNG doi nay,
#                     khong doc duoc du lieu doi khac du bi lo.>
API_BASE = os.environ.get("CARLOGD_API_BASE", "")
API_KEY = os.environ.get("CARLOGD_API_KEY", "")
API_POLL_INTERVAL_S = float(os.environ.get("CARLOGD_API_POLL_INTERVAL_S", "1.0"))

# CO CHE CU (dang nhap tai khoan role 'viewer' qua /api/auth/login) - GIU LAI
# de tham khao/dung lai neu can (xem carlogd.py#_api_login), nhung
# api_poll_loop() KHONG con goi mac dinh nua (doi sang API_KEY o tren, vi ly
# do cong bang - xem ghi chu trong carlogd.py).
API_USER = os.environ.get("CARLOGD_API_USER", "")
API_PASSWORD = os.environ.get("CARLOGD_API_PASSWORD", "")
