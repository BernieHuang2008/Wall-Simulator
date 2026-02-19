import threading
from scapy.all import sniff, IP
import logging
import netifaces

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Wall_Main")

def process_packet(packet):
    # For sniff(), 'packet' is already a Scapy packet.
    if IP in packet:
        ip_layer = packet[IP]
        print(f"Intercepted: {ip_layer.src} -> {ip_layer.dst}")

def start_sniffing():
    logger.info("Starting sniffer...")
    try:
        # 自动侦测所有非回环网卡 (如 eth0, eth1)
        interfaces = netifaces.interfaces()
        ifaces = [i for i in interfaces if i != 'lo']
        sniff(iface=ifaces, prn=process_packet, filter="ip", store=False)
    except Exception as e:
        logger.error(f"Error sniffing: {e}")


if __name__ == '__main__':
    sniffer_thread = threading.Thread(target=start_sniffing, daemon=True)
    sniffer_thread.start()
