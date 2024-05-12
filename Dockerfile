FROM python:3.12

LABEL org.opencontainers.image.title "LLMail"
LABEL org.opencontainers.image.description "Docker image for LLMail, a tool for interacting with the LLMs via email"
LABEL org.opencontainers.image.source "https://github.com/slashtechno/wyzely-detect"
RUN pip install poetry


WORKDIR /app

COPY . .

RUN poetry install

ENTRYPOINT ["poetry", "run", "--", "llmail"]