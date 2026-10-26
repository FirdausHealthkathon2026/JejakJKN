FROM python:3.12-slim
WORKDIR /app
COPY requirements/base.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY adapters/simrs-b/simrs_b_adapter /app/simrs_b_adapter
COPY simulators/simrs-b-backend/ /app/
EXPOSE 8102
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8102"]
