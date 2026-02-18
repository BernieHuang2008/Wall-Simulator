# Wall Simulator

## Project Structure

```
project_root/
  launcher/
    app.py           # Main Flask application
    manager.py       # Docker orchestration logic
    requirements.txt # Python dependencies
    templates/
      index.html     # Web dashboard
  testee/
    test_20260218/   # Sample test case
      A/
        config.yaml
      B/
        config.yaml
      W/
        config.yaml
```

## Setup & Running (Linux Environment)

1.  **Install Dependencies**:
    Ensure Docker is installed and running on the host.
    Install Python dependencies:
    ```bash
    pip install -r launcher/requirements.txt
    ```

2.  **Configuration**:
    Edit `testee/test_NAME/ROLE/config.yaml` to change images or IP addresses.
    Ensure IP addresses are within the `172.20.0.0/16` subnet, as hardcoded in `manager.py`.

3.  **Run Launcher**:
    ```bash
    python launcher/app.py
    ```

4.  **Access Dashboard**:
    Open `http://localhost:5000` in your browser.
    - Select a test (e.g., `test_20260218`) and click "Start Test".
    - Use the Console section to send commands to A, B, or W.
    - Example: In container A, try `ping 172.20.0.11` (B's IP). Traffic should route through W.
    - In container W, you can run `tcpdump -n -i eth0` to see traffic.

## Architecture Notes

-   **Networking**: A custom bridge network `wall_sim_net` (172.20.0.0/16) is created.
-   **Routing**:
    -   Container W is configured with IP forwarding enabled.
    -   Container A has a static route to B via W.
    -   Container B has a static route to A via W.
-   **Monitoring**: W sees all traffic between A and B on the network level.

# 网络拓扑与拦截 (Network Routing):
在 manager.py 中，我实现了一个自定义的 Docker Bridge 网络 wall_sim_net (172.20.0.0/16)。

- `W 容器`: 开启了 IP Forwarding (sysctl -w net.ipv4.ip_forward=1)，充当路由器。
- `A 容器`: 添加了一其路由规则，强制去往 B 的流量经过 W (ip route add <B_IP> via <W_IP>)。
- `B 容器`: 同理，去往 A 的流量也被强制经过 W。

这样，W 作为一个纯粹的“管道监听器”，可以捕获所有经过的 TCP/UDP 流量，且不需要任何密钥或证书，因为它仅在网络层（IP层）转发包。
