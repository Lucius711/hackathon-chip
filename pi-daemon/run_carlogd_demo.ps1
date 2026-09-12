# Chay carlogd.py cho demo tren may Windows (khong phai Pi that) — dat san cac
# bien moi truong roi khoi dong, khong can go tay $env:... moi lan mo terminal.
#
# Dung:
#   cd D:\Hackathon\hackathon-chip-logic\pi-daemon
#   .\run_carlogd_demo.ps1
#
# Doi TEAM_ID / INGEST_HOST / INGEST_PORT o duoi neu demo doi khac hoac
# ingest_server.py chay o may/cong khac.

$env:CARLOGD_TEAM_ID = "1"
$env:CARLOGD_INGEST_HOST = "127.0.0.1"
$env:CARLOGD_INGEST_PORT = "9999"
$env:CARLOGD_PROTOCOL_DIR = "D:\Hackathon\hackathon-server\Car\simulator"

# STATE_FILE/CONTROL_SOCKET mac dinh trong config.py la duong dan Linux
# (/var/lib/carlogd/..., /run/carlogd/...) - khong ton tai tren Windows, phai
# tro sang 1 thu muc that o day va tu tao truoc khi carlogd.py mo file.
$demoDir = Join-Path $PSScriptRoot "_demo_state"
New-Item -ItemType Directory -Force -Path $demoDir | Out-Null
$env:CARLOGD_STATE_FILE = Join-Path $demoDir "state.json"
$env:CARLOGD_CONTROL_SOCKET = Join-Path $demoDir "control.sock"

# TUY CHON: bo comment 2 dong duoi de xe TU DONG bat/dung ghi log theo nut
# "Bat dau ghi log" tren web (khong con phai go carlogctl.py start tay nua).
# CARLOGD_API_KEY la chia khoa RIENG cua doi nay (cot teams.car_api_key trong
# init_basic_int.txt - sinh bang SQL, vd:
#   UPDATE teams SET car_api_key = md5(random()::text || clock_timestamp()::text) WHERE id = 1;
# ) - KHONG phai tai khoan admin/viewer dang nhap web, chi doc duoc trang
# thai cua DUNG doi nay du bi lo.
# $env:CARLOGD_API_BASE = "http://localhost:8080"
# $env:CARLOGD_API_KEY = "CHIA_KHOA_CUA_DOI_NAY"

Write-Host "[run_carlogd_demo] TEAM_ID=$env:CARLOGD_TEAM_ID INGEST=$env:CARLOGD_INGEST_HOST`:$env:CARLOGD_INGEST_PORT PROTOCOL_DIR=$env:CARLOGD_PROTOCOL_DIR STATE_FILE=$env:CARLOGD_STATE_FILE"

python carlogd.py
