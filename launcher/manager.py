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
        # Create without network first to avoid default bridge attachment
        # network_mode='none' ensures no default network
        self.containers['W'] = self.client.containers.create(
            w_config.get('image', 'ubuntu:latest'),
            name=f"{test_name}_W",
            # network_mode='none', 
            cap_add=['NET_ADMIN'],
            command=["tail", "-f", "/dev/null"]
        )
        network.connect(self.containers['W'], ipv4_address=w_ip)
        self.containers['W'].start()
        
        # Run start script for W
        self._run_start_script(test_name, 'W')

        # Enable forwarding on W
        self.containers['W'].exec_run("sysctl -w net.ipv4.ip_forward=1")

        # Start A and B
        for role in ['A', 'B']:
            cfg = configs[role]
            ip = cfg.get('network', {}).get('ip') # Fixed to use local var 'ip' correctly
            self.containers[role] = self.client.containers.create(
                cfg.get('image', 'ubuntu:latest'),
                name=f"{test_name}_{role}",
                # network_mode='none',
                cap_add=['NET_ADMIN'], 
                command=["tail", "-f", "/dev/null"]
            )
            network.connect(self.containers[role], ipv4_address=ip)
            self.containers[role].start()
            self._run_start_script(test_name, role)

        # Configure Routes
        # A -> B via W
        # Since we use network_mode='none' then connect to custom network, 
        # the interface inside is likely 'eth0' or 'eth1'. 
        # Usually checking output of 'ip addr' is safer, but assuming eth0 for single network.
        # We need to delete default route (if any, usually none with custom IPAM?) or add specific route.
        # Custom network usually adds a default route to the gateway (172.20.0.1).
        # We want traffic to B (172.20.0.11) to go via W (172.20.0.12).
        # Since they are on the SAME SUBNET (172.20.0.0/16), we must force it.
        self.containers['A'].exec_run(f"ip route add {b_ip} via {w_ip}")
        self.containers['B'].exec_run(f"ip route add {a_ip} via {w_ip}")

        return str({k: v.status for k,v in self.containers.items()})

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
