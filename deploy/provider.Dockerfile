FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY paysim/ ./paysim/
COPY provider_api/ ./provider_api/
EXPOSE 8001
CMD ["uvicorn", "provider_api.main:app", "--host", "0.0.0.0", "--port", "8001"]
