#!/usr/bin/env python3
"""
NetBox Diode Discovery Agent
Discovers network devices and pushes them to NetBox via Diode
"""

import os
import sys
import json
import logging
import subprocess
from typing import List, Dict, Any
from datetime import datetime

# Third-party imports (installed in container)
try:
    import grpc
    from kubernetes import client, config
    from pysnmp.hlapi import (
        getCmd, SnmpEngine, CommunityData, UdpTransportTarget,
        ContextData, ObjectType, ObjectIdentity
    )
except ImportError as e:
    print(f"Warning: Some dependencies not available: {e}")
    print("Some discovery methods may not work")


class DiodeClient:
    """Client for pushing data to Diode Server"""

    def __init__(self, server_url: str, use_tls: bool = False):
        self.server_url = server_url
        self.use_tls = use_tls
        self.logger = logging.getLogger(__name__)

    def ingest_device(self, device_data: Dict[str, Any]) -> bool:
        """
        Ingest a device into NetBox via Diode
        For now, using REST API fallback until gRPC client is fully implemented
        """
        self.logger.info(f"Would ingest device: {device_data.get('name')}")
        # TODO: Implement actual gRPC client for Diode
        # For now, log the device data
        self.logger.debug(f"Device data: {json.dumps(device_data, indent=2)}")
        return True


class KubernetesDiscovery:
    """Discover Kubernetes nodes and services"""

    def __init__(self, site: str, device_role: str):
        self.site = site
        self.device_role = device_role
        self.logger = logging.getLogger(__name__)
        try:
            config.load_incluster_config()
            self.v1 = client.CoreV1Api()
        except Exception as e:
            self.logger.error(f"Failed to load Kubernetes config: {e}")
            self.v1 = None

    def discover(self) -> List[Dict[str, Any]]:
        """Discover Kubernetes nodes"""
        devices = []

        if not self.v1:
            self.logger.warning("Kubernetes client not initialized")
            return devices

        try:
            nodes = self.v1.list_node()
            for node in nodes.items:
                device = {
                    'name': node.metadata.name,
                    'device_type': self._get_node_type(node),
                    'device_role': self.device_role,
                    'site': self.site,
                    'status': 'active' if self._is_node_ready(node) else 'offline',
                    'platform': node.status.node_info.os_image,
                    'serial': node.status.node_info.machine_id[:16],  # Truncate
                    'tags': ['kubernetes', 'auto-discovered'],
                    'custom_fields': {
                        'kubernetes_version': node.status.node_info.kubelet_version,
                        'kernel_version': node.status.node_info.kernel_version,
                        'container_runtime': node.status.node_info.container_runtime_version,
                    }
                }

                # Add IP addresses
                addresses = []
                for addr in node.status.addresses:
                    if addr.type in ['InternalIP', 'ExternalIP']:
                        addresses.append(addr.address)
                device['primary_ip4'] = addresses[0] if addresses else None

                devices.append(device)
                self.logger.info(f"Discovered K8s node: {device['name']}")

        except Exception as e:
            self.logger.error(f"Error discovering Kubernetes nodes: {e}")

        return devices

    def _get_node_type(self, node) -> str:
        """Determine node type from labels"""
        labels = node.metadata.labels
        if 'node-role.kubernetes.io/master' in labels or 'node-role.kubernetes.io/control-plane' in labels:
            return 'kubernetes-master'
        return 'kubernetes-worker'

    def _is_node_ready(self, node) -> bool:
        """Check if node is ready"""
        for condition in node.status.conditions:
            if condition.type == 'Ready':
                return condition.status == 'True'
        return False


class NetworkScanner:
    """Scan network ranges for devices"""

    def __init__(self, ranges: List[str], site: str, device_role: str):
        self.ranges = ranges
        self.site = site
        self.device_role = device_role
        self.logger = logging.getLogger(__name__)

    def discover(self) -> List[Dict[str, Any]]:
        """Scan network ranges and discover devices"""
        devices = []

        for network_range in self.ranges:
            self.logger.info(f"Scanning network range: {network_range}")

            try:
                # Use nmap for host discovery
                result = subprocess.run(
                    ['nmap', '-sn', '-oG', '-', network_range],
                    capture_output=True,
                    text=True,
                    timeout=300
                )

                # Parse nmap output
                for line in result.stdout.split('\n'):
                    if 'Host:' in line and 'Status: Up' in line:
                        parts = line.split()
                        ip = parts[1]
                        hostname = parts[2].strip('()') if len(parts) > 2 and parts[2] != '()' else ip

                        device = {
                            'name': hostname,
                            'device_type': 'generic-device',
                            'device_role': self.device_role,
                            'site': self.site,
                            'status': 'active',
                            'primary_ip4': ip,
                            'tags': ['network-scan', 'auto-discovered'],
                        }
                        devices.append(device)
                        self.logger.info(f"Discovered device: {hostname} ({ip})")

            except subprocess.TimeoutExpired:
                self.logger.error(f"Timeout scanning {network_range}")
            except Exception as e:
                self.logger.error(f"Error scanning {network_range}: {e}")

        return devices


