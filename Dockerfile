FROM ubuntu:20.04
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /opt

RUN apt update && apt install -y \
    gcc \
    python3 \
    python3-pip \
    libcups2-dev \
    python3-dev \ 
    python3-libxml2 \
&& rm -rf /var/lib/apt/lists/*

RUN pip3 install \
	pycups==2.0.1

COPY . ./

ENTRYPOINT ["./airprint-generate.py"]
