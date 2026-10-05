FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY intentguard/ ./intentguard/
COPY paysim/ ./paysim/
COPY gateway_api/ ./gateway_api/
COPY experiments/results/ ./experiments/results/
EXPOSE 8000
CMD ["uvicorn", "gateway_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
