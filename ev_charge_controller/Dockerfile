FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY evcc_app evcc_app
VOLUME /data
ENV EVCC_CONFIG=/data/config.yaml EVCC_DATA=/data PYTHONUNBUFFERED=1
EXPOSE 8088
CMD ["python", "-m", "evcc_app"]
