#!/bin/bash
# Vi du bang shell/netcat - dung khi ngon ngu ban chon khong tien viet socket
# (vd goi tu 1 script Bash gian hoac test nhanh tu dong lenh). Can co `nc`
# (netcat) tren Raspberry Pi OS - thuong co san, neu chua: sudo apt install netcat-openbsd
echo -n '{"speed_kmh":25.0,"steering_deg":-8.5,"lane_offset_cm":3.2,"obstacle":false,"confidence":0.92}' \
    | nc -u -w0 127.0.0.1 8765
echo "da gui 1 goi ket qua AI mau toi carlogd."
