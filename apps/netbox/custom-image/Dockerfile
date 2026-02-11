ARG NETBOX_VERSION=v4.5.2
FROM ghcr.io/netbox-community/netbox:${NETBOX_VERSION}

RUN /opt/netbox/venv/bin/python -m ensurepip && \
    /opt/netbox/venv/bin/python -m pip install --no-cache-dir netboxlabs-diode-netbox-plugin
