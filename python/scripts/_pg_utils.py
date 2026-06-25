"""PostgreSQL 脚本共享工具函数。

提供 DATABASE_URL 解析、连接参数合并以及外部 pg 工具命令执行封装。
"""

import os
import subprocess
from urllib.parse import urlparse


def parse_database_url(url: str | None) -> dict[str, str]:
    """将 PostgreSQL 连接串解析为 pg 工具参数字典。

    支持 ``postgresql://user:pass@host:port/dbname`` 格式。
    """
    if not url:
        return {}

    parsed = urlparse(url)
    if parsed.scheme not in ("postgresql", "postgres"):
        raise ValueError(f"Unsupported database URL scheme: {parsed.scheme}")

    result: dict[str, str] = {}
    if parsed.hostname:
        result["host"] = parsed.hostname
    if parsed.port:
        result["port"] = str(parsed.port)
    if parsed.username:
        result["user"] = parsed.username
    if parsed.password:
        result["password"] = parsed.password
    if parsed.path:
        dbname = parsed.path.lstrip("/").split("?")[0]
        if dbname:
            result["dbname"] = dbname
    return result


def merge_connection_params(args) -> dict[str, str]:
    """按优先级合并连接参数：命令行参数 > 独立环境变量 > DATABASE_URL。

    ``args`` 需要暴露 ``host``、``port``、``user``、``password``、``dbname`` 属性。
    """
    url = os.getenv("DATABASE_URL")
    params = parse_database_url(url) if url else {}

    for env_key, param_key in (
        ("PGHOST", "host"),
        ("PGPORT", "port"),
        ("PGUSER", "user"),
        ("PGPASSWORD", "password"),
        ("PGDATABASE", "dbname"),
    ):
        if os.getenv(env_key):
            params[param_key] = os.getenv(env_key)

    for arg_key in ("host", "port", "user", "password", "dbname"):
        value = getattr(args, arg_key, None)
        if value:
            params[arg_key] = value

    return params


def pg_env(params: dict[str, str]) -> dict[str, str]:
    """返回包含 ``PGPASSWORD`` 的环境变量副本，供外部 pg 工具使用。"""
    env = os.environ.copy()
    if params.get("password"):
        env["PGPASSWORD"] = params["password"]
    return env


def build_pg_command(tool: str, params: dict[str, str]) -> list[str]:
    """构造 pg_dump / pg_restore / psql 等工具的基础连接参数列表。"""
    cmd = [tool]
    if params.get("host"):
        cmd.extend(["-h", params["host"]])
    if params.get("port"):
        cmd.extend(["-p", params["port"]])
    if params.get("user"):
        cmd.extend(["-U", params["user"]])
    return cmd


def run_command(
    cmd: list[str],
    env: dict[str, str],
    *,
    dry_run: bool = False,
    check: bool = True,
    capture_output: bool = True,
) -> subprocess.CompletedProcess:
    """执行外部命令；dry-run 模式下仅打印命令并返回空结果。

    默认捕获输出并在失败时抛出 ``CalledProcessError``。
    """
    if dry_run:
        print(f"[DRY-RUN] {' '.join(cmd)}")
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    result = subprocess.run(
        cmd,
        env=env,
        check=False,
        capture_output=capture_output,
        text=True,
    )
    if result.stdout:
        print(result.stdout, end="")
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            cmd,
            output=result.stdout,
            stderr=result.stderr,
        )
    return result
