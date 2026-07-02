ARG NETBOX_VERSION=v4.6.4
FROM ghcr.io/netbox-community/netbox:${NETBOX_VERSION}

ADD --chmod=644 https://bootstrap.pypa.io/get-pip.py /tmp/get-pip.py
RUN /opt/netbox/venv/bin/python /tmp/get-pip.py && \
    /opt/netbox/venv/bin/pip install --no-cache-dir \
      netbox-plugin-prometheus-sd==1.3.0 && \
    rm /tmp/get-pip.py
