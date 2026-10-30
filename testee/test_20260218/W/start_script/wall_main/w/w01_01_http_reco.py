"""
[w] w01_01_http_reco: HTTP traffic recognition

目标
===================================
识别基于 TCP 的 HTTP 流量 (HTTP1.0 / HTTP1.1 / HTTP2.0)，……TODO……。

算法
===================================
  - 维护一个 http_stack，根据TCP包的序列号（seq）顺序拼接TCP payload，将流式TCP数据组装为完整的文本数据。
  - 搜索 HTTP 协议特征：
    1. 在 http_stack 的 contents 中搜索 HTTP header 和 body 的分隔符 "\r\n\r\n"。
    2. 对于每个找到的 "\r\n\r\n"，向前搜索 HTTP version。（搜索步长为每次一个 "\r\n" 换行符，分割每个 header 行）
    3. 如果找到 HTTP version，则进一步验证这是一个 HTTP 请求。符合 HTTP 格式后，……TODO……，然后丢弃已处理的部分。
    
"""

import re
from scapy.all import TCP, IP
from utils import *

def w01_01_http_reco(packet, tcp_stack):
    match (tcp_stack is None) + (TCP not in packet):
        case 2:
            return BYPASS # not a TCP packet, its not our intended customer
        case 1:
            raise Exception("Unexpected state: stack and packet state unmatch")

    # init http_stack if not exist
    tcp_layer = packet[IP][TCP]
    if "http_stack" not in tcp_stack:
        tcp_stack["http_stack"] = {
            "contents": b"",
            "last_seq": tcp_layer.seq
        }

    http_stack = tcp_stack["http_stack"]

    # check if the packet is sequenced
    if tcp_layer.seq != http_stack["last_seq"]:
        return BYPASS   # out of order

    # update last_seq
    http_stack["last_seq"] = tcp_layer.seq + len(tcp_layer.payload)
    http_stack["last_seq"] %= 2**32
    # concat stream payload
    tcp_layer.payload.show(dump=True)
    tcp_stack["http_stack"]["contents"] += bytes(tcp_layer.payload)

    # check for HTTP msg
    # 算法: 
    #   - 首先在contents中搜索 "\r\n\r\n" 。这个是HTTP header和body的分隔符。
    #   - 对于每一处 "\r\n\r\n"，都向前搜索HTTP version 。每次搜索寻找"\r\n"换行符，该换行符用于分割每个header行。
    #   - 如果找到了HTTP version，则进一步验证这是一个HTTP请求。符合HTTP格式后，……TODO……，然后丢弃已处理的部分。
    #   - 如果到字符串开头都没有找到HTTP version 或者不符合格式，则认为这个 "\r\n\r\n" 处不是一个有效的HTTP消息分隔符，丢弃已处理的部分，并继续搜索下一个 "\r\n\r\n"。

    dbcrlf_index = http_stack["contents"].find(b"\r\n\r\n")
    while dbcrlf_index != -1:
        possible_header, http_stack["contents"] = http_stack["contents"].split(b"\r\n\r\n", 1)

        # search for HTTP version in possible_header
        header_lines = possible_header.split(b"\r\n")
        for i in range(len(header_lines)-1, -1, -1):    # search backwards for HTTP version
            line = header_lines[i]

            if line.endswith(b" HTTP/1.1") or line.endswith(b" HTTP/1.0") or line.endswith(b" HTTP/2.0"):
                # found HTTP version, now verify the HTTP format
                # 1. "method URL version"
                parts = line.split(b" ")
                if len(parts) < 3:
                    continue
                # 2. method[-3] near end of the line should be one of GET/POST/PUT/DELETE/HEAD/OPTIONS/PATCH
                if re.search(rb"(GET|POST|PUT|DELETE|HEAD|OPTIONS|PATCH)$", parts[-3]) is None:
                    continue

                # TODO: GOT an HTTP request, now do something with it, e.g. print it or store it for later use
                return "HTTP found"

                break # inner "for loop"

        dbcrlf_index = http_stack["contents"].find(b"\r\n\r\n")

    
    return BYPASS # no HTTP msg found



if __name__ == "__main__":
    # test code: simulate fragmented TCP packets
    from scapy.all import Ether, IP, TCP, Raw

    print("--- Test Case: Fragmented HTTP Request ---")

    # 1. Prepare HTTP Request
    http_payload_full = b"previous contentsGET /index.html HTTP/1.1\r\nHost: example.com\r\n\r\nsome body in http\nand some other contents"
    
    # Split payload into 3 chunks
    
    chunk1 = http_payload_full[:30]
    chunk2 = http_payload_full[30:50]
    chunk3 = http_payload_full[50:]

    # 2. Create Packets
    base_seq = 1000
    
    # Packets
    pkt1 = IP(src="192.168.1.1", dst="192.168.1.2") / TCP(sport=12345, dport=80, seq=base_seq) / Raw(load=chunk1)
    pkt2 = IP(src="192.168.1.1", dst="192.168.1.2") / TCP(sport=12345, dport=80, seq=base_seq + len(chunk1)) / Raw(load=chunk2)
    pkt3 = IP(src="192.168.1.1", dst="192.168.1.2") / TCP(sport=12345, dport=80, seq=base_seq + len(chunk1) + len(chunk2)) / Raw(load=chunk3)

    packets = [pkt1, pkt2, pkt3]
    # packets = [pkt1, pkt2]

    # 3. Initialize TCP Stack
    # In real usage, tcp_stack is passed by main.py which manages sessions.
    # Here we mock it.
    tcp_stack = {} 

    # 4. Feed packets to w01_01_http_reco
    for i, pkt in enumerate(packets):
        print(f"\nProcessing Packet {i+1} (len={len(pkt[TCP].payload)}):")
        # Ensure we initialize the session entry if not present (simulating main.py logic slightly)
        # Note: The function expects `tcp_stack` to be the *session* dictionary, not the global stack dict.
        # Let's adjust based on the function signature: def w01_01_http_reco(packet, tcp_stack):
        # inspecting main.py: stack = tcp_stack.packet_in(packet) -> returns the session dict
        # So we should pass a dictionary that represents the session.
        
        # We'll use a single dict to represent the session state
        result = w01_01_http_reco(pkt, tcp_stack)
        print(f"Result: {result}")
        if "http_stack" in tcp_stack:
            print(f"Current Reassembled Buffer: {tcp_stack['http_stack']['contents']}")

