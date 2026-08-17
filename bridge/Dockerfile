FROM python:3.12-alpine
WORKDIR /app
COPY bridge/tvbox_luna_bridge.py /app/bridge/tvbox_luna_bridge.py
COPY tvbox-jsm.json /app/tvbox-jsm.json
EXPOSE 8787
CMD ["python", "bridge/tvbox_luna_bridge.py", "--host", "0.0.0.0", "--port", "8787", "--tvbox", "tvbox-jsm.json"]
