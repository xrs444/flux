#!/usr/bin/env python3
"""
NetBox Diode Discovery Agent
Discovers network devices and pushes them to NetBox via Diode SDK
"""

import os
import sys
import json
import logging
import subprocess
from typing import List

from netboxlabs.diode.sdk import DiodeClient
from netboxlabs.diode.sdk.ingester import (
    Device,
    DeviceType,
    Entity,
    IPAddress,
    Platform,
    Site,
)

logger = logging.getLogger("diode-agent")


def discover_kubernetes(site: str, device_role: str) -> List[Entity]:
    """Discover Kubernetes nodes and return Diode entities."""
    from kubernetes import client, config

    entities = []
    try:
        config.load_incluster_config()
        v1 = client.CoreV1Api()
    except Exception as e:
        logger.error(f"Failed to load Kubernetes config: {e}")
        return entities

    try:
        nodes = v1.list_node()
        for node in nodes.items:
            name = node.metadata.name
            labels = node.metadata.labels or {}
            info = node.status.node_info

            # Determine role from labels
            if any(k in labels for k in [
                "node-role.kubernetes.io/master",
                "node-role.kubernetes.io/control-plane",
            ]):
                role = "kubernetes-control-plane"
            else:
                role = device_role

            # Check readiness
            status = "active"
            for condition in node.status.conditions or []:
                if condition.type == "Ready" and condition.status != "True":
                    status = "offline"

            device = Device(
                name=name,
                device_type=DeviceType(model=info.os_image),
                platform=Platform(name=f"kubernetes-{info.kubelet_version}"),
                site=Site(name=site),
                role=role,
                serial=info.machine_id[:16] if info.machine_id else "",
                status=status,
                tags=["kubernetes", "auto-discovered"],
            )
            entities.append(Entity(device=device))

            # Add IP addresses
            for addr in node.status.addresses or []:
                if addr.type in ("InternalIP", "ExternalIP"):
                    ip = IPAddress(address=f"{addr.address}/32")
                    entities.append(Entity(ip_address=ip))

            logger.info(f"Discovered K8s node: {name}")

    except Exception as e:
        logger.error(f"Error discovering Kubernetes nodes: {e}")

    return entities


def discover_nmap(ranges: List[str], site: str, device_role: str) -> List[dict]:
    """Scan network ranges with nmap and return host info dicts."""
    hosts = []

    for network_range in ranges:
        logger.info(f"Scanning network range: {network_range}")
        try:
            result = subprocess.run(
                ["nmap", "-sn", "-oG", "-", network_range],
                capture_output=True,
                text=True,
                timeout=600,
            )
            for line in result.stdout.split("\n"):
                if "Host:" in line and "Status: Up" in line:
                    parts = line.split()
                    ip = parts[1]
                    hostname = parts[2].strip("()") if len(parts) > 2 and parts[2] != "()" else None
                    hosts.append({"ip": ip, "hostname": hostname or ip})
                    logger.info(f"Discovered host: {hostname or ip} ({ip})")
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout scanning {network_range}")
        except Exception as e:
            logger.error(f"Error scanning {network_range}: {e}")

    return hosts


def discover_snmp(hosts: List[dict], community: str, site: str, device_role: str) -> List[Entity]:
    """Query discovered hosts via SNMP and return Diode entities."""
    from pysnmp.hlapi import (
        getCmd, SnmpEngine, CommunityData, UdpTransportTarget,
        ContextData, ObjectType, ObjectIdentity,
    )

    entities = []
    oids = {
        "sysDescr": "1.3.6.1.2.1.1.1.0",
        "sysName": "1.3.6.1.2.1.1.5.0",
        "sysLocation": "1.3.6.1.2.1.1.6.0",
        "sysContact": "1.3.6.1.2.1.1.4.0",
    }

    for host in hosts:
        ip = host["ip"]
        info = {}

        for name, oid in oids.items():
            try:
                error_indication, error_status, _, var_binds = next(
                    getCmd(
                        SnmpEngine(),
                        CommunityData(community),
                        UdpTransportTarget((ip, 161), timeout=5, retries=2),
                        ContextData(),
                        ObjectType(ObjectIdentity(oid)),
                    )
                )
                if not error_indication and not error_status:
                    info[name] = str(var_binds[0][1])
            except Exception:
                pass

        if not info:
            # No SNMP response — create a basic device from nmap data
            device = Device(
                name=host["hostname"],
                device_type=DeviceType(model="Generic Device"),
                site=Site(name=site),
                role=device_role,
                status="active",
                tags=["nmap", "auto-discovered"],
            )
        else:
            device_name = info.get("sysName", host["hostname"])
            device = Device(
                name=device_name,
                device_type=DeviceType(model=_map_device_type(info.get("sysDescr", ""))),
                site=Site(name=site),
                role=device_role,
                status="active",
                tags=["snmp", "auto-discovered"],
            )

        entities.append(Entity(device=device))

        # Add primary IP
        ip_entity = IPAddress(address=f"{ip}/32")
        entities.append(Entity(ip_address=ip_entity))
        logger.info(f"Prepared device: {device.name} ({ip})")

    return entities


