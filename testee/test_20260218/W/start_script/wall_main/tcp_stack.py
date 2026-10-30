from scapy.all import TCP, IP

stacks = dict()

def _renew_stack(KEY, packet):
    stacks[KEY] = {
        "packets": [packet],
        "state": "alive",
        "broken": False
    }

def packet_in(packet):
    if TCP in packet[IP]:
        tcp_layer = packet[IP][TCP]
        KEY = (packet[IP].src, tcp_layer.sport, packet[IP].dst, tcp_layer.dport)
        
        if 'S' in tcp_layer.flags:  # SYN packet, start of new connection
            if KEY in stacks:
                match stacks[KEY]["state"]:
                    case "alive":
                        raise Exception(f"SYN packet for existing & alive connection {KEY}")
                    case "closed":
                        # just restart the stack for new connection
                        _renew_stack(KEY, packet)
                    case _:
                        raise Exception(f"Unexpected state {stacks[KEY]['state']} for stack {KEY}")
            else:
                _renew_stack(KEY, packet)

        elif 'F' in tcp_layer.flags or 'R' in tcp_layer.flags:  # FIN or RST packet, end of connection
            if KEY in stacks:
                stacks[KEY]["packets"].append(packet)  # Add FIN/RST to stack
                stacks[KEY]["state"] = "closed"
            else:
                raise Exception(f"FIN/RST packet for non-existing connection {KEY}")

        else:  # Other packets in the connection
            if KEY in stacks and stacks[KEY]["state"] == "alive":
                stacks[KEY]["packets"].append(packet)
            else:
                # broken (headless) packet
                _renew_stack(KEY, packet)
                stacks[KEY]["broken"] = True

        return stacks[KEY]

    else:
        return None

