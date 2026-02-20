import socket
import threading
import select

# Configuration
LOCAL_HOST = '0.0.0.0'
LOCAL_PORT = 8080

# The address of Node B (The next hop proxy)
# You need to update this IP to the actual IP of Node B visible to Node A
REMOTE_PROXY_HOST = '172.20.0.11'  # REPLACE WITH NODE B IP
REMOTE_PROXY_PORT = 9090           # Port Node B is listening on

def handle_client(client_socket):
    try:
        # Connect to Node B
        remote_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        remote_socket.connect((REMOTE_PROXY_HOST, REMOTE_PROXY_PORT))

        # This is where you can inject custom logic for the initial handshake if needed
        # For a transparent chain, we often just start piping data directly
        # or parse the first headers to decide what to do.

        exchange_loop(client_socket, remote_socket)

    except Exception as e:
        print(f"[!] Error handling client: {e}")
    finally:
        client_socket.close()
        if 'remote_socket' in locals():
            remote_socket.close()

def exchange_loop(client, remote):
    """
    Forwards data between client and remote proxy.
    Implement your custom packet modification logic here.
    """
    while True:
        # Wait for data from either side
        r, w, e = select.select([client, remote], [], [])

        if client in r:
            data = client.recv(4096)
            if not data: break
            
            # --- CUSTOM LOGIC HOOK (A -> B) ---
            # Modify 'data' here before sending to Node B
            print(f"[A->B] Forwarding {len(data)} bytes")
            # ----------------------------------
            
            remote.sendall(data)

        if remote in r:
            data = remote.recv(4096)
            if not data: break
            
            # --- CUSTOM LOGIC HOOK (B -> A) ---
            # Modify 'data' here before sending back to Client
            print(f"[B->A] Forwarding {len(data)} bytes")
            # ----------------------------------
            
            client.sendall(data)

def start_proxy():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((LOCAL_HOST, LOCAL_PORT))
    server.listen(5)
    print(f"[*] Proxy A listening on {LOCAL_HOST}:{LOCAL_PORT}")
    print(f"[*] Forwarding to {REMOTE_PROXY_HOST}:{REMOTE_PROXY_PORT}")
    print(f"[*] Set your env vars: export http_proxy=http://127.0.0.1:{LOCAL_PORT} https_proxy=http://127.0.0.1:{LOCAL_PORT}")

    while True:
        client_sock, addr = server.accept()
        print(f"[*] Accepted connection from {addr[0]}:{addr[1]}")
        client_handler = threading.Thread(target=handle_client, args=(client_sock,))
        client_handler.start()

if __name__ == '__main__':
    start_proxy()