def _map_device_type(sys_descr: str) -> str:
    """Map SNMP sysDescr to a device type model name."""
    lower = sys_descr.lower()
    if "cisco" in lower:
        return "Cisco Switch" if "switch" in lower else "Cisco Device"
    if "juniper" in lower:
        return "Juniper Device"
    if "aruba" in lower:
        return "Aruba Device"
    if "ubiquiti" in lower or "unifi" in lower:
        return "Ubiquiti Device"
    if "mikrotik" in lower:
        return "MikroTik Device"
    return "Generic Device"


def main():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("Starting NetBox Diode Discovery Agent")

    diode_target = os.getenv("DIODE_TARGET", "grpc://localhost:8080/diode")
    enabled_methods = [m.strip() for m in os.getenv("DISCOVERY_ENABLED_METHODS", "").split(",") if m.strip()]
    site = os.getenv("DEFAULT_SITE", "homelab")
    device_role = os.getenv("DEFAULT_DEVICE_ROLE", "network-device")

    all_entities: List[Entity] = []

    # Kubernetes discovery
    if "kubernetes" in enabled_methods:
        logger.info("Running Kubernetes discovery")
        k8s_entities = discover_kubernetes(
            site=os.getenv("K8S_NODE_SITE", site),
            device_role=os.getenv("K8S_NODE_DEVICE_ROLE", "server"),
        )
        all_entities.extend(k8s_entities)
        logger.info(f"Kubernetes discovery produced {len(k8s_entities)} entities")

    # Network scan + SNMP enrichment
    nmap_hosts = []
    if "nmap" in enabled_methods:
        logger.info("Running network scan")
        scan_ranges = [r.strip() for r in os.getenv("NETWORK_SCAN_RANGES", "").split(",") if r.strip()]
        if scan_ranges:
            nmap_hosts = discover_nmap(scan_ranges, site, device_role)
            logger.info(f"Network scan found {len(nmap_hosts)} hosts")

    if "snmp" in enabled_methods and nmap_hosts:
        logger.info("Running SNMP discovery on discovered hosts")
        community = os.getenv("SNMP_COMMUNITY", "public")
        snmp_entities = discover_snmp(nmap_hosts, community, site, device_role)
        all_entities.extend(snmp_entities)
    elif nmap_hosts:
        # No SNMP — create basic entities from nmap results
        for host in nmap_hosts:
            device = Device(
                name=host["hostname"],
                device_type=DeviceType(model="Generic Device"),
                site=Site(name=site),
                role=device_role,
                status="active",
                tags=["nmap", "auto-discovered"],
            )
            all_entities.append(Entity(device=device))
            ip_entity = IPAddress(address=f"{host['ip']}/32")
            all_entities.append(Entity(ip_address=ip_entity))

    if not all_entities:
        logger.warning("No entities discovered")
        return 0

    # Push to Diode
    logger.info(f"Ingesting {len(all_entities)} entities into Diode")

    with DiodeClient(
        target=diode_target,
        app_name="diode-discovery-agent",
        app_version="1.0.0",
    ) as client:
        response = client.ingest(entities=all_entities)
        if response.errors:
            for error in response.errors:
                logger.error(f"Ingest error: {error}")
            logger.error(f"Ingestion completed with {len(response.errors)} errors")
            return 1

    logger.info("Ingestion completed successfully")

    summary = {
        "total_entities": len(all_entities),
        "methods_used": enabled_methods,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
