FROM python:3.12-slim-trixie
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 OMP_NUM_THREADS=1 PORT=8080 DB_PATH=/data/finnfinn.db
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0t64 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt && python -c "from rapidocr import RapidOCR; RapidOCR()"
COPY finnfinn/ finnfinn/
COPY web/ web/
RUN useradd -r -u 10001 finn && mkdir -p /data && chown finn:finn /data
USER finn
VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request as u,sys; sys.exit(0 if u.urlopen('http://127.0.0.1:8080/healthz',timeout=4).status==200 else 1)"
CMD ["python","-m","finnfinn"]
