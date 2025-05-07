FROM odoo:18

USER root

RUN apt-get update && \
    apt-get install -y python3-pip && \
    pip3 install --break-system-packages paho-mqtt

USER odoo
