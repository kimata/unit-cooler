ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-bookworm AS build

RUN --mount=type=cache,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install --no-install-recommends --assume-yes \
    build-essential \
    swig

ENV PATH="/root/.local/bin/:$PATH"

ENV UV_SYSTEM_PYTHON=1 \
    UV_LINK_MODE=copy

ADD https://astral.sh/uv/install.sh /uv-installer.sh

RUN sh /uv-installer.sh && rm /uv-installer.sh

# NOTE: lgpio で必要になるライブラリ
ADD http://abyz.me.uk/lg/lg.zip lg.zip
RUN unzip lg.zip
RUN make -C lg
RUN make -C lg install

# NOTE: システムにインストール
RUN --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=.python-version,target=.python-version \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=README.md,target=README.md \
    --mount=type=bind,source=.git,target=.git \
    --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-group dev --format requirements-txt > requirements.txt \
    && uv pip install -r requirements.txt

FROM python:${PYTHON_VERSION}-slim-bookworm AS prod

ARG PYTHON_VERSION
ARG IMAGE_BUILD_DATE
ENV IMAGE_BUILD_DATE=${IMAGE_BUILD_DATE}

ENV TZ=Asia/Tokyo

COPY --from=build /usr/local/lib/python${PYTHON_VERSION}/site-packages /usr/local/lib/python${PYTHON_VERSION}/site-packages

COPY --from=build /usr/local/lib/liblgpio.so* /usr/local/lib
RUN ldconfig


WORKDIR /opt/unit_cooler

COPY . .

EXPOSE 2222
EXPOSE 5000
EXPOSE 5001

CMD ["./src/controller.py"]