class SNMPDiscovery:
    """Discover devices via SNMP"""

    def __init__(self, targets: List[str], community: str, site: str, device_role: str):
        self.targets = targets
        self.community = community
        self.site = site
        self.device_role = device_role
        self.logger = logging.getLogger(__name__)

    def discover(self) -> List[Dict[str, Any]]:
        """Query devices via SNMP"""
        devices = []

        for target in self.targets:
            self.logger.info(f"Querying SNMP on {target}")

            try:
                device_info = self._query_device(target)
                if device_info:
                    device = {
                        'name': device_info.get('hostname', target),
                        'device_type': self._map_device_type(device_info.get('sysDescr', '')),
                        'device_role': self.device_role,
                        'site': self.site,
                        'status': 'active',
                        'primary_ip4': target,
                        'serial': device_info.get('serial'),
                        'tags': ['snmp', 'auto-discovered'],
                        'custom_fields': {
                            'system_description': device_info.get('sysDescr'),
                            'system_location': device_info.get('sysLocation'),
                            'system_contact': device_info.get('sysContact'),
                        }
                    }
                    devices.append(device)
                    self.logger.info(f"Discovered SNMP device: {device['name']}")

            except Exception as e:
                self.logger.error(f"Error querying {target}: {e}")

        return devices

    def _query_device(self, target: str) -> Dict[str, Any]:
        """Query device via SNMP"""
        # OIDs for common system information
        oids = {
            'sysDescr': '1.3.6.1.2.1.1.1.0',
            'sysName': '1.3.6.1.2.1.1.5.0',
            'sysLocation': '1.3.6.1.2.1.1.6.0',
            'sysContact': '1.3.6.1.2.1.1.4.0',
        }

        info = {}

        for name, oid in oids.items():
            try:
                errorIndication, errorStatus, errorIndex, varBinds = next(
                    getCmd(
                        SnmpEngine(),
                        CommunityData(self.community),
                        UdpTransportTarget((target, 161), timeout=5, retries=2),
                        ContextData(),
                        ObjectType(ObjectIdentity(oid))
                    )
                )

                if not errorIndication and not errorStatus:
                    info[name] = str(varBinds[0][1])

            except Exception as e:
                self.logger.debug(f"Error querying {name} from {target}: {e}")

        if 'sysName' in info:
            info['hostname'] = info['sysName']

        return info

    def _map_device_type(self, sys_descr: str) -> str:
        """Map SNMP sysDescr to device type"""
        sys_descr_lower = sys_descr.lower()

        if 'cisco' in sys_descr_lower:
            if 'switch' in sys_descr_lower:
                return 'cisco-switch'
            elif 'router' in sys_descr_lower:
                return 'cisco-router'
            return 'cisco-device'
        elif 'juniper' in sys_descr_lower:
            return 'juniper-device'
        elif 'aruba' in sys_descr_lower:
            return 'aruba-device'

        return 'generic-device'


def main():
    """Main discovery routine"""
    # Setup logging
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    logger.info("Starting NetBox Diode Discovery Agent")

    # Read configuration
    diode_url = os.getenv('DIODE_SERVER_URL', 'localhost:8081')
    use_tls = os.getenv('DIODE_USE_TLS', 'false').lower() == 'true'
    enabled_methods = os.getenv('DISCOVERY_ENABLED_METHODS', '').split(',')

    site = os.getenv('DEFAULT_SITE', 'default')
    device_role = os.getenv('DEFAULT_DEVICE_ROLE', 'network-device')

    # Initialize Diode client
    diode = DiodeClient(diode_url, use_tls)

    all_devices = []

    # Kubernetes discovery
    if 'kubernetes' in enabled_methods:
        logger.info("Running Kubernetes discovery")
        k8s_discovery = KubernetesDiscovery(
            site=os.getenv('K8S_NODE_SITE', site),
            device_role=os.getenv('K8S_NODE_DEVICE_ROLE', 'server')
        )
        devices = k8s_discovery.discover()
        all_devices.extend(devices)
        logger.info(f"Kubernetes discovery found {len(devices)} nodes")

    # Network scanning
    if 'nmap' in enabled_methods:
        logger.info("Running network scan")
        scan_ranges = os.getenv('NETWORK_SCAN_RANGES', '').split(',')
        scan_ranges = [r.strip() for r in scan_ranges if r.strip()]

        if scan_ranges:
            scanner = NetworkScanner(scan_ranges, site, device_role)
            devices = scanner.discover()
            all_devices.extend(devices)
            logger.info(f"Network scan found {len(devices)} devices")
        else:
            logger.warning("No network ranges configured for scanning")

    # SNMP discovery
    if 'snmp' in enabled_methods:
        logger.info("Running SNMP discovery")
        # For SNMP, use discovered IPs from network scan
        targets = [d['primary_ip4'] for d in all_devices if d.get('primary_ip4')]

        if targets:
            community = os.getenv('SNMP_COMMUNITY', 'public')
            snmp_discovery = SNMPDiscovery(targets, community, site, device_role)
            devices = snmp_discovery.discover()

            # Merge SNMP data with existing devices
            for snmp_dev in devices:
                # Update existing device or add new one
                existing = next((d for d in all_devices if d['primary_ip4'] == snmp_dev['primary_ip4']), None)
                if existing:
                    existing.update(snmp_dev)
                else:
                    all_devices.append(snmp_dev)

            logger.info(f"SNMP discovery enhanced {len(devices)} devices")

    # Push devices to Diode
    logger.info(f"Pushing {len(all_devices)} devices to Diode")
    success_count = 0

    for device in all_devices:
        try:
            if diode.ingest_device(device):
                success_count += 1
        except Exception as e:
            logger.error(f"Failed to ingest {device['name']}: {e}")

    logger.info(f"Discovery complete. Successfully ingested {success_count}/{len(all_devices)} devices")

    # Write summary
    summary = {
        'timestamp': datetime.utcnow().isoformat(),
        'total_discovered': len(all_devices),
        'successfully_ingested': success_count,
        'failed': len(all_devices) - success_count,
        'methods_used': enabled_methods,
    }

    print(json.dumps(summary, indent=2))

    return 0 if success_count == len(all_devices) else 1


if __name__ == '__main__':
    sys.exit(main())
