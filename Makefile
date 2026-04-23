.PHONY: start trigger-pipeline generate gate rollback

start:
	./scripts/start.sh

trigger-pipeline:
	./devops/scripts/trigger-pipeline.sh

generate:
	./scripts/generate.sh

gate:
	./scripts/gate.sh

rollback:
	./scripts/rollback.sh
