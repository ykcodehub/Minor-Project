FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.runtime.lock pyproject.toml alembic.ini ./
COPY app ./app
COPY migrations ./migrations
RUN pip install --no-cache-dir -r requirements.runtime.lock && pip install --no-cache-dir --no-deps . && useradd --uid 10001 --create-home veriora
USER veriora
EXPOSE 8000
CMD ["python", "-m", "app.serve"]
