FROM docker.io/library/python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --system --uid 10001 voc && mkdir /media/uploads && chown voc /media/uploads
COPY config config
COPY voc voc
COPY templates templates
COPY static static
COPY manage.py .
COPY deploy/entrypoint.sh /usr/local/bin/voc-start
RUN sed -i 's/\r$//' /usr/local/bin/voc-start && chmod 755 /usr/local/bin/voc-start
USER voc
CMD ["/usr/local/bin/voc-start"]
