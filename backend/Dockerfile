# One image for both backend services. docker-compose.yml runs it twice:
#   provider: uvicorn provider_api.main:app --port 8001
#   gateway:  uvicorn gateway_api.main:app  --port 8000 (default CMD)
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY intentguard/ ./intentguard/
COPY paysim/ ./paysim/
COPY gateway_api/ ./gateway_api/
COPY provider_api/ ./provider_api/
COPY investigator/ ./investigator/
# Run as a non-root user (docs/SECURITY.md 8). /data holds the simulator's state volume.
RUN useradd --system --uid 10001 --no-create-home intentguard     && mkdir -p /data && chown intentguard /data /app
USER intentguard
EXPOSE 8000 8001
CMD ["uvicorn", "gateway_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
