SHELL := /usr/bin/env bash

.DEFAULT_GOAL := help

VERSION ?=
IMAGE ?=
OUTPUT ?=
PLATFORM ?=

RELEASE_ARGS :=
ifneq ($(strip $(VERSION)),)
RELEASE_ARGS += --version $(VERSION)
endif
ifneq ($(strip $(IMAGE)),)
RELEASE_ARGS += --image $(IMAGE)
endif
ifneq ($(strip $(OUTPUT)),)
RELEASE_ARGS += --output $(OUTPUT)
endif
ifneq ($(strip $(PLATFORM)),)
RELEASE_ARGS += --platform $(PLATFORM)
endif
ifeq ($(PULL),1)
RELEASE_ARGS += --pull
endif
ifeq ($(SKIP_BUILD),1)
RELEASE_ARGS += --skip-build
endif

.PHONY: help release release-amd64 release-arm64

help:
	@printf '%s\n' '可用命令:'
	@printf '  %-16s %s\n' 'make release' '构建 Docker 镜像并生成 dist/*.run 安装包'
	@printf '  %-16s %s\n' 'make release-amd64' '按 linux/amd64 构建安装包'
	@printf '  %-16s %s\n' 'make release-arm64' '按 linux/arm64 构建安装包'
	@printf '%s\n' ''
	@printf '%s\n' '常用变量: VERSION=20260611.1 IMAGE=medteach-agent-demo:20260611.1 OUTPUT=dist/demo.run PLATFORM=linux/amd64 PULL=1 SKIP_BUILD=1'

release:
	./scripts/build-run-package.sh $(RELEASE_ARGS)

release-amd64:
	$(MAKE) release PLATFORM=linux/amd64

release-arm64:
	$(MAKE) release PLATFORM=linux/arm64
