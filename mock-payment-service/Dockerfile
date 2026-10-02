FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mock-payment-service/ ./mock-payment-service/

EXPOSE 8001

CMD ["uvicorn", "mock-payment-service.app.main:app", "--host", "0.0.0.0", "--port", "8001"]
