PLATFORM ?= linux/amd64
include .env
export $(shell sed 's/=.*//' .env)


down:
	docker compose down --volumes --remove-orphans --rmi all

up:
	docker compose up -d
