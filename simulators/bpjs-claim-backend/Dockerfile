FROM python:3.12-slim
WORKDIR /app
COPY requirements/base.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY libs/python-observability/jejakjkn_observability /usr/local/lib/python3.12/site-packages/jejakjkn_observability
COPY simulators/bpjs-claim-backend/ /app/
EXPOSE 8103
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8103"]
