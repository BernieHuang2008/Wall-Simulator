import docker
import os
import yaml
import time
import io
import tarfile

class TestManager:
    def __init__(self, base_dir):
        self.client = docker.from_env()
        self.base_dir = base_dir
        self.network_name = "wall_sim_net"
        self.containers = {}

    def _make_tarfile(self, source_dir):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as tar:
            tar.add(source_dir, arcname=os.path.basename(source_dir))
        stream.seek(0)
        return stream

    def _run_start_script(self, test_name, role):
        if role not in self.containers:
            return
            
        container = self.containers[role]
        test_path = os.path.join(self.base_dir, 'testee', test_name)
        config_path = os.path.join(test_path, role, 'config.yaml')
        script_dir = os.path.join(test_path, role, 'start_script')
        
        # Load config to check for start_script
        config = self.load_config(test_name).get(role, {})
        commands = config.get('start_script')
        
        if commands and os.path.isdir(script_dir):
            print(f"[{role}] Deploying start_script from {script_dir}...")
            # Create tar archive
            stream = self._make_tarfile(script_dir)
            # Copy archive to container root (creates /start_script)
            try:
                container.put_archive('/', stream)
            except Exception as e:
                print(f"[{role}] Failed to copy start_script: {e}")
                return

            # Run commands
            for cmd in commands:
                print(f"[{role}] Executing: {cmd}")
                try:
                    exit_code, output = container.exec_run(
                        cmd, 
                        workdir='/start_script' 
                    )
                    if exit_code != 0:
                        print(f"[{role}] Command failed ({exit_code}): {output.decode()}")
                    else:
                        print(f"[{role}] Output: {output.decode()}")
                except Exception as e:
                    print(f"[{role}] Execution error: {e}")


    def load_config(self, test_name):
        test_path = os.path.join(self.base_dir, 'testee', test_name)
        configs = {}
        for role in ['A', 'B', 'W']:
            config_path = os.path.join(test_path, role, 'config.yaml')
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    configs[role] = yaml.safe_load(f)
            else:
                raise FileNotFoundError(f"Config for {role} not found at {config_path}")
        return configs

    def setup_network(self):
        try:
            network = self.client.networks.get(self.network_name)
            network.remove()
        except docker.errors.NotFound:
            pass
        
        # Create a subnet where we can control IPs
        ipam_pool = docker.types.IPAMPool(
            subnet='172.20.0.0/16',
            gateway='172.20.0.1'
        )
        ipam_config = docker.types.IPAMConfig(pool_configs=[ipam_pool])
        return self.client.networks.create(
            self.network_name,
            driver="bridge",
            ipam=ipam_config,
            options={"com.docker.network.bridge.enable_icc": "true"} # Allow inter-container communication
        )
    
    def create_container(self, name, config):
        image = config.get('image', 'ubuntu:latest')
        ports_map = {}
        
        # Service ports
        service_ports = config.get('network', {}).get('forward_ports', []) or []
        for p in service_ports:
            ports_map[f"{p}/tcp"] = p
            
        # Wireshark port mapping
        wireshark_config = config.get('wireshark', {})
        if wireshark_config.get('enabled', False):
            ws_port = wireshark_config.get('port', 3000)
            # Wireshark internal port is 3000
            ports_map["3000/tcp"] = ws_port

        return self.client.containers.create(
            image,
            name=name,
            # network_mode='none', 
            cap_add=['NET_ADMIN'],
            command=["tail", "-f", "/dev/null"],
            ports=ports_map
        )

    def _start_wireshark_sidecar(self, role, parent_container, config):
        wireshark_config = config.get('wireshark', {})
        if not wireshark_config.get('enabled', False):
            return

        print(f"[{role}] Starting Wireshark sidecar...")
        try:
            self.client.containers.run(
                "linuxserver/wireshark:latest",
                name=f"{parent_container.name}_wireshark",
                network_mode=f"container:{parent_container.id}",
                environment={
                    "PUID": "1000",
                    "PGID": "1000",
                    "TZ": "Etc/UTC"
                },
                cap_add=['NET_ADMIN'],
                detach=True
            )
            # Track it for cleanup
            self.containers[f"{role}_wireshark"] = self.client.containers.get(f"{parent_container.name}_wireshark")
        except Exception as e:
            print(f"[{role}] Failed to start Wireshark sidecar: {e}")

    def start_test(self, test_name):
        configs = self.load_config(test_name)
        network = self.setup_network()
        
        # Helper to get IP from config
        def get_ip(role):
            return configs[role].get('network', {}).get('ip')

        w_ip = get_ip('W')
        a_ip = get_ip('A')
        b_ip = get_ip('B')

        # Start W first as it might be the gateway
        w_config = configs['W']
        self.containers['W'] = self.create_container(f"{test_name}_W", w_config)
        network.connect(self.containers['W'], ipv4_address=w_ip)
        self.containers['W'].start()
        
        # Start Wireshark Sidecar for W if configured
        self._start_wireshark_sidecar('W', self.containers['W'], w_config)
        
        # Run start script for W
        self._run_start_script(test_name, 'W')

        # Enable forwarding on W and disable ICMP redirects
        # Disabling redirects is CRITICAL: 
        # Since A and B are on the same subnet, W would normally send an ICMP Redirect 
        # telling A to contact B directly. We want to force traffic through W.
        self.containers['W'].exec_run("sysctl -w net.ipv4.ip_forward=1")
        self.containers['W'].exec_run("sysctl -w net.ipv4.conf.all.send_redirects=0")
        self.containers['W'].exec_run("sysctl -w net.ipv4.conf.default.send_redirects=0")
        self.containers['W'].exec_run("sysctl -w net.ipv4.conf.eth0.send_redirects=0")

        # Start A and B
        for role in ['A', 'B']:
            cfg = configs[role]
            self.containers[role] = self.create_container(f"{test_name}_{role}", cfg)
            
            ip = cfg.get('network', {}).get('ip') # Fixed to use local var 'ip' correctly
            network.connect(self.containers[role], ipv4_address=ip)
            self.containers[role].start()
            
            self._run_start_script(test_name, role)

        # Configure Routes
        # A -> B via W
        # Critical: A and B are on the same subnet. Linux kernel will prefer the direct link connection
        # over the gateway unless we are very specific or delete the link route (which breaks gateway comms).
        # We generally add a specific host route (/32) which has higher priority than the subnet route (/16).
        # We assume the containers have 'ip' command available (iproute2 package).
        # If the direct route still takes precedence, we might need to delete the ARP entry or use policy routing,
        # but usually a specific route 'via' gateway works if valid.
        
        print("Configuring static routes and suppressing ARP...")
        
        try:
            # Helper to rename interface and update internal state
            def configure_interface(role, ip_addr):
                # 1. Start by finding the interface for `ip_addr`
                # Fix: removed extra backslash used for escaping $ in awk. 
                # docker exec argument parsing can be tricky. We try to be as clean as possible.
                # We want the shell to execute: ip -o addr show | grep 'inet <ip>' | awk '{print $2}'
                cmd_find = f"ip -o addr show | grep 'inet {ip_addr}' | awk '{{print $2}}'"
                
                # Wrapping in sh -c to ensure pipe handling
                cmd_full = ["/bin/sh", "-c", cmd_find]
                
                exit_code, output = self.containers[role].exec_run(cmd_full)
                old_iface = output.decode().strip()
                
                if not old_iface:
                    print(f"[{role}] Warning: Could not find interface for {ip_addr}")
                    return "eth0", None 

                # 2. Rename it to 'eth_wallsim'
                # Note: 'ip link set name' requires the interface to be DOWN first.
                rename_cmds = (
                    f"ip link set dev {old_iface} down && "
                    f"ip link set dev {old_iface} name eth_wallsim && "
                    f"ip link set dev eth_wallsim up"
                )
                
                # We attempt rename. If it fails, we fall back to old name.
                exit_code, output = self.containers[role].exec_run(["/bin/sh", "-c", rename_cmds])
                
                final_iface = "eth_wallsim"
                if exit_code != 0:
                    print(f"[{role}] Failed to rename interface from {old_iface}: {output.decode()}")
                    final_iface = old_iface

                # 3. Get the MAC address
                cmd = f"cat /sys/class/net/{final_iface}/address"
                exit_code, output = self.containers[role].exec_run(cmd)
                mac = output.decode().strip() if exit_code == 0 else None
                return final_iface, mac

            w_iface, w_mac = configure_interface('W', w_ip)
            a_iface, a_mac = configure_interface('A', a_ip)
            b_iface, b_mac = configure_interface('B', b_ip)

            if w_mac and a_mac and b_mac:
                print(f"[Info] Interfaces renamed to eth_wallsim. MACs - W:{w_mac}, A:{a_mac}, B:{b_mac}")

                # 2. Configure A: Route to B via W
                self.containers['A'].exec_run(f"ip neigh add {w_ip} lladdr {w_mac} dev {a_iface}")
                self.containers['A'].exec_run(f"ip route add {b_ip}/32 via {w_ip} dev {a_iface}")

                # 3. Configure B: Route to A via W
                self.containers['B'].exec_run(f"ip neigh add {w_ip} lladdr {w_mac} dev {b_iface}")
                self.containers['B'].exec_run(f"ip route add {a_ip}/32 via {w_ip} dev {b_iface}")

                # 4. Configure W (The Router)
                self.containers['W'].exec_run(f"ip neigh add {a_ip} lladdr {a_mac} dev {w_iface}")
                self.containers['W'].exec_run(f"ip neigh add {b_ip} lladdr {b_mac} dev {w_iface}")
                
            else:
                print("[Error] Could not retrieve all MAC addresses.")

        except Exception as e:
            print(f"Error configuring static ARP: {e}")

        return str({k: v.status for k,v in self.containers.items()})

    def _get_mac_for_config(self, role, iface_name):
        cmd = f"cat /sys/class/net/{iface_name}/address"
        exit_code, output = self.containers[role].exec_run(cmd)
        return output.decode().strip() if exit_code == 0 else None

    def stop_test(self):
        for role, container in self.containers.items():
            try:
                container.stop()
                container.remove()
            except:
                pass
        self.containers = {}

    def get_status(self):
        status = {}
        for role, container in self.containers.items():
            try:
                container.reload()
                status[role] = container.status
            except:
                status[role] = "stopped"
        return status

    def execute_command(self, role, command):
        if role in self.containers:
            container = self.containers[role]
            try:
                # This returns a tuple (exit_code, output)
                return container.exec_run(command)
            except Exception as e:
                return (1, str(e).encode())
        return (1, b"Container not running")
