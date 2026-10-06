#!/usr/bin/env bash
# 启动免安装 PostgreSQL（本仓库 tools/pgsql16，数据目录 .pgdata）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PG="$ROOT/tools/pgsql16"
DATA="$ROOT/.pgdata"
PORT="${PGPORT:-5433}"

if [ ! -x "$PG/bin/postgres" ]; then
  echo "未找到 $PG/bin/postgres，请先按 README 构建/放置 PostgreSQL。" >&2
  exit 1
fi
if [ ! -d "$DATA" ]; then
  "$PG/bin/initdb" -D "$DATA" -U tolerance --auth=trust --encoding=UTF8
fi
if ! "$PG/bin/pg_isready" -p "$PORT" -h 127.0.0.1 >/dev/null 2>&1; then
  "$PG/bin/pg_ctl" -D "$DATA" -l "$DATA/server.log" -o "-p $PORT" start
  sleep 1
fi
"$PG/bin/psql" -h 127.0.0.1 -p "$PORT" -U tolerance -d postgres -tc \
  "SELECT 1 FROM pg_database WHERE datname='tolerance_db'" | grep -q 1 \
  || "$PG/bin/createdb" -h 127.0.0.1 -p "$PORT" -U tolerance tolerance_db
echo "PostgreSQL ready on 127.0.0.1:$PORT (db=tolerance_db)"
