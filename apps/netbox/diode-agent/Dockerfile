FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    nmap \
    iputils-ping \
    snmp \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    netboxlabs-diode-sdk \
    kubernetes \
    pysnmp-lextudio

# Copy discovery script
COPY discovery-script.py /usr/local/bin/discover
RUN chmod +x /usr/local/bin/discover

# Run as non-root user
RUN useradd -m -u 1000 diode && \
    chown -R diode:diode /usr/local/bin/discover

USER diode

ENTRYPOINT ["python", "/usr/local/bin/discover"]
