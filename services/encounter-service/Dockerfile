FROM python:3.12-slim
WORKDIR /app
COPY requirements/base.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY libs/python-auth/jejakjkn_auth /usr/local/lib/python3.12/site-packages/jejakjkn_auth
COPY libs/canonical-data/jejakjkn_canonical /usr/local/lib/python3.12/site-packages/jejakjkn_canonical
COPY services/encounter-service/ /app/
EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
