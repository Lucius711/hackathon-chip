"""
Vi du toi thieu: gui 1 ket qua AI toi carlogd. Copy ham send_ai_result() vao
vong lap lai xe cua ban, goi no moi khi co ket qua suy luan moi.
"""
import json
import socket

_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
_CARLOGD_ADDR = ("127.0.0.1", 8765)  # doi port neu BTC thong bao khac


def send_ai_result(speed_kmh, steering_deg, lane_offset_cm, obstacle, confidence, progress=None):
    payload = {
        "speed_kmh": speed_kmh,
        "steering_deg": steering_deg,
        "lane_offset_cm": lane_offset_cm,
        "obstacle": obstacle,
        "confidence": confidence,
    }
    if progress is not None:
        payload["progress"] = progress
    _sock.sendto(json.dumps(payload).encode("utf-8"), _CARLOGD_ADDR)


if __name__ == "__main__":
    # Demo: gui thu 1 goi, ban thay bang vong lap lai xe that cua minh.
    send_ai_result(speed_kmh=25.0, steering_deg=-8.5, lane_offset_cm=3.2,
                    obstacle=False, confidence=0.92)
    print("da gui 1 goi ket qua AI mau toi carlogd.")
