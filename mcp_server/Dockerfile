FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py entrypoint.sh ./
RUN chmod +x entrypoint.sh

EXPOSE 6701
ENV PYTHONUNBUFFERED=1
ENV METRO_MCP_SERVER_PORT=6701

CMD ["./entrypoint.sh"]
