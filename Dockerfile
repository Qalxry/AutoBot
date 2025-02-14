FROM kasmweb/core-ubuntu-jammy:1.16.1

USER root

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3-tk \
    python3-dev \
    python3-pip \
    libmagic1 \
    libmagic-dev \
    xdg-utils \ 
    xdotool \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY . /AutoBot/
WORKDIR /AutoBot
RUN dpkg -i bin/QQ_3.2.12_240927_amd64_01.deb && rm -rf bin/QQ_3.2.12_240927_amd64_01.deb && \
    pip3 install --no-cache-dir -r requirements.txt

RUN chmod +x /AutoBot/run_in_docker.sh && chmod +x /AutoBot/scripts/*.sh
# CMD ["python3", "main.py"]
# CMD ["/AutoBot/run_in_docker.sh"]

# ENTRYPOINT ["bash", "/AutoBot/run_in_docker.sh"]
# CMD ["--wait"]