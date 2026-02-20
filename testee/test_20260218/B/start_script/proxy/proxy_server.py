import socket
import threading
import select

# Configuration
BIND_HOST = '0.0.0.0'
BIND_PORT = 9090  # The port Node B listens on

def handle_client(client_socket):
    target_socket = None
    try:
        # 1. Read the initial request from the client (Node A's proxy script)
        request = client_socket.recv(4096)
        if not request:
            return

        # print(f"[*] Received request:\n{request.decode('utf-8', errors='ignore')}")

        # 2. Parse the request to find the destination
        # Format usually: "CONNECT host:port HTTP/1.1" or "GET http://host:port/..."
        first_line = request.split(b'\n')[0].decode('utf-8')
        method, url, proto = first_line.split()

        if method == 'CONNECT':
            # HTTPS Tunneling
            host, port = url.split(':')
            port = int(port)
            
            # Connect to actual destination
            target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_socket.connect((host, port))
            
            # Send 200 Connection Established back to client (Node A)
            client_socket.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            
            # Now bridge the connection for encrypted traffic
            bridge_connections(client_socket, target_socket)
            
        else:
            # HTTP Proxying (GET, POST, etc.)
            # We need to extract the host/port from the URL
            # URL format: http://www.google.com/path
            
            if '://' in url:
                url = url.split('://', 1)[1]
            path_start = url.find('/')
            if path_start == -1:
                path_start = len(url)
            
            host_port = url[:path_start]
            path = url[path_start:]
            
            if ':' in host_port:
                host, port = host_port.split(':')
                port = int(port)
            else:
                host = host_port
                port = 80

            # Connect to actual destination
            target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_socket.connect((host, port))
            
            # Rewrite the request line to be relative (standard for origin servers)
            # Original: GET http://www.google.com/path HTTP/1.1
            # New:      GET /path HTTP/1.1
            # We also need to ensure the Host header is present, but usually clients send it.
            
            # Find the path in the original request line
            # Reconstruct the request line with relative path
            new_first_line = f"{method} {path} {proto}"
            
            # Replace the first line in the original request buffer
            # Note: This is a simple binary replacement, might be brittle if buffer boundaries are odd
            # but works for standard headers in one packet.
            
            request_lines = request.split(b'\r\n')
            request_lines[0] = new_first_line.encode('utf-8')
            new_request = b'\r\n'.join(request_lines)
            
            # Forward the modified request to the destination
            target_socket.sendall(new_request)
            
            # Bridge the rest of the connection
            bridge_connections(client_socket, target_socket)

    except Exception as e:
        # print(f"[!] Error handling request: {e}")
        pass
    finally:
        if client_socket: client_socket.close()
        if target_socket: target_socket.close()

def bridge_connections(client, target):
    """
    Bi-directional bridge between client (Node A) and target (Internet).
    """
    inputs = [client, target]
    while True:
        try:
            readable, _, _ = select.select(inputs, [], [], 10)
            if not readable: break 

            for sock in readable:
                data = sock.recv(4096)
                if not data: return # connection closed

                if sock is client:
                    # Modify Traffic A -> Internet if needed here
                    target.sendall(data)
                else:
                    # Modify Traffic Internet -> A if needed here
                    client.sendall(data)
        except Exception:
            break

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server.bind((BIND_HOST, BIND_PORT))
        server.listen(50)
        print(f"[*] Proxy Server B listening on {BIND_HOST}:{BIND_PORT}")
        
        while True:
            client_sock, addr = server.accept()
            # print(f"[*] Connection from {addr[0]}:{addr[1]}")
            client_handler = threading.Thread(target=handle_client, args=(client_sock,))
            client_handler.start()
    except Exception as e:
        print(f"[!] Failed to bind: {e}")
    finally:
        server.close()

if __name__ == '__main__':
    start_server()
