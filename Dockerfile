# Name: vibesec-worker
# Based on VibeSecurity "Local-Body" Specs
FROM kalilinux/kali-rolling

# Non-interactive mode to prevent install freezes
ENV DEBIAN_FRONTEND=noninteractive

# Set Go Environment Variables explicitly
ENV GOPATH=/root/go
ENV PATH=$PATH:/usr/local/go/bin:$GOPATH/bin:/usr/local/bin

# --- NETWORK FIX: Force a reliable mirror ---
RUN echo "deb http://mirrors.ocf.berkeley.edu/kali kali-rolling main non-free contrib" > /etc/apt/sources.list

# 1. Update & Install Core Dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    wget \
    unzip \
    jq \
    massdns \
    nmap \
    golang \
    ffuf \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# --- Python Setup ---
COPY requirements.txt /tmp/requirements.txt
COPY worker_requirements.txt /tmp/worker_requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt -r /tmp/worker_requirements.txt

# --- Tool Installation Layer ---
RUN \
    # 1. Subfinder (v2.12.0)
    curl -L https://github.com/projectdiscovery/subfinder/releases/download/v2.12.0/subfinder_2.12.0_linux_amd64.zip -o subfinder.zip && \
    unzip -o subfinder.zip && mv subfinder /usr/local/bin/ && \
    # 2. Nuclei (v3.7.0)
    curl -L https://github.com/projectdiscovery/nuclei/releases/download/v3.7.0/nuclei_3.7.0_linux_amd64.zip -o nuclei.zip && \
    unzip -o nuclei.zip && mv nuclei /usr/local/bin/ && \
    # 3. Katana (v1.4.0)
    curl -L https://github.com/projectdiscovery/katana/releases/download/v1.4.0/katana_1.4.0_linux_amd64.zip -o katana.zip && \
    unzip -o katana.zip && mv katana /usr/local/bin/ && \
    # 4. HTTPX (v1.7.4)
    curl -L https://github.com/projectdiscovery/httpx/releases/download/v1.7.4/httpx_1.7.4_linux_amd64.zip -o httpx.zip && \
    unzip -o httpx.zip && mv httpx /usr/local/bin/ && \
    # 5. Naabu (v2.4.0)
    curl -L https://github.com/projectdiscovery/naabu/releases/download/v2.4.0/naabu_2.4.0_linux_amd64.zip -o naabu.zip && \
    unzip -o naabu.zip && mv naabu /usr/local/bin/ && \
    # 6. DNSX (v1.2.3)
    curl -L https://github.com/projectdiscovery/dnsx/releases/download/v1.2.3/dnsx_1.2.3_linux_amd64.zip -o dnsx.zip && \
    unzip -o dnsx.zip && mv dnsx /usr/local/bin/ && \
    # 7. AlterX (v0.1.0)
    curl -L https://github.com/projectdiscovery/alterx/releases/download/v0.1.0/alterx_0.1.0_linux_amd64.zip -o alterx.zip && \
    unzip -o alterx.zip && mv alterx /usr/local/bin/ && \
    # 8. GAU (v2.2.3)
    curl -L https://github.com/lc/gau/releases/download/v2.2.3/gau_2.2.3_linux_amd64.tar.gz -o gau.tar.gz && \
    tar -xzvf gau.tar.gz && mv gau /usr/local/bin/ && \
    # 9. PureDNS (v2.1.1)
    curl -L https://github.com/d3mondev/puredns/releases/download/v2.1.1/puredns-Linux-amd64.tgz -o puredns.tgz && \
    tar -xzvf puredns.tgz && mv puredns /usr/local/bin/ && \
    # Cleanup all zips/tars
    rm *.zip *.tar.gz *.tgz

# --- Go-Based Tools Installation ---
RUN go install github.com/BishopFox/jsluice/cmd/jsluice@latest && \
    go install github.com/tomnomnom/gf@latest && \
    go install github.com/d3mondev/puredns/v2@latest && \
    mv /root/go/bin/* /usr/local/bin/ && \
    rm -rf /root/go

# --- Fix Findomain (Using corrected URL and filename) ---
RUN curl -L https://github.com/Findomain/Findomain/releases/latest/download/findomain-linux.zip -o findomain.zip && \
    unzip findomain.zip && \
    chmod +x findomain && \
    mv findomain /usr/local/bin/ && \
    rm findomain.zip

RUN mkdir -p /root/.gf
COPY ./data/static/gf_patterns/*.json /root/.gf/

# --- Script Installers ---
RUN curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sh -s -- -b /usr/local/bin

# --- Embed Python Wrappers & Logic ---
WORKDIR /app
COPY backend/ /app/backend/
COPY data/static/ /app/data/static/
RUN mkdir -p /app/var/scan_results /app/var/generated_payloads /app/var/logs /app/var/hunter_sessions

# Fix: Set PYTHONPATH without using its own undefined value
ENV PYTHONPATH="/app"
ENV VIBESEC_STATIC_DIR="/app/data/static"
ENV VIBESEC_RUNTIME_DIR="/app/var"

WORKDIR /app
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
