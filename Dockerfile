# The site on any container host (Fly.io, Render, Railway). No keys needed.
#   docker build -t incumbent-clock .
#   docker run -p 8000:8000 incumbent-clock
FROM python:3.12-slim
WORKDIR /app
COPY . .
EXPOSE 8000
CMD ["python", "-m", "clock", "serve", "--host", "0.0.0.0", "--port", "8000"]
