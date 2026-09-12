/*
 * Vi du toi thieu bang C: gui 1 ket qua AI toi carlogd qua UDP noi bo.
 * Bien dich: gcc -O2 -o send_result_example send_result_example.c
 * Copy ham send_ai_result() vao vong lap lai xe cua ban.
 */
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>

static void send_ai_result(double speed_kmh, double steering_deg, double lane_offset_cm,
                            int obstacle, double confidence)
{
    static int sock = -1;
    static struct sockaddr_in addr;
    if (sock < 0) {
        sock = socket(AF_INET, SOCK_DGRAM, 0);
        memset(&addr, 0, sizeof(addr));
        addr.sin_family = AF_INET;
        addr.sin_port = htons(8765); // doi port neu BTC thong bao khac
        inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);
    }

    char buf[256];
    int len = snprintf(buf, sizeof(buf),
        "{\"speed_kmh\":%.2f,\"steering_deg\":%.2f,\"lane_offset_cm\":%.2f,"
        "\"obstacle\":%s,\"confidence\":%.3f}",
        speed_kmh, steering_deg, lane_offset_cm, obstacle ? "true" : "false", confidence);
    sendto(sock, buf, len, 0, (struct sockaddr *)&addr, sizeof(addr));
}

int main(void)
{
    send_ai_result(25.0, -8.5, 3.2, 0, 0.92);
    printf("da gui 1 goi ket qua AI mau toi carlogd.\n");
    return 0;
}
