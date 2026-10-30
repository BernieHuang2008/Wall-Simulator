import threading
from scapy.all import sniff, Packet, IP, TCP
import logging
import w
import tcp_stack

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("Wall_Main")


def process_packet(packet: Packet):
    # For sniff(), 'packet' is already a Scapy packet.
    if IP in packet:
        ip_layer = packet[IP]
        logger.info(f"Intercepted: {ip_layer.src} -> {ip_layer.dst}")

        # --- CUSTOM LOGIC HOOK ---
        
        # I. add to TCP stack if is TCP packet
        if TCP in ip_layer:
            stack = tcp_stack.packet_in(packet)
        else:
            stack = None
        
        # II. apply wall detects rules
        w.w01_01_http_reco(packet, stack)

        # -------------------------


def start_sniffing():
    logger.info("Starting sniffer...")
    ifaces = ["eth_wallsim"]
    sniff(
        iface=ifaces,
        prn=lambda packet: threading.Thread(
            target=process_packet, args=(packet,), daemon=True
        ).start(),
        filter=None,
        store=False,
        promisc=True,
    )
    logger.info("Sniffer stopped.")


if __name__ == "__main__":
    sniffer_thread = threading.Thread(target=start_sniffing, daemon=True)
    sniffer_thread.start()

    try:
        # Keep the main thread alive so the daemon thread can run
        sniffer_thread.join()
    except KeyboardInterrupt:
        logger.info("Stopping sniffer...")
