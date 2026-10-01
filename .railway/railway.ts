/**
 * LPU Reserve on Railway — Infrastructure as Code (railway CLI >= 5.42.1, `railway` SDK 3.12).
 *
 *   cd .railway && npm ci          # the CLI evaluates this file with the SDK installed here
 *   railway link                   # once, from the repository root
 *   railway config plan            # preview the diff against the linked environment
 *   railway config apply           # only when you mean to change the live project
 *
 * This file holds no secrets. Values that are secret or deployment-specific (the Django key,
 * the email provider key, the public URL) are Railway *shared variables* that you set once in
 * the dashboard; every service references them, so web, worker and beat can never disagree.
 * docs/deployment-railway.md lists each one and what to put in it.
 *
 * Topology (P20 §6 / CES §1.1):
 *   web     gunicorn; pre-deploy runs check --deploy + migrate; health check /ready/
 *   worker  Celery worker (email, reminders, sweeps)
 *   beat    the single scheduler (run_beat holds a PostgreSQL advisory lock)
 *   backup  cron: nightly pg_dump into the private "backups" bucket
 *   postgres, redis, media bucket (private; pre-signed URLs), backups bucket
 */
import { bucket, defineRailway, github, postgres, redis, ref, service } from "railway/iac";

const REPO = "swastikongithub/Django-EduRev-P20";
// Railway's documented client-address header. The app trusts it only because this variable says
// so; requests cannot reach the service except through Railway's edge.
const CLIENT_IP_HEADER = "X-Real-IP";
// Entry point that waits for PostgreSQL before exec'ing the command. A Railway start command
// replaces the image ENTRYPOINT, so worker, beat and pre-deploy name it explicitly.
const ENTRY = "sh /app/docker/entrypoint.sh";

export default defineRailway((ctx, project) => {
  const db = postgres("postgres");
  const cache = redis("redis");
  const media = bucket("media");
  const backups = bucket("backups");

  // Deploy from main only after GitHub CI (lint, tests, e2e, security, Docker smoke, ZAP) passes.
  const source = github(REPO, { branch: "main", checkSuites: true });
  const build = { builder: "DOCKERFILE" as const, dockerfilePath: "Dockerfile" };

  const app = {
    // Shared variables: set in Project Settings → Shared Variables (see the deployment guide).
    DJANGO_SECRET_KEY: ctx.shared.DJANGO_SECRET_KEY,
    // Only during a key rotation: the previous key (docs/runbook.md#secret-rotation).
    DJANGO_SECRET_KEY_FALLBACKS: ctx.shared.DJANGO_SECRET_KEY_FALLBACKS,
    SITE_URL: ctx.shared.SITE_URL,
    ALLOWED_HOSTS: ctx.shared.ALLOWED_HOSTS,
    CSRF_TRUSTED_ORIGINS: ctx.shared.CSRF_TRUSTED_ORIGINS,
    DEFAULT_FROM_EMAIL: ctx.shared.DEFAULT_FROM_EMAIL,
    // Email: an HTTPS API (Resend) works on every Railway plan; SMTP only on Pro. Set the shared
    // variables for the path you choose; the others stay undefined and fall back to defaults.
    EMAIL_BACKEND: ctx.shared.EMAIL_BACKEND,
    RESEND_API_KEY: ctx.shared.RESEND_API_KEY,
    EMAIL_HOST: ctx.shared.EMAIL_HOST,
    EMAIL_PORT: ctx.shared.EMAIL_PORT,
    EMAIL_HOST_USER: ctx.shared.EMAIL_HOST_USER,
    EMAIL_HOST_PASSWORD: ctx.shared.EMAIL_HOST_PASSWORD,
    SENTRY_DSN: ctx.shared.SENTRY_DSN,

    DEBUG: "0",
    DEMO_MODE: "0",
    SECURE_SSL_REDIRECT: "1",
    TRUSTED_CLIENT_IP_HEADER: CLIENT_IP_HEADER,
    TRUSTED_PROXY_HOPS: "0",
    LOG_JSON: "1",

    DATABASE_URL: db.env.DATABASE_URL,
    REDIS_URL: cache.env.REDIS_URL,

    USE_S3: "1",
    S3_BUCKET: ref(media, "BUCKET"),
    S3_ENDPOINT_URL: ref(media, "ENDPOINT"),
    S3_ACCESS_KEY_ID: ref(media, "ACCESS_KEY_ID"),
    S3_SECRET_ACCESS_KEY: ref(media, "SECRET_ACCESS_KEY"),
    S3_REGION: ref(media, "REGION"),
  };

  const web = service("web", {
    source,
    build,
    // Image default command: gunicorn on $PORT behind the entrypoint.
    deploy: {
      preDeployCommand: [`${ENTRY} sh /app/docker/predeploy.sh`],
      healthcheckPath: "/ready/",
      healthcheckTimeout: 120,
      numReplicas: 1,
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 10,
      drainingSeconds: 25, // gunicorn --graceful-timeout 20
    },
    env: { ...app, WEB_CONCURRENCY: "3" },
  });

  const worker = service("worker", {
    source,
    build,
    deploy: {
      startCommand: `${ENTRY} celery -A config worker -l info --concurrency 2`,
      numReplicas: 1,
      restartPolicyType: "ALWAYS",
      drainingSeconds: 60, // SIGTERM = Celery warm shutdown: finish the running email or sweep
    },
    env: app,
  });

  // Scaling beat is safe (followers wait on the lock) but pointless: keep one replica.
  const beat = service("beat", {
    source,
    build,
    deploy: {
      startCommand: `${ENTRY} python manage.py run_beat`,
      numReplicas: 1,
      restartPolicyType: "ALWAYS",
      drainingSeconds: 10, // Beat exits on SIGTERM; its lock is released with its connection
    },
    env: app,
  });

  const backup = service("backup", {
    source,
    build: { builder: "DOCKERFILE", dockerfilePath: "docker/backup/Dockerfile" },
    deploy: {
      cronSchedule: "30 20 * * *", // 20:30 UTC = 02:00 IST, outside booking hours
      restartPolicyType: "NEVER",
    },
    env: {
      PG_MAJOR: "17", // build arg: must equal the postgres service's major version (SHOW server_version)
      DATABASE_URL: db.env.DATABASE_URL,
      BACKUP_S3_BUCKET: ref(backups, "BUCKET"),
      BACKUP_S3_ENDPOINT_URL: ref(backups, "ENDPOINT"),
      BACKUP_S3_ACCESS_KEY_ID: ref(backups, "ACCESS_KEY_ID"),
      BACKUP_S3_SECRET_ACCESS_KEY: ref(backups, "SECRET_ACCESS_KEY"),
      BACKUP_S3_REGION: ref(backups, "REGION"),
      BACKUP_RETENTION_DAYS: "14",
      BACKUP_AGE_RECIPIENT: ctx.shared.BACKUP_AGE_RECIPIENT,
    },
  });

  return project("lpu-reserve", {
    resources: [db, cache, media, backups, web, worker, beat, backup],
  });
});
