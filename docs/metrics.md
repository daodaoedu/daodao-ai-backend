# Metrics access

`GET /metrics` requires `Authorization: Bearer <METRICS_SECRET>` in development,
staging and production. `/metrics/` is protected before its redirect. An unset,
empty or whitespace-only secret denies access with HTTP 403; the rest of the
application can still start. Ordinary API keys and service tokens do not grant
metrics access. Health endpoints keep their existing behavior.

Use a dedicated random hex credential, separate from `API_SECRET_KEY`. Store it
in the deployment environment's GitHub `METRICS_SECRET` secret. CD writes that
value into the matching `.env.dev` or `.env.prod`; a missing GitHub secret disables
metrics access. Do not commit the value or put it in URLs.

Configure the actual scraper before deploying this change. For Prometheus, use a
credential file mounted only into that scraper:

```yaml
scrape_configs:
  - job_name: daodao-ai-backend
    scheme: https
    metrics_path: /metrics
    authorization:
      type: Bearer
      credentials_file: /run/secrets/daodao_ai_metrics
    static_configs:
      - targets: ['ai-dev.daodao.so']
```

The credential file must contain the same dedicated value. Use the appropriate
host and environment-specific credential for production. This repository does
not manage the external scraper or its secret file.

After deployment, verify anonymous and incorrect credentials receive 403 without
metric data, then verify the authorized scraper receives 200 and Prometheus text.
When rotating the credential, coordinate the GitHub secret and scraper file;
requests using the previous value will be denied after deployment. Never restore
anonymous access as a workaround for a missing scraper credential.
